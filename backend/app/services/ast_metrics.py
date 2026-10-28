import logging
from typing import Dict, Any, List
from tree_sitter import Parser, Node
from backend.app.services.ast_validator import LANGUAGES, get_language_from_filename

logger = logging.getLogger("codegraph.ast_metrics")

# Syntax nodes that represent control flow decisions
BRANCH_NODE_TYPES = {
    "if_statement", "for_statement", "while_statement", "do_statement",
    "case_statement", "catch_clause", "conditional_expression", # Ternary '?'
    "binary_expression", # Logical '&&' or '||'
    "elif_clause", "for_in_clause", "switch_case"
}

NESTING_NODE_TYPES = {
    "if_statement", "for_statement", "while_statement", "do_statement",
    "switch_statement", "try_statement", "catch_clause", "block", "compound_statement"
}

def _calculate_node_metrics(node: Node, code_bytes: bytes, depth: int = 0) -> Dict[str, Any]:
    decision_points = 0
    max_depth = depth
    param_count = 0

    if node.type in BRANCH_NODE_TYPES:
        if node.type == "binary_expression":
            op_text = code_bytes[node.start_byte:node.end_byte]
            if b"&&" in op_text or b"||" in op_text or b" and " in op_text or b" or " in op_text:
                decision_points += 1
        else:
            decision_points += 1

    # Measure parameter list sizes
    if node.type in ("formal_parameters", "parameters", "parameter_list"):
        param_count = len([c for c in node.children if c.type in ("formal_parameter", "parameter", "identifier")])

    current_depth = depth + (1 if node.type in NESTING_NODE_TYPES else 0)
    max_depth = max(max_depth, current_depth)

    for child in node.children:
        child_metrics = _calculate_node_metrics(child, code_bytes, current_depth)
        decision_points += child_metrics["decision_points"]
        max_depth = max(max_depth, child_metrics["max_depth"])
        if child_metrics["param_count"] > 0:
            param_count = max(param_count, child_metrics["param_count"])

    return {
        "decision_points": decision_points,
        "max_depth": max_depth,
        "param_count": param_count
    }

def compute_ast_metrics(filename: str, code_content: str) -> Dict[str, Any]:
    """Computes Cyclomatic Complexity, Max Nesting Depth, and Parameter Count."""
    if not code_content or not code_content.strip():
        return {"cyclomatic_complexity": 1, "max_nesting_depth": 0, "param_count": 0, "loc": 0}

    lang_key = get_language_from_filename(filename)
    if not lang_key or lang_key not in LANGUAGES:
        lines = [l for l in code_content.splitlines() if l.strip()]
        return {"cyclomatic_complexity": 1, "max_nesting_depth": 1, "param_count": 0, "loc": len(lines)}

    language = LANGUAGES[lang_key]
    try:
        parser = Parser(language)
        code_bytes = code_content.encode("utf-8")
        tree = parser.parse(code_bytes)

        raw_metrics = _calculate_node_metrics(tree.root_node, code_bytes)
        non_empty_lines = [l for l in code_content.splitlines() if l.strip() and not l.strip().startswith(("//", "#", "/*"))]

        cyclomatic_complexity = raw_metrics["decision_points"] + 1

        return {
            "cyclomatic_complexity": cyclomatic_complexity,
            "max_nesting_depth": raw_metrics["max_depth"],
            "param_count": raw_metrics["param_count"],
            "loc": len(non_empty_lines)
        }
    except Exception as e:
        logger.warning(f"AST metrics calculation failed for '{filename}': {e}")
        lines = [l for l in code_content.splitlines() if l.strip()]
        return {"cyclomatic_complexity": 1, "max_nesting_depth": 1, "param_count": 0, "loc": len(lines)}

def calculate_health_delta(old_code: str, new_code: str, filename: str) -> Dict[str, Any]:
    """Computes pre vs post refactor AST health comparison and score delta."""
    pre = compute_ast_metrics(filename, old_code)
    post = compute_ast_metrics(filename, new_code)

    complexity_delta = post["cyclomatic_complexity"] - pre["cyclomatic_complexity"]
    nesting_delta = post["max_nesting_depth"] - pre["max_nesting_depth"]
    loc_delta = post["loc"] - pre["loc"]

    # Calculate Code Health Impact Score (-10 to +10)
    health_score_change = 0.0
    if complexity_delta < 0:
        health_score_change += abs(complexity_delta) * 1.5  # Complexity reduction is good
    elif complexity_delta > 0:
        health_score_change -= complexity_delta * 1.2

    if nesting_delta < 0:
        health_score_change += 1.0
    elif nesting_delta > 0:
        health_score_change -= 1.0

    return {
        "pre_refactor": pre,
        "post_refactor": post,
        "deltas": {
            "complexity": complexity_delta,
            "nesting": nesting_delta,
            "loc": loc_delta
        },
        "health_score_delta": round(health_score_change, 1),
        "verdict": "IMPROVED" if health_score_change > 0 else "NEUTRAL" if health_score_change == 0 else "COMPLEXITY_INCREASED"
    }
