import pytest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile
import os

from backend.app.services.repo_ingestor import resolve_calls, RepositoryIngestor


def test_resolve_calls_resolves_bare_method_names():
    # File 1 defines LoanService.borrow_book
    parsed = [
        {
            "rel": "services/loan_service.py",
            "ast": {
                "classes": [{"name": "LoanService", "extends": []}],
                "functions": [
                    {
                        "name": "LoanService.borrow_book",
                        "short_name": "borrow_book",
                        "type": "method",
                        "file": "services/loan_service.py",
                    }
                ],
                "calls": [],
                "imports": [],
            },
        },
        # File 2 defines LoanController.handle_borrow which calls bare "borrow_book"
        {
            "rel": "controllers/loan_controller.py",
            "ast": {
                "classes": [{"name": "LoanController", "extends": []}],
                "functions": [
                    {
                        "name": "LoanController.handle_borrow",
                        "short_name": "handle_borrow",
                        "type": "method",
                        "file": "controllers/loan_controller.py",
                    }
                ],
                "calls": [
                    {
                        "caller": "LoanController.handle_borrow",
                        "callee": "borrow_book",
                        "file": "controllers/loan_controller.py",
                    },
                    # Call originating from unnamed_entity should be dropped
                    {
                        "caller": "unnamed_entity",
                        "callee": "borrow_book",
                        "file": "controllers/loan_controller.py",
                    },
                    # Call targeting unnamed_entity should be dropped
                    {
                        "caller": "LoanController.handle_borrow",
                        "callee": "unnamed_entity",
                        "file": "controllers/loan_controller.py",
                    },
                ],
                "imports": [],
            },
        },
    ]

    resolve_calls(parsed)

    controller_calls = parsed[1]["ast"]["calls"]
    # 1. Calls from unnamed_entity and to unnamed_entity are dropped
    assert len(controller_calls) == 1

    # 2. Bare name 'borrow_book' was rewritten to qualified 'LoanService.borrow_book'
    assert controller_calls[0]["caller"] == "LoanController.handle_borrow"
    assert controller_calls[0]["callee"] == "LoanService.borrow_book"


def test_resolve_calls_disambiguates_same_class_and_same_file():
    parsed = [
        {
            "rel": "services/auth_service.py",
            "ast": {
                "classes": [{"name": "AuthService", "extends": []}],
                "functions": [
                    {
                        "name": "AuthService.generate_token",
                        "short_name": "generate_token",
                        "type": "method",
                        "file": "services/auth_service.py",
                    },
                    {
                        "name": "AuthService.login",
                        "short_name": "login",
                        "type": "method",
                        "file": "services/auth_service.py",
                    },
                ],
                "calls": [
                    {
                        "caller": "AuthService.login",
                        "callee": "generate_token",
                        "file": "services/auth_service.py",
                    }
                ],
                "imports": [],
            },
        },
        {
            "rel": "services/other_service.py",
            "ast": {
                "classes": [{"name": "OtherService", "extends": []}],
                "functions": [
                    {
                        "name": "OtherService.generate_token",
                        "short_name": "generate_token",
                        "type": "method",
                        "file": "services/other_service.py",
                    }
                ],
                "calls": [],
                "imports": [],
            },
        },
    ]

    resolve_calls(parsed)

    auth_calls = parsed[0]["ast"]["calls"]
    assert len(auth_calls) == 1
    # Prefers same-class definition AuthService.generate_token over OtherService.generate_token
    assert auth_calls[0]["callee"] == "AuthService.generate_token"


def test_index_files_executes_two_pass_call_resolution():
    mock_vector = MagicMock()
    mock_graph = MagicMock()

    ingestor = RepositoryIngestor(vector_store=mock_vector, graph_store=mock_graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "service.py"
        f1.write_text("class Service:\n    def borrow_book(self):\n        pass\n", encoding="utf-8")

        f2 = Path(tmp_dir) / "controller.py"
        f2.write_text("class Controller:\n    def borrow(self):\n        borrow_book()\n", encoding="utf-8")

        summary = ingestor._index_files(tmp_dir, [f1, f2], workspace_id="ws-test")

        # Verify graph_store.ingest_ast was called with resolved calls
        assert mock_graph.ingest_ast.called
        calls_ingested = []
        for call_args in mock_graph.ingest_ast.call_args_list:
            rel_path, ast_data = call_args[0][0], call_args[0][1]
            calls_ingested.extend(ast_data.get("calls", []))

        # Check that 'borrow_book' was rewritten to 'Service.borrow_book'
        matching = [c for c in calls_ingested if c.get("callee") == "Service.borrow_book"]
        assert len(matching) >= 1
        assert matching[0]["caller"] == "Controller.borrow"


def test_blast_radius_simulation_finds_callers():
    """Simulates the Cypher selection rules against resolved call edges."""
    # Graph nodes
    nodes = {
        "Service.borrow_book": {"name": "Service.borrow_book", "short_name": "borrow_book", "file": "service.py"},
        "Controller.borrow": {"name": "Controller.borrow", "short_name": "borrow", "file": "controller.py"},
    }
    # Call edges after resolve_calls
    edges = [
        {"caller": "Controller.borrow", "callee": "Service.borrow_book"}
    ]

    symbol = "borrow_book"

    # Cypher rule: MATCH (target) WHERE target.name = $symbol OR target.short_name = $symbol OR target.name ENDS WITH ('.' + $symbol)
    matched_targets = [
        node for name, node in nodes.items()
        if node["name"] == symbol or node["short_name"] == symbol or node["name"].endswith("." + symbol)
    ]
    assert len(matched_targets) == 1
    target = matched_targets[0]
    assert target["name"] == "Service.borrow_book"

    # Cypher rule: OPTIONAL MATCH (caller)-[:CALLS]->(target)
    callers = [e["caller"] for e in edges if e["callee"] == target["name"]]

    assert len(callers) == 1
    assert "Controller.borrow" in callers

