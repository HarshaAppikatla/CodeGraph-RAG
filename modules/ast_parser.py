import ast
from typing import List, Dict, Any

class CodeASTParser:
    """Parses Python source code into structural nodes for graph and vector indexing."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        with open(filepath, "r", encoding="utf-8") as f:
            self.source_code = f.read()
        self.tree = ast.parse(self.source_code)

    def extract_structures(self) -> Dict[str, Any]:
        """Extracts top-level classes, functions, and imports."""
        structures = {
            "classes": [],
            "functions": [],
            "imports": []
        }

        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                structures["classes"].append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                    "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                })

            elif isinstance(node, ast.FunctionDef):
                structures["functions"].append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                    "args": [arg.arg for arg in node.args.args]
                })

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    structures["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                structures["imports"].append(f"{node.module}")

        return structures