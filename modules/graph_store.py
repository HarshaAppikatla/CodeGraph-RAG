from neo4j import GraphDatabase
from typing import Dict, Any

class Neo4jGraphStore:
    """Handles connection and node/relationship creation in Neo4j for AST structures."""

    def __init__(self, uri: str, user: str, passw: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, passw))

    def close(self):
        self.driver.close()

    def ingest_ast(self, filepath: str, ast_data: Dict[str, Any]):
        """Creates File, Class, and Function nodes and connects them with relationships."""
        with self.driver.session() as session:
            session.execute_write(self._create_graph, filepath, ast_data)

    @staticmethod
    def _create_graph(tx, filepath: str, ast_data: Dict[str, Any]):
        # 1. Create File Node
        query_file = "MERGE (f:File {path: $filepath})"
        tx.run(query_file, filepath=filepath)

        # 2. Create Class Nodes & CONTAINS_CLASS relationships
        for cls in ast_data.get("classes", []):
            query_class = """
            MERGE (c:Class {name: $class_name, file: $filepath})
            ON CREATE SET c.docstring = $docstring
            WITH c
            MATCH (f:File {path: $filepath})
            MERGE (f)-[:CONTAINS_CLASS]->(c)
            """
            tx.run(query_class, class_name=cls["name"], filepath=filepath, docstring=cls["docstring"])

            # Connect methods inside class
            for method in cls.get("methods", []):
                query_method = """
                MATCH (c:Class {name: $class_name, file: $filepath})
                MERGE (m:Function {name: $method_name, file: $filepath})
                MERGE (c)-[:HAS_METHOD]->(m)
                """
                tx.run(query_method, class_name=cls["name"], method_name=method, filepath=filepath)

        # 3. Create Standalone Function Nodes
        for fn in ast_data.get("functions", []):
            query_fn = """
            MERGE (fn:Function {name: $fn_name, file: $filepath})
            ON CREATE SET fn.args = $args, fn.docstring = $docstring
            WITH fn
            MATCH (f:File {path: $filepath})
            MERGE (f)-[:DEFINES_FUNCTION]->(fn)
            """
            tx.run(query_fn, fn_name=fn["name"], filepath=filepath, args=fn["args"], docstring=fn["docstring"])