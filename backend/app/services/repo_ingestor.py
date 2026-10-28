import os
import sys
import shutil
import tempfile
import uuid
import zipfile
import subprocess
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore
from backend.app.services.ast_parser import CodeASTParser, LANGUAGE_MODULE_MAP

# Default directory & file patterns to ignore during ingestion
DEFAULT_IGNORE_PATTERNS = {
    ".git", ".github", ".idea", ".vscode", "__pycache__", "node_modules",
    "venv", ".venv", "build", "dist", "target", "qdrant_data", ".DS_Store",
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
        for fn in (item["ast"] or {}).get("functions", []):
            full, short = fn.get("name"), fn.get("short_name") or fn.get("name")
            if full and short and "anon_" not in full and "lambda_" not in full:
                defs.setdefault(short, set()).add(full)

    for item in parsed:
        ast = item["ast"]
        if not ast:
            continue
        file_defs = {fn.get("name") for fn in ast.get("functions", [])}
        seen, resolved = set(), []
        for call in ast.get("calls", []):
            caller, callee = call.get("caller"), call.get("callee")
            if not caller or not callee or caller == "unnamed_entity":
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

    def ingest_git_repo(
        self, repo_url: str, branch: Optional[str] = None, workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clones a remote Git repository into a temporary directory and indexes it."""
        self.log(f"📥 Cloning remote Git repository: {repo_url}")
        temp_dir = tempfile.mkdtemp(prefix="codegraph_git_")
        try:
            clone_cmd = ["git", "clone", "--depth", "1"]
            if branch:
                clone_cmd.extend(["-b", branch])
            clone_cmd.extend([repo_url, temp_dir])
            subprocess.run(clone_cmd, capture_output=True, text=True, check=True)
            source_files = self.collect_source_files(temp_dir)
            self.log(f"✅ Found {len(source_files)} source files for indexing.")
            indexing_summary = self._index_files(temp_dir, source_files, workspace_id)
            return {
                "status": "success",
                "source": repo_url,
                "total_files": len(source_files),
                "indexing_summary": indexing_summary,
            }
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() if e.stderr else str(e)
            self.log(f"❌ Git clone error: {err_msg}")
            return {"status": "error", "message": f"Git clone failed: {err_msg}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def ingest_zip_archive(self, zip_path: str, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Extracts a local ZIP archive safely into a temporary directory and indexes it."""
        if not os.path.exists(zip_path):
            return {"status": "error", "message": f"ZIP file not found at: {zip_path}"}
        self.log(f"📦 Extracting ZIP archive: {zip_path}")
        temp_dir = tempfile.mkdtemp(prefix="codegraph_zip_")
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                resolved_temp = os.path.realpath(temp_dir)
                for member in zip_ref.infolist():
                    member_path = os.path.realpath(os.path.join(temp_dir, member.filename))
                    if not member_path.startswith(resolved_temp):
                        raise Exception(f"Zip slip security risk detected in entry: {member.filename}")

                    # Skip files in ignored dependency/build directories (directory segments only)
                    parts = member.filename.replace("\\", "/").split("/")[:-1]
                    if any(part in DEFAULT_IGNORE_PATTERNS for part in parts):
                        continue

                    # Skip non-source binary/asset extensions
                    if any(member.filename.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
                        continue

                    zip_ref.extract(member, temp_dir)
            source_files = self.collect_source_files(temp_dir)
            self.log(f"✅ Found {len(source_files)} source files for indexing.")
            indexing_summary = self._index_files(temp_dir, source_files, workspace_id)
            return {
                "status": "success",
                "source": zip_path,
                "total_files": len(source_files),
                "indexing_summary": indexing_summary,
            }
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
        """Processes source files through vector store and graph store pipelines."""
        ws = workspace_id or "global"
        base_path = Path(base_dir).resolve()

        # Pass 1: read + parse every file
        parsed: List[Dict[str, Any]] = []
        lang_counts: Counter = Counter()
        for file_path in files:
            rel_path = str(file_path.relative_to(base_path))
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue
                parsed.append({
                    "rel": rel_path,
                    "path": file_path,
                    "content": content,
                    "ast": self._parse_ast(file_path, content, rel_path),
                })
                if file_path.suffix.lower() in LANGUAGE_NAMES:
                    lang_counts[LANGUAGE_NAMES[file_path.suffix.lower()]] += 1
            except Exception as file_err:
                self.log(f"⚠️ Skipping file '{rel_path}': {file_err}")

        # Pass 2: link calls to their definitions across the whole repository
        resolve_calls(parsed)

        indexed_graph_nodes = indexed_graph_edges = 0
        batch_vector_items = []
        for item in parsed:
            rel_path, content, ast_data = item["rel"], item["content"], item["ast"]
            symbols = []
            if ast_data:
                symbols = sorted({
                    n for n in (
                        [c.get("name") for c in ast_data.get("classes", [])]
                        + [f.get("short_name") or f.get("name") for f in ast_data.get("functions", [])]
                    ) if n and n != "unnamed_entity" and "anon_" not in n and "lambda_" not in n
                })

                if self.graph_store and hasattr(self.graph_store, "ingest_ast"):
                    try:
                        self.graph_store.ingest_ast(rel_path, ast_data, workspace_id=ws)
                    except Exception as g_err:
                        self.log(f"⚠️ Graph ingest skipped for '{rel_path}': {g_err}")
                nodes_count = (
                    len(ast_data.get("classes", []))
                    + len(ast_data.get("functions", []))
                    + len(ast_data.get("imports", []))
                )
                indexed_graph_nodes += max(1, nodes_count)
                indexed_graph_edges += len(ast_data.get("calls", []))

            if self.vector_store:
                for n, (start, end, text) in enumerate(chunk_text(content)):
                    batch_vector_items.append({
                        # Deterministic per (workspace, file, chunk): re-ingest overwrites, repos never collide
                        "doc_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ws}:{rel_path}:{n}")),
                        "code_snippet": f"# File: {rel_path}\n{text}",
                        "metadata": {
                            "filepath": rel_path,
                            "filename": item["path"].name,
                            "extension": item["path"].suffix,
                            "workspace_id": ws,
                            "start_line": start,
                            "end_line": end,
                            "symbols": symbols,
                        },
                    })

        indexed_vectors = 0
        if self.vector_store and batch_vector_items:
            try:
                if hasattr(self.vector_store, "upsert_code_batch"):
                    indexed_vectors = self.vector_store.upsert_code_batch(batch_vector_items)
            except Exception as vec_err:
                self.log(f"⚠️ Vector batch indexing notice: {vec_err}")

        return {
            "vector_chunks": indexed_vectors,
            "graph_nodes": indexed_graph_nodes,
            "graph_edges": indexed_graph_edges,
            "languages": [name for name, _ in lang_counts.most_common(3)],
        }


RepoIngestor = RepositoryIngestor
