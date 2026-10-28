import logging
from typing import Dict, List, Any, Optional
from tree_sitter import Language, Parser

logger = logging.getLogger("codegraph.validator")

# Supported tree-sitter language bindings
LANGUAGES: Dict[str, Any] = {}

try:
    import tree_sitter_java as tsjava
    LANGUAGES["java"] = Language(tsjava.language())
except Exception as e:
    logger.debug(f"Java tree-sitter unavailable: {e}")

try:
    import tree_sitter_python as tspython
    LANGUAGES["py"] = Language(tspython.language())
    LANGUAGES["python"] = LANGUAGES["py"]
except Exception as e:
    logger.debug(f"Python tree-sitter unavailable: {e}")

try:
    import tree_sitter_javascript as tsjs
    LANGUAGES["js"] = Language(tsjs.language())
    LANGUAGES["javascript"] = LANGUAGES["js"]
except Exception as e:
    logger.debug(f"JavaScript tree-sitter unavailable: {e}")

try:
    import tree_sitter_typescript as tsts
    LANGUAGES["ts"] = Language(tsts.language_typescript())
    LANGUAGES["tsx"] = Language(tsts.language_tsx())
    LANGUAGES["typescript"] = LANGUAGES["ts"]
except Exception as e:
    logger.debug(f"TypeScript tree-sitter unavailable: {e}")

try:
    import tree_sitter_go as tsgo
    LANGUAGES["go"] = Language(tsgo.language())
except Exception as e:
    logger.debug(f"Go tree-sitter unavailable: {e}")

try:
    import tree_sitter_cpp as tscpp
    LANGUAGES["cpp"] = Language(tscpp.language())
    LANGUAGES["c"] = LANGUAGES["cpp"]
except Exception as e:
    logger.debug(f"C/C++ tree-sitter unavailable: {e}")


def get_language_from_filename(filename: str) -> Optional[str]:
    """Maps a filename extension to the registered tree-sitter language identifier."""
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    ext_map = {
        "java": "java",
        "py": "py",
        "python": "py",
        "js": "js",
        "jsx": "js",
        "mjs": "js",
        "cjs": "js",
        "ts": "ts",
        "tsx": "tsx",
        "go": "go",
        "cpp": "cpp",
        "hpp": "cpp",
        "c": "c",
        "h": "cpp",
        "cc": "cpp",
    }
    return ext_map.get(ext)


def collect_ast_errors(node, code_bytes: bytes, errors: List[Dict[str, Any]], seen_positions: set):
    """Recursively collects ERROR and MISSING nodes from the tree-sitter AST."""
    if node.is_error or node.is_missing or node.type == "ERROR":
        sp = node.start_point
        ep = node.end_point
        start_row = getattr(sp, "row", sp[0])
        start_col = getattr(sp, "column", sp[1])
        end_row = getattr(ep, "row", ep[0])
        end_col = getattr(ep, "column", ep[1])

        pos_key = (start_row, start_col, end_row, end_col)
        if pos_key not in seen_positions:
            seen_positions.add(pos_key)
            snippet = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore").strip()

            errors.append({
                "type": "MISSING_CONSTRUCT" if node.is_missing else "SYNTAX_ERROR",
                "line": start_row + 1,
                "column": start_col,
                "end_line": end_row + 1,
                "end_column": end_col,
                "symbol": node.type,
                "snippet": snippet or "<missing construct>"
            })

    for child in node.children:
        collect_ast_errors(child, code_bytes, errors, seen_positions)


def validate_code_syntax(filename: str, code_content: str) -> Dict[str, Any]:
    """Validates proposed code snippet against the polyglot tree-sitter parser."""
    if not code_content or not code_content.strip():
        return {
            "is_valid": True,
            "skipped": False,
            "errors": [],
            "message": "Empty code snippet provided."
        }

    lang_key = get_language_from_filename(filename)
    if not lang_key or lang_key not in LANGUAGES:
        return {
            "is_valid": True,
            "skipped": True,
            "errors": [],
            "message": f"Unsupported or skipped language extension for '{filename}'"
        }

    language = LANGUAGES[lang_key]
    try:
        parser = Parser(language)
    except Exception as e:
        return {
            "is_valid": True,
            "skipped": True,
            "errors": [],
            "message": f"Parser initialization failed: {e}"
        }

    code_bytes = code_content.encode("utf-8")
    tree = parser.parse(code_bytes)
    root_node = tree.root_node

    if not root_node.has_error:
        return {
            "is_valid": True,
            "skipped": False,
            "errors": []
        }

    errors: List[Dict[str, Any]] = []
    seen_positions = set()
    collect_ast_errors(root_node, code_bytes, errors, seen_positions)

    return {
        "is_valid": False,
        "skipped": False,
        "errors": errors
    }
