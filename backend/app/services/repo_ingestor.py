import os
import sys
import time
import shutil
import tempfile
import uuid
import zipfile
import subprocess
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import List, Dict, Any, Optional, Tuple

from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore
from backend.app.services.ast_parser import CodeASTParser, LANGUAGE_MODULE_MAP
from backend.app.config import settings

class IngestionCancelledError(Exception):
    """Raised when an ingestion job is cancelled by the user or exceeded the maximum execution cap."""
    pass

_CANCELLED_JOBS_LOCK = Lock()
_CANCELLED_JOBS: set = set()

def cancel_job(workspace_id: str) -> None:
    """Signals an active ingestion thread to halt processing immediately."""
    with _CANCELLED_JOBS_LOCK:
        _CANCELLED_JOBS.add(workspace_id)

def is_job_cancelled(workspace_id: str) -> bool:
    """Checks whether an ingestion job has been marked cancelled."""
    with _CANCELLED_JOBS_LOCK:
        return workspace_id in _CANCELLED_JOBS

def clear_job_cancellation(workspace_id: str) -> None:
    """Clears the cancellation signal once an ingestion thread has exited."""
    with _CANCELLED_JOBS_LOCK:
        _CANCELLED_JOBS.discard(workspace_id)

# Default directory & file patterns to ignore during ingestion
DEFAULT_IGNORE_PATTERNS = {
    ".git", ".github", ".idea", ".vscode", "__pycache__", "node_modules",
    "venv", ".venv", "build", "dist", "target", "qdrant_data", ".DS_Store", "fixtures", "mock_data", "scratch",
    ".next",
}

# Known binary extensions to skip
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war", ".ear",
    ".so", ".dll", ".dylib", ".exe", ".bin", ".o", ".obj",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".db", ".sqlite",
    ".iso", ".mp4", ".mov",
}

LANGUAGE_NAMES = {
    ".java": "Java", ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".cpp": "C++", ".hpp": "C++", ".c": "C", ".h": "C/C++",
}

# Files are split into overlapping line windows so every part of a large file is
# searchable (the embedding model only reads the first ~512 tokens of its input).
CHUNK_LINES = 60
CHUNK_OVERLAP = 10
MAX_AMBIGUOUS_CALLEES = 5
# Default maximum indexable source files; configurable via MAX_INDEXABLE_FILES environment variable.
# Raised to 5,000 so full medium-to-large codebases (including 400+ file repos) are indexed completely.
DEFAULT_MAX_INDEXABLE_SOURCE_FILES = 5000
MAX_INDEXABLE_SOURCE_FILES = DEFAULT_MAX_INDEXABLE_SOURCE_FILES


def chunk_text(content: str, size: int = CHUNK_LINES, overlap: int = CHUNK_OVERLAP) -> List[Tuple[int, int, str]]:
    """Returns (start_line, end_line, text) windows; 1-based, inclusive."""
    lines = content.splitlines()
    if len(lines) <= size + overlap:
        return [(1, max(1, len(lines)), content)]
    chunks, step, i = [], size - overlap, 0
    while i < len(lines):
        part = lines[i:i + size]
        chunks.append((i + 1, i + len(part), "\n".join(part)))
        if i + size >= len(lines):
            break
        i += step
    return chunks


