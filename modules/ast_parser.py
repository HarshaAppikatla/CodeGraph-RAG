import ast
from typing import Dict, List, Any

class CodeASTParser:
    """Parses Python source code into structured AST metadata dictionary."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        with open(filepath, "r", encoding="utf-8") as f:
            self.code = f.read()
        self.tree = ast.parse(self.code)

    def extract_structures(self) -> Dict[str, List[Dict[str, Any]]]:
        structures: Dict[str, List[Dict[str, Any]]] = {
            "classes": [],
            "functions": [],
            "constants": [],
            "imports": []
        }

        for node in ast.iter_child_nodes(self.tree):
            # 1. Global Constants (e.g. FALLBACK_MODELS)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        var_code = ast.get_source_segment(self.code, node) or ""
                        structures["constants"].append({
                            "type": "constant",
                            "name": var_name,
                            "code": f"# Global Constant in {self.filepath}\n{var_code}",
                            "file": self.filepath,
                            "docstring": f"Global variable/constant '{var_name}' defined in {self.filepath}"
                        })

            # 2. Standalone Functions
            elif isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node) or ""
                func_code = ast.get_source_segment(self.code, node) or ""
                structures["functions"].append({
                    "type": "function",
                    "name": node.name,
                    "code": func_code,
                    "file": self.filepath,
                    "docstring": docstring
                })

            # 3. Classes and Class Methods
            elif isinstance(node, ast.ClassDef):
                class_doc = ast.get_docstring(node) or ""
                class_methods = []
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        method_doc = ast.get_docstring(child) or ""
                        method_code = ast.get_source_segment(self.code, child) or ""
                        method_dict = {
                            "type": "method",
                            "name": child.name,
                            "code": method_code,
                            "file": self.filepath,
                            "docstring": method_doc or class_doc
                        }
                        class_methods.append(method_dict)
                        
                        # Add method to functions array for vector search
                        structures["functions"].append({
                            "type": "method",
                            "name": f"{node.name}.{child.name}",
                            "code": method_code,
                            "file": self.filepath,
                            "docstring": f"Class: {node.name} | Doc: {method_doc or class_doc}"
                        })

                structures["classes"].append({
                    "name": node.name,
                    "docstring": class_doc,
                    "methods": class_methods,
                    "file": self.filepath
                })

            # 4. Imports
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_code = ast.get_source_segment(self.code, node) or ""
                structures["imports"].append({
                    "code": import_code,
                    "file": self.filepath
                })

        return structures