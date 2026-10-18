import os
import re
import ast
from typing import Dict, List, Any, Optional
from tree_sitter import Language, Parser

import tree_sitter_python as tspython
import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import tree_sitter_cpp as tscpp
import tree_sitter_go as tsgo


def _resolve_language(ts_module) -> Optional[Language]:
    """Safely retrieves a tree-sitter Language object across library versions."""
    if not ts_module:
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


class CodeASTParser:
    """Polyglot AST Parser with error protection and fallback extractors."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        ext = os.path.splitext(filepath)[1].lower()

        lang_info = LANGUAGE_MODULE_MAP.get(ext, ("python", tspython))
        self.language_id = lang_info[0]
        ts_mod = lang_info[1]

        self.language_obj = _resolve_language(ts_mod)

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                self.code_str = f.read()
                self.code_bytes = bytes(self.code_str, "utf-8")
        except Exception as e:
            print(f"⚠️ Could not read source file '{filepath}': {e}")
            self.code_str = ""
            self.code_bytes = b""

        self.tree = None
        if self.language_obj and self.code_bytes:
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
            except Exception:
                self.tree = None

    def extract_structures(self) -> Dict[str, List[Dict[str, Any]]]:
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
                self._traverse_node(self.tree.root_node, mapping, structures)
            except Exception as e:
                print(f"⚠️ Tree-Sitter traversal warning for '{self.filepath}': {e}")

        has_content = (
            len(structures["classes"])
            + len(structures["functions"])
            + len(structures["constants"])
        )
        if has_content == 0 and self.code_str.strip():
            structures = self._fallback_extract()

        return structures

    def _get_node_text(self, node) -> str:
        if not node:
            return ""
        try:
            return self.code_bytes[
                node.start_byte : node.end_byte
            ].decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _get_identifier_name(self, node) -> str:
        if not node or not hasattr(node, "children"):
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
                if name != "unnamed_entity":
                    return name

        return "unnamed_entity"

    def _extract_superclasses(self, node) -> List[str]:
        if not node or not hasattr(node, "children"):
            return []
        superclasses = []
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

    def _collect_calls_in_node(
        self,
        node,
        caller_name: str,
        mapping: Dict[str, List[str]],
        calls_list: List[Dict[str, Any]],
    ):
        if not node or not hasattr(node, "children"):
            return

        for child in node.children:
            if child.type in mapping.get("call", []):
                callee_name = self._get_identifier_name(child)
                if callee_name and callee_name != "unnamed_entity":
                    calls_list.append(
                        {
                            "caller": caller_name,
                            "callee": callee_name,
                            "file": self.filepath,
                        }
                    )
            self._collect_calls_in_node(child, caller_name, mapping, calls_list)

    def _collect_methods(self, node, func_types: List[str]) -> List[Any]:
        if not node or not hasattr(node, "children"):
            return []
        methods = []
        for child in node.children:
            if child.type in func_types:
                methods.append(child)
            elif child.type in [
                "class_body",
                "block",
                "declaration_list",
                "field_declaration_list",
            ]:
                methods.extend(self._collect_methods(child, func_types))
        return methods

    def _traverse_node(
        self,
        node,
        mapping: Dict[str, List[str]],
        structures: Dict[str, List[Dict[str, Any]]],
        parent_class: str = None,
    ):
        if not node:
            return

        node_type = node.type

        if node_type in mapping["class"]:
            class_name = self._get_identifier_name(node)
            superclasses = self._extract_superclasses(node)

            methods = []
            method_nodes = self._collect_methods(node, mapping["function"])
            for m_node in method_nodes:
                method_name = self._get_identifier_name(m_node)
                method_code = self._get_node_text(m_node)
                full_method_name = (
                    f"{class_name}.{method_name}"
                    if class_name != "unnamed_entity"
                    else method_name
                )
                methods.append({"name": method_name, "code": method_code})

                structures["functions"].append(
                    {
                        "type": "method",
                        "name": full_method_name,
                        "short_name": method_name,
                        "code": method_code,
                        "file": self.filepath,
                        "docstring": f"Class: {class_name} | Language: {self.language_id}",
                    }
                )

                self._collect_calls_in_node(
                    m_node, full_method_name, mapping, structures["calls"]
                )

            structures["classes"].append(
                {
                    "name": class_name,
                    "extends": superclasses,
                    "docstring": f"Language: {self.language_id} class declaration",
                    "methods": methods,
                    "file": self.filepath,
                }
            )

            for child in node.children:
                self._traverse_node(
                    child, mapping, structures, parent_class=class_name
                )
            return

        elif node_type in mapping["function"] and not parent_class:
            func_name = self._get_identifier_name(node)
            func_code = self._get_node_text(node)

            structures["functions"].append(
                {
                    "type": "function",
                    "name": func_name,
                    "short_name": func_name,
                    "code": func_code,
                    "file": self.filepath,
                    "docstring": f"Language: {self.language_id} function",
                }
            )

            self._collect_calls_in_node(
                node, func_name, mapping, structures["calls"]
            )

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

        elif node_type in mapping["import"]:
            import_code = self._get_node_text(node)
            structures["imports"].append(
                {"code": import_code, "file": self.filepath}
            )

        for child in getattr(node, "children", []):
            if child.type not in mapping["class"]:
                self._traverse_node(child, mapping, structures, parent_class)

    def _fallback_extract(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fallback extractor using Python ast or Regex pattern matching."""
        structures: Dict[str, List[Dict[str, Any]]] = {
            "classes": [],
            "functions": [],
            "constants": [],
            "imports": [],
            "calls": [],
        }
        ext = os.path.splitext(self.filepath)[1].lower()

        if ext == ".py":
            try:
                tree = ast.parse(self.code_str)
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        bases = [
                            b.id for b in node.bases if isinstance(b, ast.Name)
                        ]
                        methods = []
                        for sub in node.body:
                            if isinstance(
                                sub, (ast.FunctionDef, ast.AsyncFunctionDef)
                            ):
                                m_code = (
                                    ast.get_source_segment(self.code_str, sub)
                                    or f"def {sub.name}(...)"
                                )
                                full_m_name = f"{node.name}.{sub.name}"
                                methods.append(
                                    {"name": sub.name, "code": m_code}
                                )
                                structures["functions"].append(
                                    {
                                        "type": "method",
                                        "name": full_m_name,
                                        "short_name": sub.name,
                                        "code": m_code,
                                        "file": self.filepath,
                                        "docstring": ast.get_docstring(sub)
                                        or "",
                                    }
                                )

                                for sub_node in ast.walk(sub):
                                    if isinstance(sub_node, ast.Call):
                                        if isinstance(
                                            sub_node.func, ast.Name
                                        ):
                                            structures["calls"].append(
                                                {
                                                    "caller": full_m_name,
                                                    "callee": sub_node.func.id,
                                                    "file": self.filepath,
                                                }
                                            )
                                        elif isinstance(
                                            sub_node.func, ast.Attribute
                                        ):
                                            structures["calls"].append(
                                                {
                                                    "caller": full_m_name,
                                                    "callee": sub_node.func.attr,
                                                    "file": self.filepath,
                                                }
                                            )

                        structures["classes"].append(
                            {
                                "name": node.name,
                                "extends": bases,
                                "docstring": ast.get_docstring(node) or "",
                                "methods": methods,
                                "file": self.filepath,
                            }
                        )
                    elif isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
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
                                if isinstance(sub_node.func, ast.Name):
                                    structures["calls"].append(
                                        {
                                            "caller": node.name,
                                            "callee": sub_node.func.id,
                                            "file": self.filepath,
                                        }
                                    )
                                elif isinstance(sub_node.func, ast.Attribute):
                                    structures["calls"].append(
                                        {
                                            "caller": node.name,
                                            "callee": sub_node.func.attr,
                                            "file": self.filepath,
                                        }
                                    )

                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                c_code = (
                                    ast.get_source_segment(self.code_str, node)
                                    or f"{target.id} = ..."
                                )
                                structures["constants"].append(
                                    {
                                        "type": "constant",
                                        "name": target.id,
                                        "code": c_code,
                                        "file": self.filepath,
                                        "docstring": f"Constant in {self.filepath}",
                                    }
                                )
                return structures
            except Exception:
                pass

        try:
            class_matches = re.findall(
                r"(?:public\s+|private\s+|protected\s+)?class\s+([A-Za-z0-9_]+)(?:\s+extends\s+([A-Za-z0-9_]+))?",
                self.code_str,
            )
            for match in class_matches:
                c_name = match[0]
                extends_list = [match[1]] if len(match) > 1 and match[1] else []
                structures["classes"].append(
                    {
                        "name": c_name,
                        "extends": extends_list,
                        "docstring": f"Class {c_name} in {self.filepath}",
                        "methods": [],
                        "file": self.filepath,
                    }
                )

            func_matches = re.findall(
                r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{",
                self.code_str,
            )
            for f_name in func_matches:
                if f_name not in ["if", "for", "while", "switch"]:
                    structures["functions"].append(
                        {
                            "type": "function",
                            "name": f_name,
                            "short_name": f_name,
                            "code": f"// Definition of {f_name} in {self.filepath}\n{self.code_str}",
                            "file": self.filepath,
                            "docstring": f"Function/Method {f_name} in {self.filepath}",
                        }
                    )
        except Exception as e:
            print(f"⚠️ Regex fallback error for '{self.filepath}': {e}")

        return structures