def resolve_calls(parsed: List[Dict[str, Any]]) -> None:
    """Rewrites bare callee names (`borrowBook`) to the qualified definition name
    (`LoanService.borrowBook`) so call edges attach to the real definition node,
    not to a nameless stub. Calls from unnamed scopes are dropped."""
    defs: Dict[str, set] = {}
    for item in parsed:
        ast = item.get("ast")
        if not ast:
            continue
        for fn in ast.get("functions", []):
            full = fn.get("name")
            short = fn.get("short_name") or fn.get("name")
            if full and "anon_" not in full and "lambda_" not in full:
                if short:
                    defs.setdefault(short, set()).add(full)
                defs.setdefault(full, set()).add(full)

    for item in parsed:
        ast = item.get("ast")
        if not ast:
            continue
        file_defs = {fn.get("name") for fn in ast.get("functions", [])}
        seen, resolved = set(), []
        for call in ast.get("calls", []):
            caller = call.get("caller")
            callee = call.get("callee")
            if not caller or not callee or caller == "unnamed_entity" or callee == "unnamed_entity":
                continue
            cands = defs.get(callee)
            if not cands:
                targets = [callee]                      # external / library call
            else:
                prefix = caller.rsplit(".", 1)[0] + "." if "." in caller else None
                chosen = (
                    [d for d in cands if prefix and d.startswith(prefix)]   # same class
                    or [d for d in cands if d in file_defs]                  # same file
                    or sorted(cands)
                )
                targets = chosen if len(chosen) <= MAX_AMBIGUOUS_CALLEES else [callee]
            for t in targets:
                if (caller, t) not in seen:
                    seen.add((caller, t))
                    resolved.append({"caller": caller, "callee": t, "file": call.get("file")})
        ast["calls"] = resolved


