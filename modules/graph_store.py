import os
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Driver


class Neo4jGraphStore:
    """Manages property graph storage in Neo4j, modeling code entities and dependencies."""

    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[Driver] = None
        self._connect()

    def _connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            self._bootstrap_schema()
        except Exception as e:
            print(f"⚠️ Neo4j Connection Error: {e}")
            self.driver = None

    def _bootstrap_schema(self):
        """Pre-seeds schema relationship types to suppress Neo4j DBMS missing-type warnings."""
        if not self.driver:
            return
        seed_cypher = """
        MERGE (a:__InitNode__ {id: 1})
        MERGE (b:__InitNode__ {id: 2})
        MERGE (a)-[:EXTENDS]->(b)
        MERGE (a)-[:CALLS]->(b)
        MERGE (a)-[:CONTAINS_CLASS]->(b)
        MERGE (a)-[:CONTAINS_FUNCTION]->(b)
        MERGE (a)-[:HAS_METHOD]->(b)
        MERGE (a)-[:IMPORTS]->(b)
        WITH a, b
        DETACH DELETE a, b
        """
        try:
            with self.driver.session() as session:
                session.run(seed_cypher)
        except Exception:
            pass

    def close(self):
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass

    def ingest_ast(self, filepath: str, ast_data: Dict[str, Any]):
        """Ingests AST components into Neo4j, safely persisting anonymous entities without dropping relationships."""
        if not self.driver or not ast_data:
            return

        cypher_file = """
        MERGE (f:File {path: $filepath})
        SET f.updated_at = timestamp()
        """

        cypher_class = """
        MATCH (f:File {path: $filepath})
        MERGE (c:Class {name: $class_name})
        MERGE (f)-[:CONTAINS_CLASS]->(c)
        """

        cypher_extends = """
        MATCH (sub:Class {name: $sub_class})
        MERGE (super:Class {name: $super_class})
        MERGE (sub)-[:EXTENDS]->(super)
        """

        cypher_method = """
        MATCH (f:File {path: $filepath})
        MATCH (c:Class {name: $class_name})
        MERGE (fn:Function {name: $full_method_name})
        SET fn.short_name = $short_name, 
            fn.type = 'method', 
            fn.file = $filepath,
            fn.is_anonymous = $is_anon
        MERGE (c)-[:HAS_METHOD]->(fn)
        MERGE (f)-[:CONTAINS_FUNCTION]->(fn)
        """

        cypher_func = """
        MATCH (f:File {path: $filepath})
        MERGE (fn:Function {name: $func_name})
        SET fn.short_name = $short_name, 
            fn.type = 'function', 
            fn.file = $filepath,
            fn.is_anonymous = $is_anon
        MERGE (f)-[:CONTAINS_FUNCTION]->(fn)
        """

        cypher_call = """
        MERGE (caller:Function {name: $caller_name})
        MERGE (callee:Function {name: $callee_name})
        MERGE (caller)-[:CALLS]->(callee)
        """

        cypher_import = """
        MATCH (f:File {path: $filepath})
        MERGE (imp:Import {code: $import_code})
        MERGE (f)-[:IMPORTS]->(imp)
        """

        try:
            with self.driver.session() as session:
                session.run(cypher_file, filepath=filepath)

                for cls in ast_data.get("classes", []):
                    c_name = cls.get("name") or "AnonClass"
                    session.run(cypher_class, filepath=filepath, class_name=c_name)

                    for parent in cls.get("extends", []):
                        if parent and parent != "unnamed_entity":
                            session.run(cypher_extends, sub_class=c_name, super_class=parent)

                for fn in ast_data.get("functions", []):
                    full_name = fn.get("name")
                    if not full_name or full_name == "unnamed_entity":
                        full_name = f"anon_func_{os.path.basename(filepath)}_L{fn.get('line', 0)}"

                    short_name = fn.get("short_name", full_name)
                    is_anon = "anon_" in full_name or "lambda_" in full_name

                    if fn.get("type") == "method" and "." in full_name:
                        c_name = full_name.split(".")[0]
                        session.run(
                            cypher_method,
                            filepath=filepath,
                            class_name=c_name,
                            full_method_name=full_name,
                            short_name=short_name,
                            is_anon=is_anon,
                        )
                    else:
                        session.run(
                            cypher_func,
                            filepath=filepath,
                            func_name=full_name,
                            short_name=short_name,
                            is_anon=is_anon,
                        )

                for call in ast_data.get("calls", []):
                    caller = call.get("caller")
                    callee = call.get("callee")
                    if caller and callee:
                        session.run(cypher_call, caller_name=caller, callee_name=callee)

                for imp in ast_data.get("imports", []):
                    code_str = imp.get("code", "").strip()
                    if code_str:
                        session.run(cypher_import, filepath=filepath, import_code=code_str)

        except Exception as e:
            print(f"⚠️ Neo4j Ingestion Error for '{filepath}': {e}")

    def analyze_impact(self, target_symbol: str) -> Dict[str, Any]:
        """Runs graph traversal to identify downstream entities impacted if target_symbol changes."""
        default_error_res = {
            "impact_found": False,
            "target_symbol": target_symbol,
            "symbol_type": [],
            "defined_in_file": "Unknown",
            "affected_callers": [],
            "affected_subclasses": [],
            "message": "Neo4j driver not connected.",
        }

        if not self.driver:
            return default_error_res

        cypher = """
        MATCH (target) WHERE target.name = $symbol OR target.short_name = $symbol
        OPTIONAL MATCH (caller:Function)-[:CALLS*1..5]->(target)
        OPTIONAL MATCH (sub:Class)-[:EXTENDS*1..5]->(target)
        OPTIONAL MATCH (f:File)-[:CONTAINS_FUNCTION|CONTAINS_CLASS]->(target)
        RETURN
            target.name AS symbol_name,
            labels(target) AS symbol_type,
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
                    RETURN
                        fn.name AS symbol_name,
                        ['Function'] AS symbol_type,
                        collect(DISTINCT caller.name) AS direct_and_transitive_callers,
                        [] AS child_classes,
                        f.path AS defined_in_file
                    """
                    result = session.run(fuzzy_cypher, symbol=target_symbol)
                    records = list(result)

                if not records or not records[0]["symbol_name"]:
                    return {
                        "impact_found": False,
                        "target_symbol": target_symbol,
                        "symbol_type": [],
                        "defined_in_file": "Unknown",
                        "affected_callers": [],
                        "affected_subclasses": [],
                        "message": f"No graph node found matching '{target_symbol}'.",
                    }

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
            default_error_res["message"] = f"Impact Analysis Cypher execution failed: {e}"
            return default_error_res

    def get_file_graph(self, filepath: str) -> Dict[str, Any]:
        """Retrieves structural nodes and edges (classes, functions, calls, imports) for a specific file."""
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
        RETURN
            f.path AS file_path,
            collect(DISTINCT c.name) AS classes,
            collect(DISTINCT fn.name) AS top_functions,
            collect(DISTINCT m.name) AS class_methods,
            collect(DISTINCT imp.code) AS imports,
            collect(DISTINCT {caller: caller.name, callee: callee.name}) AS call_edges
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, filepath=filepath)
                records = list(result)

                if not records or not records[0]["file_path"]:
                    return {
                        "found": False,
                        "filepath": filepath,
                        "message": f"File '{filepath}' not found in knowledge graph."
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
                    "call_relationships": valid_calls
                }
        except Exception as e:
            return {"error": f"Failed to retrieve file graph for '{filepath}': {e}"}