import ast
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Modern Tree-Sitter Language Bindings
try:
    from tree_sitter import Language, Parser
    import tree_sitter_cpp as tscpp
    import tree_sitter_go as tsgo
    import tree_sitter_java as tsjava
    import tree_sitter_javascript as tsjs
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tsts
except ImportError:
    Language, Parser = None, None
    tscpp, tsgo, tsjava, tsjs, tspython, tsts = None, None, None, None, None, None


def _resolve_language(ts_module) -> Optional[Any]:
    """Safely retrieves a tree-sitter Language object across library versions."""
    if not ts_module or not Language:
        return None
    try:
        lang_func = getattr(ts_module, "language", None)
        if not lang_func:
            return None
        lang_val = lang_func()
        if isinstance(lang_val, Language):
            return lang_val
        return Language(lang_val)
    except Exception:
        return None


LANGUAGE_MODULE_MAP = {
    ".py": ("python", tspython),
    ".java": ("java", tsjava),
    ".js": ("javascript", tsjs),
    ".jsx": ("javascript", tsjs),
    ".ts": ("typescript", tsts),
    ".tsx": ("typescript", tsts),
    ".cpp": ("cpp", tscpp),
    ".hpp": ("cpp", tscpp),
    ".c": ("cpp", tscpp),
    ".h": ("cpp", tscpp),
    ".go": ("go", tsgo),
}