class RepositoryIngestor:
    """Handles dynamic cloning, extraction, filtering, and indexing of code repositories."""

    def __init__(
        self,
        vector_store: Optional[Any] = None,
        graph_store: Optional[Any] = None,
        ast_parser: Optional[Any] = None,
    ):
        if vector_store is None and CodeVectorStore is not None:
            try:
                self.vector_store = CodeVectorStore()
            except Exception as e:
                self.log(f"⚠️ VectorStore auto-init notice: {e}")
                self.vector_store = None
        else:
            self.vector_store = vector_store

        if graph_store is None and Neo4jGraphStore is not None:
            try:
                self.graph_store = Neo4jGraphStore()
            except Exception as e:
                self.log(f"⚠️ GraphStore auto-init notice: {e}")
                self.graph_store = None
        else:
            self.graph_store = graph_store

        self.ast_parser = ast_parser or CodeASTParser

    def log(self, message: str) -> None:
        """Logs status messages strictly to sys.stderr to avoid polluting stdio JSON-RPC."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def is_binary_file(self, filepath: Path) -> bool:
        """Determines if a file is binary using suffix matching and null-byte inspection."""
        if filepath.suffix.lower() in BINARY_EXTENSIONS:
            return True
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return True
                chunk.decode("utf-8")
                return False
        except (UnicodeDecodeError, PermissionError, OSError):
            return True

    def collect_source_files(self, root_dir: str) -> List[Path]:
        """Traverses the root directory and collects valid text/code source files."""
        root_path = Path(root_dir).resolve()
        valid_files: List[Path] = []
        for path in root_path.rglob("*"):
            if path.is_file():
                rel_parts = set(path.relative_to(root_path).parts[:-1])
                if rel_parts.intersection(DEFAULT_IGNORE_PATTERNS):
                    continue
                if path.name.startswith(".") or self.is_binary_file(path):
                    continue
                valid_files.append(path)
        return valid_files

    def _prepare_source_files(self, source_files: List[Path]) -> Tuple[List[Path], Optional[str]]:
        """Validates file count against safety limits. Never silently drops files without an explicit warning."""
        max_limit = getattr(settings, "MAX_INDEXABLE_SOURCE_FILES", None)
        if max_limit is None:
            max_limit = int(os.getenv("MAX_INDEXABLE_FILES", str(DEFAULT_MAX_INDEXABLE_SOURCE_FILES)))
        total_found = len(source_files)
        if total_found > max_limit:
            source_files.sort(key=lambda p: 0 if p.suffix.lower() in LANGUAGE_MODULE_MAP else 1)
            selected_files = source_files[:max_limit]
            omitted = total_found - max_limit
            warning = (
                f"Warning: Codebase truncated. Indexed {max_limit} of {total_found} source files "
                f"({omitted} files omitted due to size limit). Impact analysis, call graphs, and search are incomplete."
            )
            self.log(f"⚠️ {warning}")
            return selected_files, warning
        return source_files, None

    def ingest_local_directory(self, root_dir: str, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Indexes an existing local workspace directory into Vector & Graph stores."""
        raw_files = self.collect_source_files(root_dir)
        total_found = len(raw_files)
        source_files, truncation_warning = self._prepare_source_files(raw_files)
        indexing_summary = self._index_files(root_dir, source_files, workspace_id=workspace_id)
        if truncation_warning:
            indexing_summary["warning"] = truncation_warning
            indexing_summary["truncated"] = True
            indexing_summary["total_files_found"] = total_found
            indexing_summary["indexed_files"] = len(source_files)
        return {
            "status": "success",
            "source": root_dir,
            "total_files": len(source_files),
            "total_files_found": total_found,
            "truncated": bool(truncation_warning),
            "warning": truncation_warning,
            "indexing_summary": indexing_summary,
            **indexing_summary,
        }

    def ingest_git_repo(
        self, repo_url: str, branch: Optional[str] = None, workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clones a remote Git repository into a temporary directory and indexes it with resilient branch fallbacks."""
        clean_url = (repo_url or "").strip()
        if not clean_url or clean_url.startswith("-") or any(ch in clean_url for ch in [";", "&", "|", "`", "$", "\n", "\r", " "]):
            return {"status": "error", "message": "Invalid repository URL format."}

        from urllib.parse import urlparse
        parsed = urlparse(clean_url)
        if parsed.scheme != "https":
            return {"status": "error", "message": "Only secure https:// Git repository URLs are allowed."}
        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            return {"status": "error", "message": "Invalid Git repository domain."}

        # SSRF Protection: Block internal, loopback, and cloud metadata addresses
        if hostname in ("localhost", "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0"):
            return {"status": "error", "message": "Internal, metadata, or loopback Git addresses are not permitted."}

        allowed_hosts = [h.strip().lower() for h in getattr(settings, "GIT_ALLOWED_HOSTS", "github.com,gitlab.com,bitbucket.org").split(",") if h.strip()]
        if hostname not in allowed_hosts:
            return {"status": "error", "message": f"Git host '{hostname}' is not permitted. Allowed hosts: {', '.join(allowed_hosts)}"}

        clean_branch = (branch or "").strip()
        if clean_branch and (clean_branch.startswith("-") or any(ch in clean_branch for ch in [";", "&", "|", "`", "$", "\n", "\r", " "])):
            clean_branch = "main"

        self.log(f"📥 Cloning remote Git repository: {clean_url} (requested branch: {clean_branch or 'default'})")
        temp_dir = tempfile.mkdtemp(prefix="codegraph_git_")
        clone_timeout = 120  # 2 minute timeout prevents hung workers
        git_harden_flags = [
            "-c", "protocol.allow=never",
            "-c", "protocol.https.allow=always",
            "-c", "http.followRedirects=false",
        ]
        # Prevent git from interactively prompting for username/password in terminal
        git_env = dict(os.environ, GIT_TERMINAL_PROMPT="0")

        def _clean_and_recreate_temp_dir(d: str) -> str:
            shutil.rmtree(d, ignore_errors=True)
            return tempfile.mkdtemp(prefix="codegraph_git_")

        try:
            cloned = False
            err_msg = ""

            # 1. Attempt clone with specified branch (if provided)
            if clean_branch:
                clone_cmd = ["git"] + git_harden_flags + ["clone", "--depth", "1", "-b", clean_branch, "--", clean_url, temp_dir]
                try:
                    res = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=clone_timeout, env=git_env)
                    if res.returncode == 0:
                        cloned = True
                    else:
                        err_msg = res.stderr.strip()
                        self.log(f"⚠️ Branch '{clean_branch}' clone notice: {err_msg}. Retrying remote default branch...")
                        temp_dir = _clean_and_recreate_temp_dir(temp_dir)
                except subprocess.TimeoutExpired:
                    self.log(f"⚠️ Branch '{clean_branch}' clone timed out after {clone_timeout}s. Cleaning temp dir and retrying remote default branch...")
                    err_msg = f"Git clone timed out after {clone_timeout} seconds."
                    temp_dir = _clean_and_recreate_temp_dir(temp_dir)

            # 2. Fallback: clone without branch specifier (clones remote default branch, e.g. master/main)
            if not cloned:
                fallback_cmd = ["git"] + git_harden_flags + ["clone", "--depth", "1", "--", clean_url, temp_dir]
                try:
                    res2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=clone_timeout, env=git_env)
                    if res2.returncode == 0:
                        cloned = True
                    else:
                        err_msg = res2.stderr.strip() or err_msg
                        temp_dir = _clean_and_recreate_temp_dir(temp_dir)
                except subprocess.TimeoutExpired:
                    self.log(f"⚠️ Remote default branch clone timed out after {clone_timeout}s. Cleaning temp dir before master fallback...")
                    err_msg = f"Git clone timed out after {clone_timeout} seconds."
                    temp_dir = _clean_and_recreate_temp_dir(temp_dir)

            # 3. Final fallback: explicitly try 'master' if requested branch was 'main'
            if not cloned and clean_branch != "master":
                master_cmd = ["git"] + git_harden_flags + ["clone", "--depth", "1", "-b", "master", "--", clean_url, temp_dir]
                try:
                    res3 = subprocess.run(master_cmd, capture_output=True, text=True, timeout=clone_timeout, env=git_env)
                    if res3.returncode == 0:
                        cloned = True
                    else:
                        err_msg = res3.stderr.strip() or err_msg
                except subprocess.TimeoutExpired:
                    err_msg = f"Git clone timed out after {clone_timeout} seconds."

            if not cloned:
                self.log(f"❌ Git clone error: {err_msg}")
                lower_err = err_msg.lower()
                if any(x in lower_err for x in ["redirect", "301", "302", "moved", "followredirects"]):
                    friendly_err = (
                        "Git clone failed: Repository redirect detected. For SSRF security, HTTP redirects are disabled. "
                        "Please provide the canonical repository URL (e.g. check for renamed repositories or verify the exact URL format on GitHub/GitLab)."
                    )
                elif any(x in lower_err for x in [
                    "could not read username", "could not read password", "authentication failed",
                    "terminal prompts disabled", "repository not found", "please make sure you have the correct access rights"
                ]):
                    friendly_err = (
                        "Git clone failed: Repository is private or not found. "
                        "Accessing private repositories requires credentials or is not supported. "
                        "Please ensure the repository is public and the URL is correct."
                    )
                else:
                    friendly_err = f"Git clone failed: {err_msg}"
                return {"status": "error", "message": friendly_err}

            # Detect actual cloned branch
            actual_branch = branch or "main"
            try:
                head_check = subprocess.run(
                    ["git", "-C", temp_dir, "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True
                )
                if head_check.returncode == 0 and head_check.stdout.strip():
                    actual_branch = head_check.stdout.strip()
            except Exception:
                pass

            raw_files = self.collect_source_files(temp_dir)
            total_found = len(raw_files)
            source_files, truncation_warning = self._prepare_source_files(raw_files)
            self.log(f"✅ Found {len(source_files)} source files for indexing on branch '{actual_branch}' (total discovered: {total_found}).")
            indexing_summary = self._index_files(temp_dir, source_files, workspace_id)
            if truncation_warning:
                indexing_summary["warning"] = truncation_warning
                indexing_summary["truncated"] = True
                indexing_summary["total_files_found"] = total_found
                indexing_summary["indexed_files"] = len(source_files)
            return {
                "status": "success",
                "source": clean_url,
                "branch": actual_branch,
                "total_files": len(source_files),
                "total_files_found": total_found,
                "truncated": bool(truncation_warning),
                "warning": truncation_warning,
                "indexing_summary": indexing_summary,
            }
        except IngestionCancelledError as ice:
            self.log(f"🛑 Git ingestion halted: {ice}")
            return {"status": "error", "message": str(ice)}
        except Exception as e:
            self.log(f"❌ Unexpected git ingestion error: {e}")
            return {"status": "error", "message": f"Git ingestion failed: {e}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def ingest_zip_archive(self, zip_path: str, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Extracts a local ZIP archive safely into a temporary directory and indexes it."""
        if not os.path.exists(zip_path):
            return {"status": "error", "message": f"ZIP file not found at: {zip_path}"}
        self.log(f"📦 Extracting ZIP archive: {zip_path}")
        temp_dir = tempfile.mkdtemp(prefix="codegraph_zip_")
        MAX_UNCOMPRESSED_BYTES = 2048 * 1024 * 1024  # 2 GB safety cap to prevent zip bombs
        MAX_ZIP_ENTRIES = 50000
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                infolist = zip_ref.infolist()
                if len(infolist) > MAX_ZIP_ENTRIES:
                    raise Exception(f"ZIP archive contains {len(infolist)} files, exceeding limit ({MAX_ZIP_ENTRIES}).")

                total_uncompressed = sum(member.file_size for member in infolist)
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise Exception(
                        f"Uncompressed size ({total_uncompressed // (1024 * 1024)} MB) exceeds "
                        f"safety limit ({MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB) - potential zip bomb."
                    )

                resolved_temp = os.path.realpath(temp_dir)
                prefix = resolved_temp + os.sep

                for member in infolist:
                    member_path = os.path.realpath(os.path.join(temp_dir, member.filename))
                    # Zip-slip protection: strictly enforce that member path resides inside temp directory
                    if not (member_path == resolved_temp or member_path.startswith(prefix)):
                        raise Exception(f"Zip slip security risk detected in entry: {member.filename}")

                    # Skip files in ignored dependency/build directories (directory segments only)
                    parts = member.filename.replace("\\", "/").split("/")[:-1]
                    if any(part in DEFAULT_IGNORE_PATTERNS for part in parts):
                        continue

                    # Skip non-source binary/asset extensions
                    if any(member.filename.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
                        continue

                    zip_ref.extract(member, temp_dir)
            raw_files = self.collect_source_files(temp_dir)
            total_found = len(raw_files)
            source_files, truncation_warning = self._prepare_source_files(raw_files)
            self.log(f"✅ Found {len(source_files)} source files for indexing (total discovered: {total_found}).")
            indexing_summary = self._index_files(temp_dir, source_files, workspace_id)
            if truncation_warning:
                indexing_summary["warning"] = truncation_warning
                indexing_summary["truncated"] = True
                indexing_summary["total_files_found"] = total_found
                indexing_summary["indexed_files"] = len(source_files)
            return {
                "status": "success",
                "source": zip_path,
                "total_files": len(source_files),
                "total_files_found": total_found,
                "truncated": bool(truncation_warning),
                "warning": truncation_warning,
                "indexing_summary": indexing_summary,
            }
        except IngestionCancelledError as ice:
            self.log(f"🛑 ZIP ingestion halted: {ice}")
            return {"status": "error", "message": str(ice)}
        except zipfile.BadZipFile:
            return {"status": "error", "message": "Invalid or corrupted ZIP archive."}
        except Exception as e:
            return {"status": "error", "message": f"ZIP extraction error: {e}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _parse_ast(self, file_path: Path, content: str, rel_path: str) -> Optional[Dict[str, Any]]:
        """Parses only languages the AST parser supports (never README/XML/JSON)."""
        if file_path.suffix.lower() not in LANGUAGE_MODULE_MAP or not self.ast_parser:
            return None
        try:
            if isinstance(self.ast_parser, type):
                parser_inst = self.ast_parser(str(file_path), code_str=content)
                if hasattr(parser_inst, "extract_structures"):
                    return parser_inst.extract_structures()
                if hasattr(parser_inst, "parse"):
                    return parser_inst.parse()
            elif hasattr(self.ast_parser, "extract_structures"):
                return self.ast_parser.extract_structures()
        except Exception as ast_err:
            self.log(f"⚠️ AST parsing skipped for '{rel_path}': {ast_err}")
        return None

    def _index_files(
        self, base_dir: str, files: List[Path], workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes source files through vector store and graph store in a strict single-pass streaming pipeline."""
        import gc
        ws = workspace_id or "global"
        base_path = Path(base_dir).resolve()

        # Clean slate purge on re-ingestion to eliminate stale vector chunks and orphaned graph nodes
        if ws and ws != "global":
            try:
                if self.vector_store and hasattr(self.vector_store, "delete_workspace"):
                    self.vector_store.delete_workspace(ws)
            except Exception as e:
                self.log(f"⚠️ Vector store pre-index purge notice for {ws}: {e}")
            try:
                if self.graph_store and hasattr(self.graph_store, "delete_workspace"):
                    self.graph_store.delete_workspace(ws)
            except Exception as e:
                self.log(f"⚠️ Graph store pre-index purge notice for {ws}: {e}")

        indexed_graph_nodes = 0
        indexed_graph_edges = 0
        indexed_vectors = 0
        lang_counts: Counter = Counter()
        pending_vector_items: List[Dict[str, Any]] = []
        BATCH_FLUSH_SIZE = 16
        # Track whether at least one successful write reached each backend
        graph_write_ok = False
        vector_write_ok = False
        start_time = time.time()
        MAX_INDEXING_SECONDS = 1200  # 20-minute safety cap for background ingestion thread

        def _record_upsert(n_upserted: Any) -> None:
            nonlocal indexed_vectors, vector_write_ok
            if isinstance(n_upserted, (int, float)):
                indexed_vectors += int(n_upserted)
                if n_upserted > 0:
                    vector_write_ok = True
            elif n_upserted:
                # Handles test mocks (e.g. MagicMock) returning truthy values
                vector_write_ok = True

        # Pass 1: Parse AST structures and stream vector chunking without holding file contents in RAM
        parsed: List[Dict[str, Any]] = []
        for idx, file_path in enumerate(files):
            if ws and is_job_cancelled(ws):
                self.log(f"🛑 Ingestion job for workspace '{ws}' was cancelled. Halting thread.")
                raise IngestionCancelledError(f"Ingestion for workspace '{ws}' was cancelled.")
            if time.time() - start_time > MAX_INDEXING_SECONDS:
                self.log(f"🛑 Ingestion job for workspace '{ws}' exceeded 20-minute safety cap. Halting thread.")
                raise IngestionCancelledError(f"Ingestion for workspace '{ws}' exceeded maximum safety cap (20 minutes).")

            rel_path = str(file_path.relative_to(base_path))
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue

                if file_path.suffix.lower() in LANGUAGE_NAMES:
                    lang_counts[LANGUAGE_NAMES[file_path.suffix.lower()]] += 1

                ast_data = self._parse_ast(file_path, content, rel_path)
                parsed.append({
                    "rel": rel_path,
                    "ast": ast_data,
                })

                # Chunk for Vector Store immediately to stream vector indexing and release file text
                if self.vector_store:
                    symbols = []
                    if ast_data:
                        symbols = sorted({
                            n for n in (
                                [c.get("name") for c in ast_data.get("classes", [])]
                                + [f.get("short_name") or f.get("name") for f in ast_data.get("functions", [])]
                            ) if n and n != "unnamed_entity" and "anon_" not in n and "lambda_" not in n
                        })

                    for n, (start, end, text_snippet) in enumerate(chunk_text(content)):
                        pending_vector_items.append({
                            "doc_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ws}:{rel_path}:{n}")),
                            "code_snippet": f"# File: {rel_path}\n{text_snippet}",
                            "metadata": {
                                "filepath": rel_path,
                                "filename": file_path.name,
                                "extension": file_path.suffix,
                                "workspace_id": ws,
                                "start_line": start,
                                "end_line": end,
                                "symbols": symbols,
                            },
                        })

                    # Micro-batch flush to keep memory usage flat
                    if len(pending_vector_items) >= BATCH_FLUSH_SIZE:
                        try:
                            _record_upsert(self.vector_store.upsert_code_batch(pending_vector_items))
                        except Exception as vec_err:
                            self.log(f"⚠️ Vector batch indexing notice: {vec_err}")
                        pending_vector_items.clear()

                del content
                if (idx + 1) % 25 == 0 or (idx + 1) == len(files):
                    self.log(f"📊 Progress: Parsed AST for {idx + 1}/{len(files)} files...")

                # Periodic garbage collection every 15 files
                if (idx + 1) % 15 == 0:
                    gc.collect()

            except Exception as file_err:
                self.log(f"⚠️ Skipping file '{rel_path}': {file_err}")

        # Flush any remaining vector chunks
        if self.vector_store and pending_vector_items:
            try:
                _record_upsert(self.vector_store.upsert_code_batch(pending_vector_items))
            except Exception as vec_err:
                self.log(f"⚠️ Final vector batch indexing notice: {vec_err}")
            pending_vector_items.clear()

        # Derive vector_ok from confirmed upserts and model health
        if vector_write_ok or (isinstance(indexed_vectors, (int, float)) and indexed_vectors > 0):
            vector_write_ok = True
        elif self.vector_store and hasattr(self.vector_store, "embedding_ok"):
            # If the vector store confirmed the model loaded but nothing was stored, treat as failure
            vector_write_ok = False

        # Pass 1.5: Cross-file caller-callee resolution
        resolve_calls(parsed)

        # Pass 2: Ingest resolved AST nodes and call edges into Neo4j
        for idx, item in enumerate(parsed):
            if ws and is_job_cancelled(ws):
                self.log(f"🛑 Ingestion job for workspace '{ws}' was cancelled. Halting thread.")
                raise IngestionCancelledError(f"Ingestion for workspace '{ws}' was cancelled.")
            if time.time() - start_time > MAX_INDEXING_SECONDS:
                self.log(f"🛑 Ingestion job for workspace '{ws}' exceeded 20-minute safety cap. Halting thread.")
                raise IngestionCancelledError(f"Ingestion for workspace '{ws}' exceeded maximum safety cap (20 minutes).")

            rel_path, ast_data = item["rel"], item["ast"]
            if ast_data:
                written_to_graph = False
                if self.graph_store and hasattr(self.graph_store, "ingest_ast"):
                    try:
                        ok = self.graph_store.ingest_ast(rel_path, ast_data, workspace_id=ws)
                        # ingest_ast returns True on confirmed Neo4j commit, False on error or when driver is None
                        if ok:
                            written_to_graph = True
                    except Exception as g_err:
                        self.log(f"⚠️ Graph ingest skipped for '{rel_path}': {g_err}")

                if written_to_graph:
                    nodes_count = (
                        len(ast_data.get("classes", []))
                        + len(ast_data.get("functions", []))
                        + len(ast_data.get("imports", []))
                    )
                    indexed_graph_nodes += max(1, nodes_count)
                    indexed_graph_edges += len(ast_data.get("calls", []))
                    graph_write_ok = True

                # Free AST data as we progress
                item["ast"] = None

            if (idx + 1) % 25 == 0 or (idx + 1) == len(parsed):
                self.log(f"📊 Progress: Ingested {idx + 1}/{len(parsed)} files into Neo4j ({indexed_graph_nodes} nodes, {indexed_graph_edges} edges)...")

            if (idx + 1) % 15 == 0:
                gc.collect()

        del parsed
        gc.collect()

        return {
            "vector_chunks": indexed_vectors,
            "graph_nodes": indexed_graph_nodes,
            "graph_edges": indexed_graph_edges,
            "languages": [name for name, _ in lang_counts.most_common(3)],
            # True only when at least one successful write reached each backend
            "graph_ok": graph_write_ok,
            "vector_ok": vector_write_ok,
        }
RepoIngestor = RepositoryIngestor
