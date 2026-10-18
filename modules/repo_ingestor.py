import os
import sys
import shutil
import tempfile
import zipfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# Default directory & file patterns to ignore during ingestion
DEFAULT_IGNORE_PATTERNS = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "build",
    "dist",
    "target",
    "qdrant_data",
    ".DS_Store",
}

# Known binary extensions to skip
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war", ".ear",
    ".so", ".dll", ".dylib", ".exe", ".bin", ".o", ".obj",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".db", ".sqlite"
}


class RepositoryIngestor:
    """Handles dynamic cloning, extraction, filtering, and indexing of code repositories."""

    def __init__(
        self,
        vector_store: Optional[Any] = None,
        graph_store: Optional[Any] = None,
        ast_parser: Optional[Any] = None,
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.ast_parser = ast_parser

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
                # Skip ignored directory patterns
                rel_parts = set(path.relative_to(root_path).parts[:-1])
                if rel_parts.intersection(DEFAULT_IGNORE_PATTERNS):
                    continue

                # Skip hidden files and binary formats
                if path.name.startswith(".") or self.is_binary_file(path):
                    continue

                valid_files.append(path)

        return valid_files

    def ingest_git_repo(self, repo_url: str, branch: Optional[str] = None) -> Dict[str, Any]:
        """Clones a remote Git repository into a temporary directory and indexes it."""
        self.log(f"📥 Cloning remote Git repository: {repo_url}")
        temp_dir = tempfile.mkdtemp(prefix="codegraph_git_")

        try:
            clone_cmd = ["git", "clone", "--depth", "1"]
            if branch:
                clone_cmd.extend(["-b", branch])
            clone_cmd.extend([repo_url, temp_dir])

            subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            source_files = self.collect_source_files(temp_dir)
            self.log(f"✅ Found {len(source_files)} source files for indexing.")

            indexing_summary = self._index_files(temp_dir, source_files)
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

    def ingest_zip_archive(self, zip_path: str) -> Dict[str, Any]:
        """Extracts a local ZIP archive safely into a temporary directory and indexes it."""
        if not os.path.exists(zip_path):
            return {"status": "error", "message": f"ZIP file not found at: {zip_path}"}

        self.log(f"📦 Extracting ZIP archive: {zip_path}")
        temp_dir = tempfile.mkdtemp(prefix="codegraph_zip_")

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Zip-Slip protection
                resolved_temp = os.path.realpath(temp_dir)
                for member in zip_ref.namelist():
                    member_path = os.path.realpath(os.path.join(temp_dir, member))
                    if not member_path.startswith(resolved_temp):
                        raise Exception(f"Zip slip security risk detected in entry: {member}")
                
                zip_ref.extractall(temp_dir)

            source_files = self.collect_source_files(temp_dir)
            self.log(f"✅ Found {len(source_files)} source files for indexing.")

            indexing_summary = self._index_files(temp_dir, source_files)
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

    def _index_files(self, base_dir: str, files: List[Path]) -> Dict[str, int]:
        """Processes source files through vector store and graph store pipelines."""
        indexed_vectors = 0
        indexed_graph_nodes = 0
        base_path = Path(base_dir).resolve()

        for idx, file_path in enumerate(files, start=1):
            rel_path = str(file_path.relative_to(base_path))

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue

                # 1. Upsert into Qdrant Vector Store
                if self.vector_store:
                    try:
                        metadata = {
                            "filepath": rel_path,
                            "filename": file_path.name,
                            "extension": file_path.suffix,
                        }
                        if self.vector_store.upsert_code_snippet(
                            doc_id=idx,
                            code_snippet=content,
                            metadata=metadata,
                        ):
                            indexed_vectors += 1
                    except Exception as vec_err:
                        self.log(f"⚠️ Vector store indexing failed for '{rel_path}': {vec_err}")

                # 2. Parse AST & populate Neo4j Graph Store
                if self.graph_store and self.ast_parser:
                    try:
                        ast_data = None
                        # Check if ast_parser is passed as class reference or instance
                        if isinstance(self.ast_parser, type):
                            try:
                                parser_inst = self.ast_parser(str(file_path))
                                if hasattr(parser_inst, "parse"):
                                    ast_data = parser_inst.parse()
                                elif hasattr(parser_inst, "parse_code"):
                                    ast_data = parser_inst.parse_code(content, language=file_path.suffix)
                            except Exception:
                                parser_inst = self.ast_parser()
                                if hasattr(parser_inst, "parse_code"):
                                    ast_data = parser_inst.parse_code(content, language=file_path.suffix)
                        elif hasattr(self.ast_parser, "parse_code"):
                            ast_data = self.ast_parser.parse_code(content, language=file_path.suffix)
                        elif hasattr(self.ast_parser, "parse"):
                            ast_data = self.ast_parser.parse()

                        if ast_data:
                            self.graph_store.build_file_node_graph(rel_path, ast_data)
                            indexed_graph_nodes += 1
                    except Exception as ast_err:
                        self.log(f"⚠️ AST parsing skipped for '{rel_path}': {ast_err}")

            except Exception as file_err:
                self.log(f"⚠️ Skipping file '{rel_path}': {file_err}")

        return {
            "vector_chunks": indexed_vectors,
            "graph_nodes": indexed_graph_nodes,
        }