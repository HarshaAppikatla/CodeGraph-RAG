import pytest
from unittest.mock import MagicMock, patch
from qdrant_client.models import HnswConfigDiff, OptimizersConfigDiff, SearchParams

from backend.app.services.vector_store import CodeVectorStore
from backend.app.services.graph_store import Neo4jGraphStore
from backend.app.api.workspace import MAX_ZIP_BYTES
import backend.app.services.repo_ingestor as repo_ingestor


def test_qdrant_hnsw_and_payload_optimization():
    """Verify Qdrant configuration enables HNSW graph search and payloads are not duplicated."""
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = False
    
    with patch("backend.app.services.vector_store.QdrantClient", return_value=mock_client):
        vs = CodeVectorStore()
        
        # 1. Ensure collection was created with HnswConfigDiff and OptimizersConfigDiff
        assert mock_client.create_collection.called
        create_kwargs = mock_client.create_collection.call_args[1]
        assert "hnsw_config" in create_kwargs
        assert isinstance(create_kwargs["hnsw_config"], HnswConfigDiff)
        assert create_kwargs["hnsw_config"].full_scan_threshold == 100
        assert "optimizers_config" in create_kwargs
        assert isinstance(create_kwargs["optimizers_config"], OptimizersConfigDiff)
        assert create_kwargs["optimizers_config"].indexing_threshold == 100

        # 2. Test upsert payload only stores 'snippet' (not 'code' and 'content' 3x)
        mock_client.reset_mock()
        with patch.object(vs, "generate_embedding", return_value=[0.1] * 384):
            vs.upsert_code_snippet(
                doc_id=1,
                code_snippet="def add(a, b): return a + b",
                metadata={"file_path": "math.py", "language": "python", "workspace_id": "ws-123"}
            )
            assert mock_client.upsert.called
            points = mock_client.upsert.call_args[1]["points"]
            assert len(points) == 1
            payload = points[0].payload
            assert "snippet" in payload
            assert payload["snippet"] == "def add(a, b): return a + b"
            assert "code" not in payload, "Payload duplicated 'code' key unnecessarily"
            assert "content" not in payload, "Payload duplicated 'content' key unnecessarily"

        # 3. Test search uses SearchParams and adds backward-compatible aliases dynamically
        mock_point = MagicMock()
        mock_point.id = 1
        mock_point.score = 0.95
        mock_point.payload = {
            "snippet": "def add(a, b): return a + b",
            "file_path": "math.py",
            "language": "python",
            "workspace_id": "ws-123"
        }
        
        # When query_points is called
        mock_client.query_points.return_value = MagicMock(points=[mock_point])
        with patch.object(vs, "generate_embedding", return_value=[0.1] * 384):
            results = vs.search_similar_code("def add", workspace_id="ws-123", limit=5)
            
            # Verify search_params used
            assert mock_client.query_points.called
            qp_kwargs = mock_client.query_points.call_args[1]
            assert "search_params" in qp_kwargs
            assert isinstance(qp_kwargs["search_params"], SearchParams)
            assert qp_kwargs["search_params"].hnsw_ef == 64
            assert qp_kwargs["search_params"].exact is False
            
            # Verify dynamic aliasing in results
            assert len(results) == 1
            res = results[0]
            assert res["snippet"] == "def add(a, b): return a + b"
            assert res["code"] == "def add(a, b): return a + b"
            assert res["content"] == "def add(a, b): return a + b"


def test_neo4j_cypher_no_cartesian_product_and_labelled_match():
    """Verify Neo4j queries use labelled MATCH (no MATCH (n)) and CALL subqueries to prevent Cartesian explosive joins."""
    import inspect
    from backend.app.services.graph_store import Neo4jGraphStore

    source = inspect.getsource(Neo4jGraphStore)

    # 1. Check that unlabelled MATCH (target) or MATCH (n) without labels does not exist
    # (Except allowed generic deletion or where specifically labelled)
    assert "MATCH (target)\n" not in source, "Found unlabelled MATCH (target)"
    assert "MATCH (target) \n" not in source, "Found unlabelled MATCH (target)"
    assert "MATCH (target:Function|Class {ws: $ws})" in source

    # 2. Check that CALL { WITH target ... } subqueries are used for relationship traversal
    assert "CALL {" in source
    assert "WITH target" in source

    # 3. Check schema bootstrap indexes
    assert "CREATE INDEX entity_ws" in source
    assert "CREATE INDEX function_ws_short" in source
    assert "CREATE INDEX class_ws_short" in source
    assert "CREATE INDEX file_ws" in source


def test_zip_and_uncompressed_limits_raised():
    """Verify max upload limits are raised to handle large repos (1 GB zip, 2 GB uncompressed)."""
    assert MAX_ZIP_BYTES == 1024 * 1024 * 1024, f"Expected 1GB, got {MAX_ZIP_BYTES}"
    
    # Check repo_ingestor.ingest_zip_archive
    import inspect
    ingest_source = inspect.getsource(repo_ingestor.RepoIngestor.ingest_zip_archive)
    assert "MAX_UNCOMPRESSED_BYTES = 2048 * 1024 * 1024" in ingest_source
    assert "MAX_ZIP_ENTRIES = 50000" in ingest_source
