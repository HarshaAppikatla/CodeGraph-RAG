from unittest.mock import MagicMock, patch
import pytest
from backend.app.services.vector_store import CodeVectorStore


def test_gemini_provider_detection_and_dimension():
    # 1. By provider="gemini"
    store_p = CodeVectorStore(
        collection_name="test_gemini_p",
        qdrant_path=":memory:",
        provider="gemini",
    )
    assert store_p.provider == "gemini"
    assert store_p.vector_size == 3072
    assert store_p.model_name == "text-embedding-004"

    # 2. By model_name="models/text-embedding-004"
    store_m = CodeVectorStore(
        collection_name="test_gemini_m",
        qdrant_path=":memory:",
        model_name="models/text-embedding-004",
    )
    assert store_m.provider == "gemini"
    assert store_m.vector_size == 3072

    # 3. By model_name="gemini-embedding-001"
    store_g = CodeVectorStore(
        collection_name="test_gemini_g",
        qdrant_path=":memory:",
        model_name="gemini-embedding-001",
    )
    assert store_g.provider == "gemini"
    assert store_g.vector_size == 3072

    # 4. Default stays local 384D
    store_default = CodeVectorStore(
        collection_name="test_default_local",
        qdrant_path=":memory:",
    )
    assert store_default.provider == "local"
    assert store_default.vector_size == 384


def test_gemini_embedding_generation_mock():
    store = CodeVectorStore(
        collection_name="test_gemini_gen",
        qdrant_path=":memory:",
        provider="gemini",
        gemini_api_key="test-gemini-key",
    )

    mock_emb = MagicMock()
    mock_emb.values = [0.1] * 3072
    mock_resp = MagicMock()
    mock_resp.embeddings = [mock_emb]

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_resp
    store._gemini_client = mock_client

    # Single embedding
    vec = store.generate_embedding("def calculate_tax(): pass")
    assert len(vec) == 3072
    assert vec[0] == pytest.approx(0.1)
    assert store.embedding_ok is True

    # Check that output_dimensionality=3072 was passed in config
    call_args, call_kwargs = mock_client.models.embed_content.call_args
    assert call_kwargs["model"] == "text-embedding-004"
    assert call_kwargs["contents"] == "def calculate_tax(): pass"
    assert call_kwargs["config"].output_dimensionality == 3072

    # Batch embedding
    mock_emb2 = MagicMock()
    mock_emb2.values = [0.2] * 3072
    mock_batch_resp = MagicMock()
    mock_batch_resp.embeddings = [mock_emb, mock_emb2]
    mock_client.models.embed_content.return_value = mock_batch_resp

    batch_vecs = store.generate_embeddings_batch(["code 1", "code 2"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 3072
    assert len(batch_vecs[1]) == 3072
    assert batch_vecs[1][0] == pytest.approx(0.2)


def test_gemini_empty_or_failure_handling():
    store = CodeVectorStore(
        collection_name="test_gemini_err",
        qdrant_path=":memory:",
        provider="gemini",
        gemini_api_key=None,
    )
    # No client initialized because no key
    assert store.generate_embedding("") == []
    assert store.generate_embedding("some code") == []
    assert store.generate_embeddings_batch([]) == []
    assert store.generate_embeddings_batch(["code"]) == []


def test_gemini_upsert_and_search_3072d():
    store = CodeVectorStore(
        collection_name="test_gemini_search_3072",
        qdrant_path=":memory:",
        provider="gemini",
        gemini_api_key="mock-key",
    )

    mock_emb = MagicMock()
    mock_emb.values = [0.05] * 3072
    mock_resp = MagicMock()
    mock_resp.embeddings = [mock_emb]

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_resp
    store._gemini_client = mock_client

    # Upsert a code snippet with 3072D vector
    success = store.upsert_code_snippet(
        doc_id=1,
        code_snippet="def add(a, b): return a + b",
        metadata={"workspace_id": "ws-test", "file_path": "math.py"},
    )
    assert success is True

    # Search for it
    results = store.search_similar_code(query="addition", limit=3, workspace_id="ws-test")
    assert len(results) == 1
    assert results[0]["snippet"] == "def add(a, b): return a + b"
    assert results[0]["file_path"] == "math.py"

