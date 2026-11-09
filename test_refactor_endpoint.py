import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.rag import _extract_snippets_from_diff

client = TestClient(app)


def test_extract_snippets_from_diff_is_imported_and_works():
    diff_code = (
        "--- a/service/LoanService.py\n"
        "+++ b/service/LoanService.py\n"
        "@@ -10,1 +10,1 @@\n"
        "-def borrow_book(self):\n"
        "+def borrow_book(self, user_id):\n"
    )
    old_snip, new_snip = _extract_snippets_from_diff(diff_code)
    assert old_snip == "def borrow_book(self):"
    assert new_snip == "def borrow_book(self, user_id):"


@patch("backend.app.api.rag._call_gemini")
@patch("backend.app.api.rag.completion_with_telemetry")
@patch("backend.app.api.rag._retrieve")
def test_refactor_handles_missing_old_new_code_without_500(mock_retrieve, mock_completion, mock_call_gemini):
    mock_retrieve.return_value = [
        {"filepath": "service/LoanService.py", "start_line": 1, "end_line": 20, "snippet": "def borrow_book(): pass"}
    ]

    # Model reply omits old_code and new_code, providing only diffCode
    stubbed_reply = json.dumps({
        "summary": "Added user parameter to borrow_book",
        "diffs": [
            {
                "file": "service/LoanService.py",
                "diffCode": "--- a/service/LoanService.py\n+++ b/service/LoanService.py\n@@ -10,1 +10,1 @@\n-def borrow_book(self):\n+def borrow_book(self, user_id):\n"
            }
        ]
    })
    mock_call_gemini.return_value = stubbed_reply

    response = client.post(
        "/api/rag/refactor",
        json={
            "workspace_id": "ws-study-sync",
            "prompt": "Update borrow_book signature",
            "gemini_api_key": "dummy_gemini_key_1234567890",
            "provider": "gemini"
        }
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["filesChanged"] == 1
    diff = data["diffs"][0]
    # Extracted from diffCode without 500 NameError
    assert diff["old_code"] == "def borrow_book(self):"
    assert diff["new_code"] == "def borrow_book(self, user_id):"


@patch("backend.app.api.rag._call_gemini")
@patch("backend.app.api.rag.completion_with_telemetry")
@patch("backend.app.api.rag._retrieve")
def test_refactor_routes_to_selected_non_gemini_provider(mock_retrieve, mock_completion, mock_call_gemini):
    mock_retrieve.return_value = [
        {"filepath": "service/LoanService.py", "start_line": 1, "end_line": 20, "snippet": "def borrow_book(): pass"}
    ]

    stubbed_reply = json.dumps({
        "summary": "Refactored with Groq",
        "diffs": [
            {
                "file": "service/LoanService.py",
                "old_code": "def borrow_book(self):",
                "new_code": "def borrow_book(self, user_id):",
                "diffCode": "--- a/service/LoanService.py\n+++ b/service/LoanService.py\n@@ -10,1 +10,1 @@\n-def borrow_book(self):\n+def borrow_book(self, user_id):\n"
            }
        ]
    })
    mock_completion.return_value = (stubbed_reply, {"latency_ms": 100})

    response = client.post(
        "/api/rag/refactor",
        json={
            "workspace_id": "ws-study-sync",
            "prompt": "Update borrow_book signature",
            "api_key": "gsk_dummy_groq_key_1234567890",
            "provider": "groq",
            "model_id": "groq/llama-3.3-70b-versatile"
        }
    )

    assert response.status_code == 200, response.text
    # _call_gemini MUST NOT have been called!
    assert not mock_call_gemini.called
    # completion_with_telemetry MUST have been called with provider="groq"
    assert mock_completion.called
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs["provider"] == "groq"
    assert "groq" in call_kwargs["model_alias"].lower() or "llama" in call_kwargs["model_alias"].lower()


@patch("backend.app.api.rag._call_gemini")
@patch("backend.app.api.rag.completion_with_telemetry")
@patch("backend.app.api.rag._retrieve")
def test_refactor_routes_to_openai_provider(mock_retrieve, mock_completion, mock_call_gemini):
    mock_retrieve.return_value = [
        {"filepath": "service/LoanService.py", "start_line": 1, "end_line": 20, "snippet": "def borrow_book(): pass"}
    ]

    stubbed_reply = json.dumps({
        "summary": "Refactored with OpenAI",
        "diffs": [
            {
                "file": "service/LoanService.py",
                "old_code": "def old():",
                "new_code": "def new():",
                "diffCode": "--- a/service/LoanService.py\n+++ b/service/LoanService.py\n@@ -1,1 +1,1 @@\n-def old():\n+def new():\n"
            }
        ]
    })
    mock_completion.return_value = (stubbed_reply, {"latency_ms": 100})

    response = client.post(
        "/api/rag/refactor",
        json={
            "workspace_id": "ws-study-sync",
            "prompt": "Update signature",
            "api_key": "sk-dummy_openai_key_1234567890",
            "provider": "openai",
            "model_id": "gpt-4o"
        }
    )

    assert response.status_code == 200, response.text
    assert not mock_call_gemini.called
    assert mock_completion.called
    assert mock_completion.call_args[1]["provider"] == "openai"

