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
        auth: Optional[Any] = None,
    ):
        self.uri = uri or settings.NEO4J_URI
        if auth and isinstance(auth, (tuple, list)) and len(auth) >= 2:
            self.user = auth[0]
            self.password = auth[1]
        else:
            self.user = user or settings.neo4j_user
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
            driver_kwargs = {
                "auth": (self.user, self.password),
                "connection_timeout": 15.0,
            }
            try:
                from neo4j import NotificationDisabledClassification
                driver_kwargs["notifications_disabled_classifications"] = [
                    NotificationDisabledClassification.UNRECOGNIZED
                ]
            except Exception:
                pass

            self.driver = GraphDatabase.driver(
                self.uri,
                **driver_kwargs,
            )
            self.driver.verify_connectivity()
            self.log("✅ Connected to Neo4j Graph Database.")
            self._bootstrap_schema()
        except Exception as e:
            self.log(f"⚠️ Neo4j Connection Notice: {e}")
            self.driver = None

    def _bootstrap_schema(self) -> None:
        """Sets up per-workspace uniqueness constraints (ws + key) for multi-tenant graphs."""
        if not self.driver:
            return

        legacy = {("File", "path"), ("Class", "name"), ("Function", "name"), ("Import", "code")}
        constraints = [
            "CREATE CONSTRAINT file_ws_path IF NOT EXISTS FOR (f:File) REQUIRE (f.ws, f.path) IS UNIQUE",
            "CREATE CONSTRAINT class_ws_name IF NOT EXISTS FOR (c:Class) REQUIRE (c.ws, c.name) IS UNIQUE",
            "CREATE CONSTRAINT function_ws_name IF NOT EXISTS FOR (fn:Function) REQUIRE (fn.ws, fn.name) IS UNIQUE",
            "CREATE CONSTRAINT import_ws_code IF NOT EXISTS FOR (i:Import) REQUIRE (i.ws, i.code) IS UNIQUE",
            "CREATE INDEX entity_ws IF NOT EXISTS FOR (e:Entity) ON (e.ws)",
            "CREATE INDEX function_ws_short IF NOT EXISTS FOR (fn:Function) ON (fn.ws, fn.short_name)",
            "CREATE INDEX class_ws_short IF NOT EXISTS FOR (c:Class) ON (c.ws, c.short_name)",
            "CREATE INDEX file_ws IF NOT EXISTS FOR (f:File) ON (f.ws)",
        ]

        try:
            with self.driver.session() as session:
                # 0. Register polymorphic schema tokens so cross-language queries (e.g. IMPLEMENTS)
                # do not trigger Neo4j GqlStatusObject "relationship type does not exist" warnings.
                try:
                    session.run(
                        "MERGE (d:_SchemaInit {id: '__init__'}) "
                        "MERGE (d)-[:IMPLEMENTS]->(d) "
                        "MERGE (d)-[:EXTENDS]->(d) "
                        "DETACH DELETE d"
                    )
                except Exception as e:
                    self.log(f"⚠️ Relationship schema init notice: {e}")
                # Older databases have global single-property constraints that would
                # stop two workspaces from sharing a file path / symbol name.
                try:
                    existing = list(session.run(
                        "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties"
                    ))
                    for rec in existing:
                        labels, props = rec["labelsOrTypes"] or [], rec["properties"] or []
                        if (
                            rec["type"] == "UNIQUENESS"
                            and len(labels) == 1
                            and len(props) == 1
                            and (labels[0], props[0]) in legacy
                        ):
                            session.run(f"DROP CONSTRAINT `{rec['name']}` IF EXISTS")
                except Exception as e:
                    self.log(f"⚠️ Legacy constraint cleanup notice: {e}")

                for query in constraints:
                    try:
                        session.run(query)
                    except Exception as e:
                        self.log(f"⚠️ Constraint notice: {e}")
        except Exception as e:
            self.log(f"⚠️ Schema bootstrapping notice: {e}")

    def close(self) -> None:
        """Safely closes the Neo4j driver connection on process exit."""
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass

    def ingest_ast(self, filepath: str, ast_data: Dict[str, Any], workspace_id: Optional[str] = None) -> bool:
        """Ingests file AST structures into Neo4j in batch transactions for maximum throughput.

        Returns True only if the writes were successfully committed to Neo4j.
        Returns False if the driver is unavailable or if an error occurs.
        """
        if not self.driver or not ast_data:
            return False
        ws = workspace_id or "global"

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
            and c["caller"] != "unnamed_entity" and c["callee"] != "unnamed_entity"
        ]

        # 4. Prepare Imports payload
        imports_payload = [
            i.get("code", "").strip()
            for i in ast_data.get("imports", [])
            if i.get("code") and i.get("code").strip()
        ]

        # Cypher Transactions
        cypher_file_imports = """
        MERGE (f:File:Entity {path: $filepath, ws: $ws})
        SET f.updated_at = timestamp()
        WITH f
        UNWIND $imports AS imp_code
        MERGE (imp:Import:Entity {code: imp_code, ws: $ws})
        MERGE (f)-[:IMPORTS]->(imp)
        """

        cypher_classes = """
        MATCH (f:File {path: $filepath, ws: $ws})
        UNWIND $classes AS cls
        MERGE (c:Class:Entity {name: cls.name, ws: $ws})
        MERGE (f)-[:CONTAINS_CLASS]->(c)
        WITH c, cls
        UNWIND cls.extends AS parent
        MERGE (super:Class:Entity {name: parent, ws: $ws})
        MERGE (c)-[:EXTENDS]->(super)
        """

        cypher_functions = """
        MATCH (f:File {path: $filepath, ws: $ws})
        UNWIND $functions AS fn
        MERGE (func:Function:Entity {name: fn.full_name, ws: $ws})
        SET func.short_name = fn.short_name,
            func.type = fn.type,
            func.file = $filepath,
            func.is_anonymous = fn.is_anon
        MERGE (f)-[:CONTAINS_FUNCTION]->(func)
        WITH func, fn
        WHERE fn.class_name IS NOT NULL
        MERGE (c:Class:Entity {name: fn.class_name, ws: $ws})
        MERGE (c)-[:HAS_METHOD]->(func)
        """

        cypher_calls = """
        UNWIND $calls AS call
        MERGE (caller:Function:Entity {name: call.caller, ws: $ws})
        MERGE (callee:Function:Entity {name: call.callee, ws: $ws})
        MERGE (caller)-[:CALLS]->(callee)
        """

        try:
            with self.driver.session() as session:
                session.run(cypher_file_imports, filepath=filepath, imports=imports_payload, ws=ws)
                if classes_payload:
                    session.run(cypher_classes, filepath=filepath, classes=classes_payload, ws=ws)
                if functions_payload:
                    session.run(cypher_functions, filepath=filepath, functions=functions_payload, ws=ws)
                if calls_payload:
                    session.run(cypher_calls, calls=calls_payload, ws=ws)
            return True
        except Exception as e:
            self.log(f"⚠️ Neo4j Ingestion Error for '{filepath}': {e}")
            return False

    def analyze_blast_radius_with_inheritance(
        self, symbol: str, workspace_id: Optional[str] = None, max_hops: int = 3
    ) -> Dict[str, Any]:
        """
        Executes multi-hop Cypher traversals spanning [:CALLS], [:EXTENDS], [:IMPLEMENTS], and [:OVERRIDES].
        Traces downstream implementations and upstream callers across multi-module projects.
        """
        default_res = {
            "impact_found": False,
            "symbol": symbol,
            "target_symbol": symbol,
            "defined_in_file": "Unknown",
            "blast_radius_score": 0.0,
            "riskScore": "0.0 / 10",
            "riskLevel": "LOW",
            "affected_callers": [],
            "affected_subclasses": [],
            "affected_files": [],
            "nodes": [],
            "edges": [],
            "message": "Neo4j driver not connected or node not found.",
        }

        if not self.driver:
            return default_res
        clean_ws = str(workspace_id).strip() if workspace_id and str(workspace_id).strip() else None

        safe_hops = min(5, max(1, int(max_hops)))
        ws_target_clause = "{ws: $ws}" if clean_ws else ""
        ws_file_clause = "{ws: $ws}" if clean_ws else ""
        cypher_params = {"symbol": symbol}
        if clean_ws:
            cypher_params["ws"] = clean_ws

        cypher_query = f"""
        MATCH (target:Function|Class {ws_target_clause})
        WHERE (target.name = $symbol OR target.short_name = $symbol OR target.name ENDS WITH ('.' + $symbol))

        OPTIONAL MATCH (f:File {ws_file_clause})-[:CONTAINS_FUNCTION|CONTAINS_CLASS]->(target)

        CALL {{
            WITH target
            OPTIONAL MATCH (target)-[:EXTENDS|IMPLEMENTS*1..2]->(parent)
            RETURN collect(DISTINCT parent) as parents
        }}
        CALL {{
            WITH target
            OPTIONAL MATCH (child)-[:EXTENDS|IMPLEMENTS*1..2]->(target)
            RETURN collect(DISTINCT child) as children
        }}
        CALL {{
            WITH target
            OPTIONAL MATCH (caller:Function {{ws: target.ws}})-[:CALLS*1..{safe_hops}]->(target)
            RETURN collect(DISTINCT caller) as direct_callers
        }}
        CALL {{
            WITH target
            OPTIONAL MATCH (child)-[:EXTENDS|IMPLEMENTS*1..2]->(target)
            OPTIONAL MATCH (child_caller:Function {{ws: target.ws}})-[:CALLS*1..{safe_hops}]->(child)
            RETURN collect(DISTINCT child_caller) as child_callers
        }}
        CALL {{
            WITH target
            OPTIONAL MATCH (target)-[:CALLS]->(callee:Function {{ws: target.ws}})
            RETURN collect(DISTINCT callee)[0..15] as callees
        }}

        RETURN 
            target,
            labels(target) as target_labels,
            f.path as defined_file,
            parents,
            children,
            direct_callers,
            child_callers,
            callees
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, symbol=symbol, ws=clean_ws)
                records = list(result)
                if not records or not records[0]["target"]:
                    default_res["message"] = f"Symbol '{symbol}' not found in Neo4j graph."
                    return default_res

                # In case multiple nodes matched, choose the one with known file and most callers
                record = max(
                    records,
                    key=lambda r: (
                        bool(r.get("defined_file") or (r["target"].get("file") if hasattr(r["target"], "get") else None)),
                        len(r.get("direct_callers") or [])
                    )
                )

                target_node = record["target"]
                target_name = (target_node.get("name") if hasattr(target_node, "get") else None) or symbol
                target_file = (
                    (target_node.get("file") if hasattr(target_node, "get") else None)
                    or record.get("defined_file")
                    or "Unknown"
                )
                target_scope = (
                    (target_node.get("scope") if hasattr(target_node, "get") else None)
                    or (f"Class {target_name.split('.')[0]}" if "." in target_name else "Target Symbol")
                )

                parents = [p for p in (record.get("parents") or []) if p]
                children = [c for c in (record.get("children") or []) if c]
                callers = [c for c in (record.get("direct_callers") or []) if c]
                child_callers = [c for c in (record.get("child_callers") or []) if c]

                base_file_name = target_file.replace("\\", "/").split("/")[-1]

                nodes = [{
                    "id": "target",
                    "label": target_name,
                    "file": base_file_name,
                    "full_path": target_file,
                    "type": "TARGET",
                    "scope": target_scope,
                    "risk": "HIGH",
                    "x": 400,
                    "y": 200,
                }]
                edges = []

                # Process Parents ([:EXTENDS] / [:IMPLEMENTS])
                for i, p in enumerate(parents):
                    p_name = (p.get("name") if hasattr(p, "get") else str(p)) or f"Parent_{i}"
                    p_file = (p.get("file") if hasattr(p, "get") else "Unknown") or "Unknown"
                    p_id = f"parent_{i}"
                    nodes.append({
                        "id": p_id,
                        "label": p_name,
                        "file": p_file.replace("\\", "/").split("/")[-1],
                        "full_path": p_file,
                        "type": "INTERFACE" if "interface" in p_name.lower() else "SUPERCLASS",
                        "scope": "Inherited Contract",
                        "x": 220 + (i * 120),
                        "y": 80,
                    })
                    edges.append({"from": "target", "to": p_id, "label": "[:IMPLEMENTS|EXTENDS]", "hop": "Contract"})

                # Process Child Subclasses / Interface Implementations
                for i, c in enumerate(children):
                    c_name = (c.get("name") if hasattr(c, "get") else str(c)) or f"Child_{i}"
                    c_file = (c.get("file") if hasattr(c, "get") else "Unknown") or "Unknown"
                    c_id = f"child_{i}"
                    nodes.append({
                        "id": c_id,
                        "label": c_name,
                        "file": c_file.replace("\\", "/").split("/")[-1],
                        "full_path": c_file,
                        "type": "IMPLEMENTATION",
                        "scope": "Override / Subclass",
                        "x": 580 + (i * 120),
                        "y": 80,
                    })
                    edges.append({"from": c_id, "to": "target", "label": "[:OVERRIDES]", "hop": "Polymorphic"})

                # Process Direct Callers
                seen_caller_names = set()
                for i, c_node in enumerate(callers):
                    c_name = (c_node.get("name") if hasattr(c_node, "get") else str(c_node)) or f"Caller_{i}"
                    if c_name in seen_caller_names:
                        continue
                    seen_caller_names.add(c_name)
                    c_file = (c_node.get("file") if hasattr(c_node, "get") else "Unknown") or "Unknown"
                    c_id = f"caller_{i}"
                    nodes.append({
                        "id": c_id,
                        "label": c_name,
                        "file": c_file.replace("\\", "/").split("/")[-1],
                        "full_path": c_file,
                        "type": "DIRECT_CALLER",
                        "scope": f"Direct Call ({c_file.replace('\\', '/').split('/')[-1]})",
                        "x": 200 + (len(seen_caller_names) * 110),
                        "y": 340,
                    })
                    edges.append({"from": c_id, "to": "target", "label": "[:CALLS]", "hop": "1st Hop"})

                # Process Polymorphic Child Callers
                for i, cc_node in enumerate(child_callers):
                    cc_name = (cc_node.get("name") if hasattr(cc_node, "get") else str(cc_node)) or f"ChildCaller_{i}"
                    if cc_name in seen_caller_names:
                        continue
                    seen_caller_names.add(cc_name)
                    cc_file = (cc_node.get("file") if hasattr(cc_node, "get") else "Unknown") or "Unknown"
                    cc_id = f"child_caller_{i}"
                    nodes.append({
                        "id": cc_id,
                        "label": cc_name,
                        "file": cc_file.replace("\\", "/").split("/")[-1],
                        "full_path": cc_file,
                        "type": "DIRECT_CALLER",
                        "scope": f"Polymorphic Call ({cc_file.replace('\\', '/').split('/')[-1]})",
                        "x": 200 + (len(seen_caller_names) * 110),
                        "y": 340,
                    })
                    edges.append({"from": cc_id, "to": "target", "label": "[:CALLS]", "hop": "Polymorphic"})

                # Process Downstream Callees (invoked symbols)
                callees = [c for c in (record.get("callees") or []) if c]
                seen_callee_names = set()
                for i, c_node in enumerate(callees):
                    c_name = (c_node.get("name") if hasattr(c_node, "get") else str(c_node)) or f"Callee_{i}"
                    if c_name in seen_callee_names or c_name in seen_caller_names or c_name == target_name:
                        continue
                    seen_callee_names.add(c_name)
                    c_file = (c_node.get("file") if hasattr(c_node, "get") else "Unknown") or "Unknown"
                    is_external = not c_file or c_file == "Unknown"
                    display_file = "External / StdLib" if is_external else c_file.replace("\\", "/").split("/")[-1]
                    c_id = f"callee_{i}"
                    nodes.append({
                        "id": c_id,
                        "label": c_name,
                        "file": display_file,
                        "full_path": c_file if not is_external else "Standard Library / External Dependency",
                        "type": "CALLEE",
                        "scope": "Runtime Built-in / External Dependency" if is_external else f"Invoked Callee ({display_file})",
                        "x": 260 + (len(seen_callee_names) * 110),
                        "y": 420,
                    })
                    edges.append({"from": "target", "to": c_id, "label": "[:CALLS]", "hop": "Downstream"})

                all_callers_count = len(seen_caller_names)
                blast_score = round(min(10.0, 1.5 + (all_callers_count * 1.2) + (len(children) * 1.5)), 1)
                risk_level = "HIGH" if blast_score >= 6.5 else "MEDIUM" if blast_score >= 3.5 else "LOW"

                affected_files = list(set([
                    n["full_path"] for n in nodes if n.get("full_path") and n["full_path"] != "Unknown"
                ]))

                return {
                    "impact_found": True,
                    "symbol": target_name,
                    "target_symbol": target_name,
                    "name": target_name,
                    "defined_in_file": target_file,
                    "file": target_file,
                    "scope": target_scope,
                    "type": "Method" if "." in target_name else "Class",
                    "signature": f"symbol {target_name}",
                    "blast_radius_score": blast_score,
                    "riskScore": f"{blast_score} / 10",
                    "riskLevel": risk_level,
                    "blastRadiusHops": min(5, max(1, len(edges))),
                    "affected_callers": list(seen_caller_names),
                    "affected_subclasses": [c.get("name") for c in children if hasattr(c, "get") and c.get("name")],
                    "affected_files": affected_files or [target_file],
                    "nodes": nodes,
                    "edges": edges,
                }
        except Exception as e:
            self.log(f"⚠️ Blast Radius Inheritance Cypher error: {e}")
            return {
                "impact_found": False,
                "symbol": symbol,
                "message": f"Blast radius traversal failed: {e}",
            }

    def analyze_impact(self, target_symbol: str, workspace_id: Optional[str] = None) -> Dict[str, Any]:
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
        clean_ws = str(workspace_id).strip() if workspace_id and str(workspace_id).strip() else None

        if clean_ws:
            cypher = """
            MATCH (target:Function|Class {ws: $ws})
            WHERE (target.name = $symbol OR target.short_name = $symbol OR target.name ENDS WITH ('.' + $symbol))
            OPTIONAL MATCH (f:File {ws: $ws})-[:CONTAINS_FUNCTION|CONTAINS_CLASS]->(target)
            CALL {
                WITH target
                OPTIONAL MATCH (caller:Function {ws: target.ws})-[:CALLS*1..5]->(target)
                RETURN collect(DISTINCT caller.name) AS direct_and_transitive_callers
            }
            CALL {
                WITH target
                OPTIONAL MATCH (sub:Class {ws: target.ws})-[:EXTENDS*1..5]->(target)
                RETURN collect(DISTINCT sub.name) AS child_classes
            }
            RETURN target.name AS symbol_name, labels(target) AS symbol_type,
                   direct_and_transitive_callers,
                   child_classes,
                   f.path AS defined_in_file
            """
        else:
            cypher = """
            MATCH (target:Function|Class)
            WHERE (target.name = $symbol OR target.short_name = $symbol OR target.name ENDS WITH ('.' + $symbol))
            OPTIONAL MATCH (f:File)-[:CONTAINS_FUNCTION|CONTAINS_CLASS]->(target)
            CALL {
                WITH target
                OPTIONAL MATCH (caller:Function {ws: target.ws})-[:CALLS*1..5]->(target)
                RETURN collect(DISTINCT caller.name) AS direct_and_transitive_callers
            }
            CALL {
                WITH target
                OPTIONAL MATCH (sub:Class {ws: target.ws})-[:EXTENDS*1..5]->(target)
                RETURN collect(DISTINCT sub.name) AS child_classes
            }
            RETURN target.name AS symbol_name, labels(target) AS symbol_type,
                   direct_and_transitive_callers,
                   child_classes,
                   f.path AS defined_in_file
            """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, symbol=target_symbol, ws=clean_ws)
                records = list(result)

                if not records or not records[0]["symbol_name"]:
                    fuzzy_cypher = """
                    MATCH (fn:Function {ws: $ws}) WHERE (fn.name ENDS WITH '.' + $symbol OR fn.short_name = $symbol)
                    OPTIONAL MATCH (f:File {ws: $ws})-[:CONTAINS_FUNCTION]->(fn)
                    CALL {
                        WITH fn
                        OPTIONAL MATCH (caller:Function {ws: fn.ws})-[:CALLS*1..5]->(fn)
                        RETURN collect(DISTINCT caller.name) AS direct_and_transitive_callers
                    }
                    RETURN fn.name AS symbol_name, ['Function'] AS symbol_type,
                           direct_and_transitive_callers,
                           [] AS child_classes, f.path AS defined_in_file
                    """
                    records = list(session.run(fuzzy_cypher, symbol=target_symbol, ws=clean_ws))

                if not records or not records[0]["symbol_name"]:
                    default_res["message"] = f"No graph node found matching '{target_symbol}'."
                    return default_res

                # Several nodes can share a name: prefer one with a known file and the most callers
                record = max(
                    records,
                    key=lambda r: (
                        bool(r["defined_in_file"]),
                        len([c for c in r["direct_and_transitive_callers"] if c]),
                    ),
                )
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

    def list_symbols(self, workspace_id: Optional[str] = None, limit: int = 300) -> List[Dict[str, str]]:
        """Distinct class/function names indexed in the Neo4j AST for one workspace, with their file."""
        if not self.driver or not workspace_id or not str(workspace_id).strip():
            return []
        clean_ws = str(workspace_id).strip()
        cypher = """
        MATCH (n:Function|Class {ws: $ws}) 
        WHERE n.file IS NOT NULL 
          AND NOT n.name STARTS WITH '('
        RETURN DISTINCT n.name as name, n.file as file, head(labels(n)) as type
        ORDER BY n.name 
        LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                records = session.run(cypher, ws=clean_ws, limit=limit).data()
                return [{"name": r["name"], "file": r["file"] or "", "type": r.get("type", "Function")} for r in records]
        except Exception as e:
            self.log(f"⚠️ Neo4j symbol listing error: {e}")
            return []

    def get_file_graph(self, filepath: str, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves structural nodes and edges for a specific file."""
        if not self.driver:
            return {"error": "Neo4j driver must be connected."}
        clean_ws = str(workspace_id).strip() if workspace_id and str(workspace_id).strip() else None

        f_filter = "{path: $filepath, ws: $ws}" if clean_ws else "{path: $filepath}"
        cypher = """
        MATCH (f:File F_FILTER)
        CALL {
            WITH f
            OPTIONAL MATCH (f)-[:CONTAINS_CLASS]->(c:Class)
            RETURN collect(DISTINCT c.name) AS classes
        }
        CALL {
            WITH f
            OPTIONAL MATCH (f)-[:CONTAINS_CLASS]->(:Class)-[:HAS_METHOD]->(m:Function)
            RETURN collect(DISTINCT m.name) AS class_methods
        }
        CALL {
            WITH f
            OPTIONAL MATCH (f)-[:CONTAINS_FUNCTION]->(fn:Function)
            RETURN collect(DISTINCT fn.name) AS top_functions
        }
        CALL {
            WITH f
            OPTIONAL MATCH (f)-[:IMPORTS]->(imp:Import)
            RETURN collect(DISTINCT imp.code) AS imports
        }
        CALL {
            WITH f
            OPTIONAL MATCH (caller:Function {ws: f.ws})-[:CALLS]->(callee:Function {ws: f.ws})
            WHERE (caller.file = f.path OR callee.file = f.path)
            RETURN collect(DISTINCT {caller: caller.name, callee: callee.name}) AS call_edges
        }
        RETURN f.path AS file_path,
               classes,
               top_functions,
               class_methods,
               imports,
               call_edges
        """.replace("F_FILTER", f_filter)

        try:
            with self.driver.session() as session:
                records = list(session.run(cypher, filepath=filepath, ws=clean_ws))
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

    def get_workspace_architecture_graph(
        self, workspace_id: Optional[str] = None, limit: int = 350
    ) -> Dict[str, Any]:
        """
        Retrieves the unified architecture graph of all nodes connected by different relations:
        - Class inheritance: [:EXTENDS], [:IMPLEMENTS]
        - Class methods: [:HAS_METHOD]
        - Cross-class function calls: [:CALLS]
        - File containment: [:CONTAINS_CLASS], [:CONTAINS_FUNCTION]
        - File imports: [:IMPORTS]
        """
        if not self.driver or not workspace_id or not str(workspace_id).strip():
            return {"connected": False, "nodes": [], "edges": [], "message": "Workspace ID is required."}
        clean_ws = str(workspace_id).strip()

        # Stratified query across relationship tiers to ensure a balanced, readable architecture constellation:
        # 1. Inheritance & Interfaces ([:EXTENDS], [:IMPLEMENTS])
        # 2. File containment hierarchy ([:CONTAINS_CLASS], [:CONTAINS_FUNCTION])
        # 3. Class structure ([:HAS_METHOD])
        # 4. Cross-file imports ([:IMPORTS])
        # 5. Connected call flows ([:CALLS]) with dummy script tokens (unnamed_entity) filtered out
        cypher = """
        CALL () {
            MATCH (n:Class {ws: $ws})-[r:EXTENDS|IMPLEMENTS]->(m:Class {ws: $ws})
            WHERE 1=1
              AND n.name <> "unnamed_entity" AND m.name <> "unnamed_entity"
            RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
            LIMIT 25
        }
        RETURN n, n_labels, r, r_type, m, m_labels
        UNION
        CALL () {
            MATCH (n:File)-[r:CONTAINS_CLASS|CONTAINS_FUNCTION]->(m)
            WHERE (m.ws = $ws OR n.ws = $ws)
              AND m.name <> "unnamed_entity" AND NOT m.name STARTS WITH "anon_"
            RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
            LIMIT 60
        }
        RETURN n, n_labels, r, r_type, m, m_labels
        UNION
        CALL () {
            MATCH (n:Class)-[r:HAS_METHOD]->(m:Function)
            WHERE (n.ws = $ws OR m.ws = $ws)
              AND n.name <> "unnamed_entity" AND m.name <> "unnamed_entity"
            RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
            LIMIT 40
        }
        RETURN n, n_labels, r, r_type, m, m_labels
        UNION
        CALL () {
            MATCH (n:File)-[r:IMPORTS]->(m)
            WHERE (n.ws = $ws OR m.ws = $ws)
            RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
            LIMIT 40
        }
        RETURN n, n_labels, r, r_type, m, m_labels
        UNION
        CALL () {
            MATCH (n:Function)-[r:CALLS]->(m:Function)
            WHERE n.ws = $ws
              AND n.name <> "unnamed_entity" AND m.name <> "unnamed_entity"
              AND NOT n.name STARTS WITH "anon_" AND NOT m.name STARTS WITH "anon_"
              AND (n.file IS NOT NULL OR m.file IS NOT NULL)
            RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
            LIMIT 120
        }
        RETURN n, n_labels, r, r_type, m, m_labels
        """

        try:
            with self.driver.session() as session:
                try:
                    records = list(session.run(cypher, ws=clean_ws))
                except Exception:
                    # Fallback for simpler Neo4j runtimes without subqueries
                    records = list(session.run(
                        "MATCH (n:File|Class|Function|Entity {ws: $ws})-[r]->(m:File|Class|Function|Entity {ws: $ws}) RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels LIMIT $limit",
                        ws=clean_ws, limit=limit
                    ))
                nodes_map = {}
                edges = []

                for rec in records:
                    n = rec.get("n")
                    m = rec.get("m")
                    r = rec.get("r")
                    r_type = rec.get("r_type") or "RELATES"

                    def _extract_node(node_obj, labels):
                        if not node_obj:
                            return None
                        raw_id = (
                            (node_obj.get("name") if hasattr(node_obj, "get") else None)
                            or (node_obj.get("path") if hasattr(node_obj, "get") else None)
                            or (node_obj.get("code") if hasattr(node_obj, "get") else None)
                            or str(getattr(node_obj, "element_id", getattr(node_obj, "id", "")))
                        )
                        if not raw_id:
                            return None

                        labels_set = set(labels or [])
                        is_file = "File" in labels_set or "/" in raw_id or "\\" in raw_id or raw_id.endswith(".java") or raw_id.endswith(".go") or raw_id.endswith(".py") or raw_id.endswith(".js")
                        is_class = "Class" in labels_set or (raw_id[:1].isupper() and "." not in raw_id and not is_file)
                        is_iface = "interface" in raw_id.lower() or "Repository" in raw_id or "Details" in raw_id
                        is_method = "Function" in labels_set or "." in raw_id
                        is_import = "Import" in labels_set or raw_id.startswith("import ") or raw_id.startswith("from ")

                        node_type = (
                            "FILE" if is_file
                            else "IMPORT" if is_import
                            else "INTERFACE" if is_iface
                            else "CLASS" if is_class
                            else "METHOD" if is_method
                            else "SYMBOL"
                        )

                        display_label = (
                            (node_obj.get("short_name") if hasattr(node_obj, "get") else None)
                            or raw_id.replace("\\", "/").split("/")[-1]
                        )

                        return {
                            "id": raw_id,
                            "label": display_label,
                            "type": node_type,
                            "file": (node_obj.get("file") if hasattr(node_obj, "get") else None) or (raw_id if is_file else "Unknown"),
                            "scope": (node_obj.get("scope") if hasattr(node_obj, "get") else None) or f"{node_type} Scope",
                        }

                    node_n = _extract_node(n, rec.get("n_labels"))
                    if node_n and node_n["id"] not in nodes_map:
                        nodes_map[node_n["id"]] = node_n

                    node_m = _extract_node(m, rec.get("m_labels"))
                    if node_m and node_m["id"] not in nodes_map:
                        nodes_map[node_m["id"]] = node_m

                    if node_n and node_m and r is not None:
                        clean_type = r_type.replace("CONTAINS_CLASS", "CONTAINS").replace("CONTAINS_FUNCTION", "CONTAINS")
                        edges.append({
                            "from": node_n["id"],
                            "to": node_m["id"],
                            "label": f"[:{clean_type}]",
                            "relationType": clean_type,
                        })

                if not nodes_map:
                    # Fallback to isolated nodes if no relationships exist
                    fallback_records = list(session.run(
                        "MATCH (n:File|Class|Function|Entity {ws: $ws}) RETURN n, labels(n) as n_labels LIMIT $limit",
                        ws=clean_ws, limit=limit
                    ))
                    for rec in fallback_records:
                        node_n = _extract_node(rec.get("n"), rec.get("n_labels"))
                        if node_n and node_n["id"] not in nodes_map:
                            nodes_map[node_n["id"]] = node_n

                if not nodes_map:
                    return {"connected": False, "nodes": [], "edges": [], "message": "No nodes found in Neo4j."}

                return {
                    "connected": True,
                    "nodes": list(nodes_map.values()),
                    "edges": edges,
                    "stats": {
                        "totalNodes": len(nodes_map),
                        "totalEdges": len(edges),
                        "classes": len([n for n in nodes_map.values() if n.get("type") == "CLASS"]),
                        "interfaces": len([n for n in nodes_map.values() if n.get("type") == "INTERFACE"]),
                        "methods": len([n for n in nodes_map.values() if n.get("type") == "METHOD"]),
                        "files": len([n for n in nodes_map.values() if n.get("type") == "FILE"]),
                    }
                }
        except Exception as e:
            self.log(f"⚠️ get_workspace_architecture_graph failed: {e}")
            return {"connected": False, "nodes": [], "edges": [], "message": f"Architecture query failed: {e}"}

    def count_workspace_nodes(self, workspace_id: str) -> int:
        """Returns the number of nodes stored for this workspace in Neo4j."""
        if not self.driver or not workspace_id:
            return 0
        try:
            with self.driver.session() as session:
                res = session.run("MATCH (n:File|Class|Function|Import|Entity {ws: $ws}) RETURN count(n) as cnt", ws=str(workspace_id).strip()).single()
                return res["cnt"] if res else 0
        except Exception as e:
            self.log(f"⚠️ Graph count check error for {workspace_id}: {e}")
            return 0

    def delete_workspace(self, workspace_id: str) -> int:
        """Permanently deletes all nodes and relationships associated with a workspace from Neo4j."""
        if not self.driver or not workspace_id:
            return 0
        try:
            with self.driver.session() as session:
                res = session.run("MATCH (n:File|Class|Function|Import|Entity {ws: $ws}) DETACH DELETE n", ws=workspace_id)
                summary = res.consume()
                deleted = summary.counters.nodes_deleted
                self.log(f"🗑️ Deleted {deleted} Neo4j nodes for workspace '{workspace_id}'")
                return deleted
        except Exception as e:
            self.log(f"⚠️ Failed to delete Neo4j nodes for workspace '{workspace_id}': {e}")
            raise

    def get_blast_radius(
        self,
        symbol_name: str,
        workspace_id: Optional[str] = None,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """Calculates multi-hop blast radius for a symbol across the graph.

        Alias for analyze_blast_radius_with_inheritance to support programmatic usage
        and developer scripts matching README documentation.
        """
        res = self.analyze_blast_radius_with_inheritance(
            symbol=symbol_name,
            workspace_id=workspace_id,
            max_hops=max_depth,
        )
        if "total_affected_callers" not in res:
            res["total_affected_callers"] = len(res.get("affected_callers", []))
        return res


# Backward compatibility and README quickstart export alias
CodeGraphStore = Neo4jGraphStore
__all__ = ["Neo4jGraphStore", "CodeGraphStore"]
