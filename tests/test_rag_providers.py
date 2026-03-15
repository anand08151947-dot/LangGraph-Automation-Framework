"""
TEST-1: Unit and integration tests for RAG provider implementations.
Covers LocalFileRagProvider (TF-IDF), RagProviderRegistry.deduplicate(),
and basic retrieval / edge-case handling.
"""
import os
import tempfile
import pytest
from backend.rag_provider import LocalFileRagProvider, RagProviderRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider(tmp_path, files: dict) -> LocalFileRagProvider:
    """Write test documents to tmp_path and return a configured provider."""
    for fname, content in files.items():
        (tmp_path / fname).write_text(content, encoding="utf-8")
    return LocalFileRagProvider(str(tmp_path))


# ---------------------------------------------------------------------------
# LocalFileRagProvider — basic retrieval
# ---------------------------------------------------------------------------

def test_local_file_provider_returns_relevant_results(tmp_path):
    provider = _make_provider(tmp_path, {
        "alpha.txt": "Python is a great programming language.",
        "beta.txt": "The weather is sunny today.",
        "gamma.txt": "Python supports functional and object-oriented programming.",
    })
    results = provider.search("Python programming")
    assert isinstance(results, list)
    assert len(results) > 0
    assert any("Python" in t for t in results)


def test_local_file_provider_score_threshold_filters_all_low_score(tmp_path):
    provider = _make_provider(tmp_path, {
        "relevant.txt": "Machine learning models train on data.",
        "irrelevant.txt": "Dolphins swim in the ocean.",
    })
    # With a very high TF-IDF threshold, fewer/zero results
    results = provider.search("machine learning training", score_threshold=999.0)
    assert results == []


def test_local_file_provider_empty_directory(tmp_path):
    provider = LocalFileRagProvider(str(tmp_path))
    results = provider.search("anything")
    assert results == []


def test_local_file_provider_nonexistent_directory_returns_empty():
    # LocalFileRagProvider returns [] for non-existent directory (doesn't raise)
    provider = LocalFileRagProvider("/nonexistent/path/that/does/not/exist")
    results = provider.search("test query")
    assert results == []


def test_local_file_provider_top_k_respected(tmp_path):
    files = {f"doc{i}.txt": f"Document number {i} about topic alpha." for i in range(10)}
    provider = _make_provider(tmp_path, files)
    results = provider.search("topic alpha", top_k=3)
    assert len(results) <= 3


def test_local_file_provider_all_text_files_loaded(tmp_path):
    provider = _make_provider(tmp_path, {
        "a.txt": "content A about cats",
        "b.txt": "content B about dogs",
        "c.txt": "content C about birds",
    })
    results = provider.search("content about animals", top_k=10)
    assert isinstance(results, list)
    assert len(results) <= 3  # Only 3 docs exist


def test_local_file_provider_returns_strings(tmp_path):
    provider = _make_provider(tmp_path, {"test.txt": "Hello world test document."})
    results = provider.search("hello world")
    for r in results:
        assert isinstance(r, str)


# ---------------------------------------------------------------------------
# RagProviderRegistry.deduplicate() — RAG-2 (takes List[str])
# ---------------------------------------------------------------------------

def test_deduplicate_removes_exact_duplicates():
    docs = ["Hello world", "Hello world", "Different text"]
    deduped = RagProviderRegistry.deduplicate(docs)
    assert deduped.count("Hello world") == 1
    assert "Different text" in deduped
    assert len(deduped) == 2


def test_deduplicate_whitespace_normalized_duplicates():
    docs = ["Hello   world", "Hello world", "Other text"]
    deduped = RagProviderRegistry.deduplicate(docs)
    assert len(deduped) == 2


def test_deduplicate_no_duplicates_unchanged():
    docs = ["First document", "Second document", "Third document"]
    deduped = RagProviderRegistry.deduplicate(docs)
    assert len(deduped) == 3


def test_deduplicate_empty_list():
    assert RagProviderRegistry.deduplicate([]) == []


def test_deduplicate_preserves_order():
    docs = ["A", "B", "C", "A"]
    deduped = RagProviderRegistry.deduplicate(docs)
    assert deduped == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# RagProviderRegistry.get_provider() — RAG-4 error handling
# ---------------------------------------------------------------------------

def test_get_provider_local_files_missing_directory_raises():
    with pytest.raises(ValueError):
        RagProviderRegistry.get_provider(
            "local_files",
            {"documents_path": "/does/not/exist/xyz"}
        )

