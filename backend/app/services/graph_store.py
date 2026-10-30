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
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                connection_timeout=15.0
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
        ]

        try:
            with self.driver.session() as session:
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

    def ingest_ast(self, filepath: str, ast_data: Dict[str, Any], workspace_id: Optional[str] = None) -> None:
        """Ingests file AST structures into Neo4j in batch transactions for maximum throughput."""
        if not self.driver or not ast_data:
            return
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
        ]

        # 4. Prepare Imports payload
        imports_payload = [
            i.get("code", "").strip()
            for i in ast_data.get("imports", [])
            if i.get("code") and i.get("code").strip()
        ]

        # Cypher Transactions
        cypher_file_imports = """
        MERGE (f:File {path: $filepath, ws: $ws})
        SET f.updated_at = timestamp()
        WITH f
        UNWIND $imports AS imp_code
        MERGE (imp:Import {code: imp_code, ws: $ws})
        MERGE (f)-[:IMPORTS]->(imp)
        """

        cypher_classes = """
        MATCH (f:File {path: $filepath, ws: $ws})
        UNWIND $classes AS cls
        MERGE (c:Class {name: cls.name, ws: $ws})
        MERGE (f)-[:CONTAINS_CLASS]->(c)
        WITH c, cls
        UNWIND cls.extends AS parent
        MERGE (super:Class {name: parent, ws: $ws})
        MERGE (c)-[:EXTENDS]->(super)
        """

        cypher_functions = """
        MATCH (f:File {path: $filepath, ws: $ws})
        UNWIND $functions AS fn
        MERGE (func:Function {name: fn.full_name, ws: $ws})
        SET func.short_name = fn.short_name,
            func.type = fn.type,
            func.file = $filepath,
            func.is_anonymous = fn.is_anon
        MERGE (f)-[:CONTAINS_FUNCTION]->(func)
        WITH func, fn
        WHERE fn.class_name IS NOT NULL
        MERGE (c:Class {name: fn.class_name, ws: $ws})
        MERGE (c)-[:HAS_METHOD]->(func)
        """

        cypher_calls = """
        UNWIND $calls AS call
        MERGE (caller:Function {name: call.caller, ws: $ws})
        MERGE (callee:Function {name: call.callee, ws: $ws})
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
        except Exception as e:
            self.log(f"⚠️ Neo4j Ingestion Error for '{filepath}': {e}")

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

        safe_hops = min(5, max(1, int(max_hops)))

        cypher_query = f"""
        MATCH (target) WHERE (target.name = $symbol OR target.short_name = $symbol OR target.name ENDS WITH ('.' + $symbol))
          AND ($ws IS NULL OR target.ws = $ws)

        // 1. Fetch Interface & Class Hierarchy (Upstream & Downstream)
        OPTIONAL MATCH (target)-[:EXTENDS|IMPLEMENTS*1..2]->(parent)
        OPTIONAL MATCH (child)-[:EXTENDS|IMPLEMENTS*1..2]->(target)

        // 2. Fetch Callers across all overrides & implementations
        OPTIONAL MATCH (caller)-[:CALLS*1..{safe_hops}]->(target)
        OPTIONAL MATCH (child_caller)-[:CALLS*1..{safe_hops}]->(child)

        // 3. Fetch Downstream Callees that target invokes
        OPTIONAL MATCH (target)-[:CALLS]->(callee)

        // 4. File containing target
        OPTIONAL MATCH (f:File)-[:CONTAINS_FUNCTION|CONTAINS_CLASS]->(target)

        RETURN 
            target,
            labels(target) as target_labels,
            f.path as defined_file,
            collect(DISTINCT parent) as parents,
            collect(DISTINCT child) as children,
            collect(DISTINCT caller) as direct_callers,
            collect(DISTINCT child_caller) as child_callers,
            collect(DISTINCT callee)[0..15] as callees
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, symbol=symbol, ws=workspace_id)
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

        cypher = """
        MATCH (target) WHERE (target.name = $symbol OR target.short_name = $symbol)
          AND ($ws IS NULL OR target.ws = $ws)
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
                result = session.run(cypher, symbol=target_symbol, ws=workspace_id)
                records = list(result)

                if not records or not records[0]["symbol_name"]:
                    fuzzy_cypher = """
                    MATCH (fn:Function) WHERE (fn.name ENDS WITH '.' + $symbol OR fn.short_name = $symbol)
                      AND ($ws IS NULL OR fn.ws = $ws)
                    OPTIONAL MATCH (caller:Function)-[:CALLS*1..5]->(fn)
                    OPTIONAL MATCH (f:File)-[:CONTAINS_FUNCTION]->(fn)
                    RETURN fn.name AS symbol_name, ['Function'] AS symbol_type,
                           collect(DISTINCT caller.name) AS direct_and_transitive_callers,
                           [] AS child_classes, f.path AS defined_in_file
                    """
                    records = list(session.run(fuzzy_cypher, symbol=target_symbol, ws=workspace_id))

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
        if not self.driver:
            return []
        cypher = """
        MATCH (n) 
        WHERE (n.ws = $ws OR $ws IS NULL) 
          AND (n:Function OR n:Class) 
          AND n.file IS NOT NULL 
          AND NOT n.name STARTS WITH '('
        RETURN DISTINCT n.name as name, n.file as file, head(labels(n)) as type
        ORDER BY n.name 
        LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                records = session.run(cypher, ws=workspace_id, limit=limit).data()
                return [{"name": r["name"], "file": r["file"] or "", "type": r.get("type", "Function")} for r in records]
        except Exception as e:
            self.log(f"⚠️ Neo4j symbol listing error: {e}")
            return []

    def get_file_graph(self, filepath: str, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves structural nodes and edges for a specific file."""
        if not self.driver:
            return {"error": "Neo4j driver not connected."}

        cypher = """
        MATCH (f:File) WHERE f.path = $filepath AND ($ws IS NULL OR f.ws = $ws)
        OPTIONAL MATCH (f)-[:CONTAINS_CLASS]->(c:Class)
        OPTIONAL MATCH (c)-[:HAS_METHOD]->(m:Function)
        OPTIONAL MATCH (f)-[:CONTAINS_FUNCTION]->(fn:Function)
        OPTIONAL MATCH (f)-[:IMPORTS]->(imp:Import)
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(callee:Function)
        WHERE (caller.file = $filepath OR callee.file = $filepath) AND ($ws IS NULL OR caller.ws = $ws)
        RETURN f.path AS file_path,
               collect(DISTINCT c.name) AS classes,
               collect(DISTINCT fn.name) AS top_functions,
               collect(DISTINCT m.name) AS class_methods,
               collect(DISTINCT imp.code) AS imports,
               collect(DISTINCT {caller: caller.name, callee: callee.name}) AS call_edges
        """

        try:
            with self.driver.session() as session:
                records = list(session.run(cypher, filepath=filepath, ws=workspace_id))
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
        if not self.driver:
            return {"connected": False, "nodes": [], "edges": [], "message": "Neo4j driver not connected."}

        # Query explicit relationships first to ensure full connectivity and typed edges
        cypher = """
        MATCH (n)-[r]->(m) WHERE ($ws IS NULL OR n.ws = $ws)
        RETURN n, labels(n) as n_labels, r, type(r) as r_type, m, labels(m) as m_labels
        LIMIT $limit
        """

        try:
            with self.driver.session() as session:
                records = list(session.run(cypher, ws=workspace_id, limit=limit))
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
                        edges.append({
                            "from": node_n["id"],
                            "to": node_m["id"],
                            "label": f"[:{r_type}]",
                            "relationType": r_type.replace("CONTAINS_CLASS", "CONTAINS").replace("CONTAINS_FUNCTION", "CONTAINS"),
                        })

                if not nodes_map:
                    # Fallback to isolated nodes if no relationships exist
                    fallback_records = list(session.run(
                        "MATCH (n) WHERE ($ws IS NULL OR n.ws = $ws) RETURN n, labels(n) as n_labels LIMIT $limit",
                        ws=workspace_id, limit=limit
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
