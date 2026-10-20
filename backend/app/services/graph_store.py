import os
import sys
import atexit
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Driver
from backend.app.config import settings


class Neo4jGraphStore:
    """Manages property graph storage in Neo4j, modeling code entities and dependencies."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USERNAME
        self.password = password or settings.NEO4J_PASSWORD
        self.driver: Optional[Driver] = None
        self._connect()
        atexit.register(self.close)

    def log(self, message: str) -> None:
        """Logs messages to sys.stderr to preserve stdout for MCP JSON-RPC protocol messages."""
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()

    def _connect(self) -> None:
        """Establishes Neo4j connection and bootstraps constraints."""
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            self.log("✅ Connected to Neo4j Graph Database.")
            self._bootstrap_schema()
        except Exception as e:
            self.log(f"⚠️ Neo4j Connection Notice: {e}")
            self.driver = None

    def _bootstrap_schema(self) -> None:
        """Sets up uniqueness constraints to accelerate graph lookups and prevent duplicate nodes."""
        if not self.driver:
            return

        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.name IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (fn:Function) REQUIRE fn.name IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Import) REQUIRE i.code IS UNIQUE;",
        ]

        try:
            with self.driver.session() as session:
                for query in constraints:
                    try:
                        session.run(query)
                    except Exception:
                        pass
        except Exception as e:
            self.log(f"⚠️ Schema bootstrapping notice: {e}")

    def close(self) -> None:
        """Safely closes the Neo4j driver connection on process exit."""
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass

    def ingest_ast(self, filepath: str, ast_data: Dict[str, Any]) -> None:
        """Ingests file AST structures into Neo4j in batch transactions for maximum throughput."""
        if not self.driver or not ast_data:
            return

        # 1. Prepare Classes payload
        classes_payload = []
        for cls in ast_data.get("classes", []):
            c_name = cls.get("name") or "AnonClass"
            if c_name == "unnamed_entity":
                c_name = f"AnonClass_{os.path.basename(filepath)}"
            parents = [
                p for p in cls.get("extends", [])
                if p and p != "unnamed_entity"
            ]
            classes_payload.append({"name": c_name, "extends": parents})

        # 2. Prepare Functions / Methods payload
        functions_payload = []
        for fn in ast_data.get("functions", []):
            full_name = fn.get("name")
            if not full_name or full_name == "unnamed_entity":
                full_name = f"anon_func_{os.path.basename(filepath)}_L{fn.get('line', 0)}"

            short_name = fn.get("short_name", full_name)
            is_anon = "anon_" in full_name or "lambda_" in full_name
            fn_type = fn.get("type", "function")

            class_name = None
            if fn_type == "method" and "." in full_name:
                class_name = full_name.split(".")[0]

            functions_payload.append({
                "full_name": full_name,
                "short_name": short_name,
                "type": fn_type,
                "is_anon": is_anon,
                "class_name": class_name,
            })

        # 3. Prepare Calls payload
        calls_payload = [
            {"caller": c["caller"], "callee": c["callee"]}
            for c in ast_data.get("calls", [])
            if c.get("caller") and c.get("callee")
        ]

        # 4. Prepare Imports payload
        imports_payload = [
            i.get("code", "").strip()
            for i in ast_data.get("imports", [])
            if i.get("code") and i.get("code").strip()
        ]

        # Cypher Transactions
        cypher_file_imports = """
        MERGE (f:File {path: $filepath})
        SET f.updated_at = timestamp()
        WITH f
        UNWIND $imports AS imp_code
        MERGE (imp:Import {code: imp_code})
        MERGE (f)-[:IMPORTS]->(imp)
        """

        cypher_classes = """
        MATCH (f:File {path: $filepath})
        UNWIND $classes AS cls
        MERGE (c:Class {name: cls.name})
        MERGE (f)-[:CONTAINS_CLASS]->(c)
        WITH c, cls
        UNWIND cls.extends AS parent
        MERGE (super:Class {name: parent})
        MERGE (c)-[:EXTENDS]->(super)
        """

        cypher_functions = """
        MATCH (f:File {path: $filepath})
        UNWIND $functions AS fn
        MERGE (func:Function {name: fn.full_name})
        SET func.short_name = fn.short_name,
            func.type = fn.type,
            func.file = $filepath,
            func.is_anonymous = fn.is_anon
        MERGE (f)-[:CONTAINS_FUNCTION]->(func)
        WITH func, fn
        WHERE fn.class_name IS NOT NULL
        MERGE (c:Class {name: fn.class_name})
        MERGE (c)-[:HAS_METHOD]->(func)
        """

        cypher_calls = """
        UNWIND $calls AS call
        MERGE (caller:Function {name: call.caller})
        MERGE (callee:Function {name: call.callee})
        MERGE (caller)-[:CALLS]->(callee)
        """

        try:
            with self.driver.session() as session:
                session.run(cypher_file_imports, filepath=filepath, imports=imports_payload)
                if classes_payload:
                    session.run(cypher_classes, filepath=filepath, classes=classes_payload)
                if functions_payload:
                    session.run(cypher_functions, filepath=filepath, functions=functions_payload)
                if calls_payload:
                    session.run(cypher_calls, calls=calls_payload)
        except Exception as e:
            self.log(f"⚠️ Neo4j Ingestion Error for '{filepath}': {e}")

    def analyze_impact(self, target_symbol: str) -> Dict[str, Any]:
        """Runs graph traversal to identify downstream entities impacted if target_symbol changes."""
        default_res = {
            "impact_found": False,
            "target_symbol": target_symbol,
            "symbol_type": ["Method"],
            "defined_in_file": "Unknown",
            "affected_callers": [],
            "affected_subclasses": [],
            "message": "Neo4j driver not connected or node not found.",
        }

        if not self.driver:
            return default_res

        cypher = """
        MATCH (target) WHERE target.name = $symbol OR target.short_name = $symbol
        OPTIONAL MATCH (caller:Function)-[:CALLS*1..5]->(target)
        OPTIONAL MATCH (sub:Class)-[:EXTENDS*1..5]->(target)
        OPTIONAL MATCH (f:File)-[:CONTAINS_FUNCTION|CONTAINS_CLASS]->(target)
        RETURN target.name AS symbol_name, labels(target) AS symbol_type,
               collect(DISTINCT caller.name) AS direct_and_transitive_callers,
               collect(DISTINCT sub.name) AS child_classes,
               f.path AS defined_in_file
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, symbol=target_symbol)
                records = list(result)

                if not records or not records[0]["symbol_name"]:
                    fuzzy_cypher = """
                    MATCH (fn:Function) WHERE fn.name ENDS WITH '.' + $symbol OR fn.short_name = $symbol
                    OPTIONAL MATCH (caller:Function)-[:CALLS*1..5]->(fn)
                    OPTIONAL MATCH (f:File)-[:CONTAINS_FUNCTION]->(fn)
                    RETURN fn.name AS symbol_name, ['Function'] AS symbol_type,
                           collect(DISTINCT caller.name) AS direct_and_transitive_callers,
                           [] AS child_classes, f.path AS defined_in_file
                    """
                    records = list(session.run(fuzzy_cypher, symbol=target_symbol))

                if not records or not records[0]["symbol_name"]:
                    default_res["message"] = f"No graph node found matching '{target_symbol}'."
                    return default_res

                record = records[0]
                return {
                    "impact_found": True,
                    "target_symbol": record["symbol_name"],
                    "symbol_type": record["symbol_type"],
                    "defined_in_file": record["defined_in_file"] or "Unknown",
                    "affected_callers": [c for c in record["direct_and_transitive_callers"] if c],
                    "affected_subclasses": [s for s in record["child_classes"] if s],
                }
        except Exception as e:
            default_res["message"] = f"Impact Analysis Cypher execution failed: {e}"
            return default_res

    def get_file_graph(self, filepath: str) -> Dict[str, Any]:
        """Retrieves structural nodes and edges for a specific file."""
        if not self.driver:
            return {"error": "Neo4j driver not connected."}

        cypher = """
        MATCH (f:File {path: $filepath})
        OPTIONAL MATCH (f)-[:CONTAINS_CLASS]->(c:Class)
        OPTIONAL MATCH (c)-[:HAS_METHOD]->(m:Function)
        OPTIONAL MATCH (f)-[:CONTAINS_FUNCTION]->(fn:Function)
        OPTIONAL MATCH (f)-[:IMPORTS]->(imp:Import)
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(callee:Function)
        WHERE caller.file = $filepath OR callee.file = $filepath
        RETURN f.path AS file_path,
               collect(DISTINCT c.name) AS classes,
               collect(DISTINCT fn.name) AS top_functions,
               collect(DISTINCT m.name) AS class_methods,
               collect(DISTINCT imp.code) AS imports,
               collect(DISTINCT {caller: caller.name, callee: callee.name}) AS call_edges
        """

        try:
            with self.driver.session() as session:
                records = list(session.run(cypher, filepath=filepath))
                if not records or not records[0]["file_path"]:
                    return {
                        "found": False,
                        "filepath": filepath,
                        "message": f"File '{filepath}' not found in knowledge graph.",
                    }

                rec = records[0]
                all_funcs = list(set([f for f in rec["top_functions"] if f] + [m for m in rec["class_methods"] if m]))
                valid_calls = [c for c in rec["call_edges"] if c.get("caller") and c.get("callee")]

                return {
                    "found": True,
                    "filepath": rec["file_path"],
                    "classes": [c for c in rec["classes"] if c],
                    "functions": all_funcs,
                    "imports": [i for i in rec["imports"] if i],
                    "call_relationships": valid_calls,
                }
        except Exception as e:
            return {"error": f"Failed to retrieve file graph for '{filepath}': {e}"}