NODE_TYPE_MAPPINGS = {
    "python": {
        "class": ["class_definition"],
        "function": ["function_definition", "async_function_definition"],
        "constant": ["assignment"],
        "import": ["import_statement", "import_from_statement"],
        "call": ["call"],
    },
    "java": {
        "class": ["class_declaration", "interface_declaration", "enum_declaration"],
        "function": ["method_declaration", "constructor_declaration"],
        "constant": ["field_declaration"],
        "import": ["import_declaration"],
        "call": ["method_invocation"],
    },
    "javascript": {
        "class": ["class_declaration"],
        "function": ["function_declaration", "method_definition", "arrow_function"],
        "constant": ["lexical_declaration", "variable_declaration"],
        "import": ["import_statement"],
        "call": ["call_expression"],
    },
    "typescript": {
        "class": ["class_declaration", "interface_declaration"],
        "function": ["function_declaration", "method_definition", "arrow_function"],
        "constant": ["lexical_declaration", "variable_declaration"],
        "import": ["import_statement"],
        "call": ["call_expression"],
    },
    "cpp": {
        "class": ["class_specifier", "struct_specifier"],
        "function": ["function_definition"],
        "constant": ["declaration"],
        "import": ["preproc_include"],
        "call": ["call_expression"],
    },
    "go": {
        "class": ["type_spec"],
        "function": ["function_declaration", "method_declaration"],
        "constant": ["const_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
    },
}

ROOT_NODE_TYPES = {
    "program",
    "module",
    "compilation_unit",
    "translation_unit",
    "source_file",
}


def _is_valid_name(name: str) -> bool:
    """Helper to check if a symbol name is non-empty and not an unnamed default."""
    return bool(name) and name != "unnamed_entity"


class CodeASTParser:
    """Polyglot AST Parser with error protection, scope-aware call graph extraction, and stdio safety."""

    def __init__(self, filepath: str, code_str: Optional[str] = None):
        self.filepath = filepath
        ext = os.path.splitext(filepath)[1].lower()
        lang_info = LANGUAGE_MODULE_MAP.get(ext, ("python", tspython))
        self.language_id = lang_info[0]
        ts_mod = lang_info[1]
        self.language_obj = _resolve_language(ts_mod)

        if code_str is not None:
            self.code_str = code_str
        else:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    self.code_str = f.read()
            except Exception as e:
                self.log(f"⚠️ Could not read source file '{filepath}': {e}")
                self.code_str = ""

        self.code_bytes = self.code_str.encode("utf-8")
        self.tree = None

        if Parser and self.language_obj and self.code_bytes:
            try:
                try:
                    parser = Parser(self.language_obj)
                except Exception:
                    parser = Parser()
                    if hasattr(parser, "language"):
                        parser.language = self.language_obj
                    elif hasattr(parser, "set_language"):
                        parser.set_language(self.language_obj)
                self.tree = parser.parse(self.code_bytes)
            except Exception as e:
                self.log(f"⚠️ Tree-sitter parsing error for '{filepath}': {e}")
                self.tree = None

    def log(self, message: str) -> None:
        """Logs status messages strictly to sys.stderr to preserve stdio JSON-RPC transport."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def extract_structures(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extracts classes, functions, constants, imports, and method calls from AST."""
        structures: Dict[str, List[Dict[str, Any]]] = {
            "classes": [],
            "functions": [],
            "constants": [],
            "imports": [],
            "calls": [],
        }

        if self.tree and self.tree.root_node:
            try:
                mapping = NODE_TYPE_MAPPINGS.get(
                    self.language_id, NODE_TYPE_MAPPINGS["python"]
                )
                self._traverse_node(
                    self.tree.root_node, mapping, structures, current_class="", current_func=""
                )
            except Exception as e:
                self.log(f"⚠️ Tree-Sitter traversal warning for '{self.filepath}': {e}")

        total_extracted = sum(len(v) for v in structures.values())
        if total_extracted == 0 and self.code_str.strip():
            structures = self._fallback_extract()

        structures["calls"] = self._deduplicate_calls(structures["calls"])
        return structures

    def parse(self) -> Dict[str, List[Dict[str, Any]]]:
        """Alias for extract_structures() for backward compatibility."""
        return self.extract_structures()

    def parse_file(self, filepath: str, code_str: str) -> Dict[str, List[Dict[str, Any]]]:
        """Helper to re-parse a specific file path and content."""
        self.__init__(filepath, code_str=code_str)
        return self.extract_structures()

    def _get_node_text(self, node) -> str:
        """Helper to extract string content of an AST node."""
        if not node:
            return ""
        try:
            return self.code_bytes[node.start_byte : node.end_byte].decode(
                "utf-8", errors="ignore"
            )
        except Exception:
            return ""

    def _get_identifier_name(self, node) -> str:
        """Extracts symbol identifier using named fields first, falling back to child nodes."""
        if not node:
            return "unnamed_entity"

        if hasattr(node, "child_by_field_name"):
            name_node = node.child_by_field_name("name") or node.child_by_field_name("declarator")
            if name_node:
                text = self._get_node_text(name_node).strip()
                if text and not text.startswith("("):
                    return text

        if not hasattr(node, "children"):
            return "unnamed_entity"

        for child in node.children:
            if child.type in [
                "identifier",
                "property_identifier",
                "type_identifier",
                "name",
                "field_identifier",
            ]:
                text = self._get_node_text(child).strip()
                if text:
                    return text

        for child in node.children:
            if child.type in [
                "declarator",
                "init_declarator",
                "function_declarator",
                "variable_declarator",
            ]:
                name = self._get_identifier_name(child)
                if _is_valid_name(name):
                    return name

        return "unnamed_entity"

    def _get_callee_name(self, node) -> str:
        """Extracts the invoked method/function name from call expression nodes."""
        if not node:
            return "unnamed_entity"

        if hasattr(node, "child_by_field_name"):
            name_node = node.child_by_field_name("name")
            if name_node:
                return self._get_node_text(name_node).strip()

            func_node = node.child_by_field_name("function")
            if func_node:
                if func_node.type in ("attribute", "member_expression"):
                    attr_node = func_node.child_by_field_name(
                        "attribute"
                    ) or func_node.child_by_field_name("property")
                    if attr_node:
                        return self._get_node_text(attr_node).strip()

                full_text = self._get_node_text(func_node).strip()
                if "." in full_text:
                    return full_text.split(".")[-1].strip()
                return full_text

        for child in getattr(node, "children", []):
            if child.type in ("identifier", "property_identifier", "field_identifier"):
                return self._get_node_text(child).strip()

        return "unnamed_entity"

    def _extract_superclasses(self, node) -> List[str]:
        """Extracts extended classes or implemented interfaces."""
        if not node or not hasattr(node, "children"):
            return []
        superclasses = []

        if hasattr(node, "child_by_field_name"):
            heritage = node.child_by_field_name("superclasses") or node.child_by_field_name("heritage")
            if heritage:
                text = self._get_node_text(heritage).strip()
                if text:
                    return [text]

        for child in node.children:
            if child.type in [
                "argument_list",
                "superclass",
                "super_interfaces",
                "extends_clause",
                "class_heritage",
            ]:
                for sub in child.children:
                    if sub.type in [
                        "identifier",
                        "type_identifier",
                        "scoped_type_identifier",
                    ]:
                        text = self._get_node_text(sub).strip()
                        if text and text not in superclasses:
                            superclasses.append(text)
        return superclasses

    def _traverse_node(
        self,
        node,
        mapping: Dict[str, List[str]],
        structures: Dict[str, List[Dict[str, Any]]],
        current_class: str = "",
        current_func: str = "",
        inside_class: bool = False,
    ) -> None:
        """Traverses AST nodes while preserving enclosing class and function scopes."""
        if not node:
            return

        node_type = node.type

        # 1. Class / Struct / Interface Declaration
        if node_type in mapping["class"]:
            class_name = self._get_identifier_name(node)
            superclasses = self._extract_superclasses(node)

            structures["classes"].append(
                {
                    "name": class_name,
                    "extends": superclasses,
                    "docstring": f"Language: {self.language_id} class declaration",
                    "file": self.filepath,
                }
            )

            for child in getattr(node, "children", []):
                self._traverse_node(
                    child,
                    mapping,
                    structures,
                    current_class=class_name,
                    current_func=current_func,
                    inside_class=True,
                )
            return

        # 2. Function / Method Declaration
        elif node_type in mapping["function"]:
            func_name = self._get_identifier_name(node)
            func_code = self._get_node_text(node)
            full_func_name = (
                f"{current_class}.{func_name}" if _is_valid_name(current_class) else func_name
            )
            fn_type = "method" if inside_class else "function"
            doc_str = (
                f"Class: {current_class} | Language: {self.language_id}"
                if inside_class
                else f"Language: {self.language_id} function"
            )

            structures["functions"].append(
                {
                    "type": fn_type,
                    "name": full_func_name,
                    "short_name": func_name,
                    "code": func_code,
                    "file": self.filepath,
                    "docstring": doc_str,
                }
            )

            for child in getattr(node, "children", []):
                self._traverse_node(
                    child,
                    mapping,
                    structures,
                    current_class=current_class,
                    current_func=full_func_name,
                    inside_class=inside_class,
                )
            return

        # 3. Function / Method Invocations
        elif node_type in mapping["call"]:
            callee_name = self._get_callee_name(node)
            if _is_valid_name(callee_name):
                caller_name = current_func if current_func else "unnamed_entity"
                structures["calls"].append(
                    {
                        "caller": caller_name,
                        "callee": callee_name,
                        "file": self.filepath,
                    }
                )

        # 4. Global Constants
        elif (
            node_type in mapping["constant"]
            and node.parent
            and node.parent.type in ROOT_NODE_TYPES
        ):
            const_code = self._get_node_text(node)
            const_name = self._get_identifier_name(node)
            structures["constants"].append(
                {
                    "type": "constant",
                    "name": const_name,
                    "code": f"# [{self.language_id.upper()}] Constant in {self.filepath}\n{const_code}",
                    "file": self.filepath,
                    "docstring": f"Global definition '{const_name}' in {self.filepath}",
                }
            )

        # 5. Import Statements
        elif node_type in mapping["import"]:
            import_code = self._get_node_text(node)
            structures["imports"].append({"code": import_code, "file": self.filepath})

        # Recurse children for non-class/non-function nodes
        for child in getattr(node, "children", []):
            self._traverse_node(
                child, mapping, structures, current_class, current_func, inside_class
            )

    def _deduplicate_calls(
        self, calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Deduplicates function/method call records."""
        seen: Set[Tuple[str, str, str]] = set()
        deduped = []
        for c in calls:
            key = (c["caller"], c["callee"], c["file"])
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        return deduped

    def _fallback_extract(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fallback extractor using Python standard library `ast` or Regex pattern matching."""
        structures: Dict[str, List[Dict[str, Any]]] = {
            "classes": [],
            "functions": [],
            "constants": [],
            "imports": [],
            "calls": [],
        }

        ext = os.path.splitext(self.filepath)[1].lower()

        # Python Standard Library AST Fallback
        if ext == ".py":
            try:
                tree = ast.parse(self.code_str)
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                        structures["classes"].append(
                            {
                                "name": node.name,
                                "extends": bases,
                                "docstring": ast.get_docstring(node) or "",
                                "file": self.filepath,
                            }
                        )
                        for sub in node.body:
                            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                m_code = (
                                    ast.get_source_segment(self.code_str, sub)
                                    or f"def {sub.name}(...)"
                                )
                                full_m_name = f"{node.name}.{sub.name}"
                                structures["functions"].append(
                                    {
                                        "type": "method",
                                        "name": full_m_name,
                                        "short_name": sub.name,
                                        "code": m_code,
                                        "file": self.filepath,
                                        "docstring": ast.get_docstring(sub) or "",
                                    }
                                )
                                for sub_node in ast.walk(sub):
                                    if isinstance(sub_node, ast.Call):
                                        callee = ""
                                        if isinstance(sub_node.func, ast.Name):
                                            callee = sub_node.func.id
                                        elif isinstance(sub_node.func, ast.Attribute):
                                            callee = sub_node.func.attr
                                        if callee:
                                            structures["calls"].append(
                                                {
                                                    "caller": full_m_name,
                                                    "callee": callee,
                                                    "file": self.filepath,
                                                }
                                            )
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        f_code = (
                            ast.get_source_segment(self.code_str, node)
                            or f"def {node.name}(...)"
                        )
                        structures["functions"].append(
                            {
                                "type": "function",
                                "name": node.name,
                                "short_name": node.name,
                                "code": f_code,
                                "file": self.filepath,
                                "docstring": ast.get_docstring(node) or "",
                            }
                        )
                        for sub_node in ast.walk(node):
                            if isinstance(sub_node, ast.Call):
                                callee = ""
                                if isinstance(sub_node.func, ast.Name):
                                    callee = sub_node.func.id
                                elif isinstance(sub_node.func, ast.Attribute):
                                    callee = sub_node.func.attr
                                if callee:
                                    structures["calls"].append(
                                        {
                                            "caller": node.name,
                                            "callee": callee,
                                            "file": self.filepath,
                                        }
                                    )
                return structures
            except Exception as e:
                self.log(f"⚠️ Python AST fallback error for '{self.filepath}': {e}")

        # Regex Fallback for Non-Python Files or Malformed Syntax
        try:
            class_matches = re.findall(
                r"(?:public\s+|private\s+|protected\s+)?(?:class|interface|enum)\s+([A-Za-z0-9_]+)(?:\s+extends\s+([A-Za-z0-9_]+))?",
                self.code_str,
            )
            for match in class_matches:
                c_name = match[0]
                extends_list = [match[1]] if len(match) > 1 and match[1] else []
                structures["classes"].append(
                    {
                        "name": c_name,
                        "extends": extends_list,
                        "docstring": f"Class/Interface {c_name} in {self.filepath}",
                        "file": self.filepath,
                    }
                )

            func_matches = re.finditer(
                r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{",
                self.code_str,
            )
            for m in func_matches:
                f_name = m.group(1)
                if f_name not in ["if", "for", "while", "switch", "catch"]:
                    start_pos = max(0, m.start() - 20)
                    snippet = self.code_str[start_pos : start_pos + 150]
                    structures["functions"].append(
                        {
                            "type": "function",
                            "name": f_name,
                            "short_name": f_name,
                            "code": f"// Definition snippet of {f_name}\n{snippet}...",
                            "file": self.filepath,
                            "docstring": f"Function/Method {f_name} in {self.filepath}",
                        }
                    )
        except Exception as e:
            self.log(f"⚠️ Regex fallback error for '{self.filepath}': {e}")

        return structures