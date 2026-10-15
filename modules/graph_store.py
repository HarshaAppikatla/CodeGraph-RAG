from neo4j import GraphDatabase
from typing import Dict, Any, List

class Neo4jGraphStore:
    """Handles connection and node/relationship creation in Neo4j for AST structures."""

    def __init__(self, uri: str, user: str, passw: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, passw))

    def close(self):
        if self.driver:
            self.driver.close()

    def ingest_ast(self, filepath: str, ast_data: Dict[str, Any]):
        """Creates File, Class, Function, and Constant nodes with edges in Neo4j."""
        with self.driver.session() as session:
            # 1. Merge File Node
            session.run(
                "MERGE (f:File {path: $path})",
                path=filepath
            )

            # 2. Ingest Functions & Methods
            for fn in ast_data.get("functions", []):
                fn_name = fn.get("name", "unknown")
                session.run(
                    """
                    MATCH (f:File {path: $file_path})
                    MERGE (fn:Function {name: $fn_name, file: $file_path})
                    MERGE (f)-[:DEFINES_FUNCTION]->(fn)
                    """,
                    file_path=filepath,
                    fn_name=fn_name
                )

            # 3. Ingest Classes
            for cls in ast_data.get("classes", []):
                cls_name = cls.get("name", "unknown")
                
                # Extract clean list of string method names for Neo4j primitive array compatibility
                raw_methods = cls.get("methods", [])
                method_names = []
                for m in raw_methods:
                    if isinstance(m, dict):
                        method_names.append(m.get("name", "unknown"))
                    else:
                        method_names.append(str(m))

                session.run(
                    """
                    MATCH (f:File {path: $file_path})
                    MERGE (c:Class {name: $cls_name, file: $file_path})
                    SET c.methods = $methods, c.docstring = $docstring
                    MERGE (f)-[:CONTAINS_CLASS]->(c)
                    """,
                    file_path=filepath,
                    cls_name=cls_name,
                    methods=method_names,
                    docstring=cls.get("docstring", "")
                )

            # 4. Ingest Global Constants
            for const in ast_data.get("constants", []):
                const_name = const.get("name", "unknown")
                session.run(
                    """
                    MATCH (f:File {path: $file_path})
                    MERGE (k:Constant {name: $const_name, file: $file_path})
                    MERGE (f)-[:DEFINES_CONSTANT]->(k)
                    """,
                    file_path=filepath,
                    const_name=const_name
                )