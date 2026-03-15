"""
rag_provider.py
Pluggable RAG (Retrieval-Augmented Generation) provider abstraction.

Providers:
  - LtmRagProvider     : keyword search over MemoryManager LTM (SQLite)
  - LocalFileRagProvider: keyword search over local .txt/.md files (zero-dependency)
  - ChromaRagProvider  : semantic search via chromadb (optional dependency)
  - RagProviderRegistry: factory — get_provider(name, config) → RagProvider
"""

import logging
import os
from typing import List

logger = logging.getLogger(__name__)


class RagProvider:
    def search(
        self,
        query: str,
        collection: str = "",
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[str]:
        raise NotImplementedError


class LtmRagProvider(RagProvider):
    def __init__(self, memory_manager, session_id: str = ""):
        self.memory_manager = memory_manager
        self.session_id = session_id

    def search(
        self,
        query: str,
        collection: str = "",
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[str]:
        if self.memory_manager is None:
            return []
        try:
            entries = self.memory_manager.query_ltm(
                session_id=self.session_id,
                keyword=query,
                limit=top_k,
            )
            return [e if isinstance(e, str) else e.get("content", str(e)) for e in entries]
        except Exception as exc:
            logger.warning("LtmRagProvider search failed: %s", exc)
            return []


class LocalFileRagProvider(RagProvider):
    def __init__(self, directory: str = "."):
        self.directory = directory

    def search(
        self,
        query: str,
        collection: str = "",
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[str]:
        if not os.path.isdir(self.directory):
            return []

        # RAG-1: TF-IDF relevance scoring instead of plain keyword match
        import math
        import re as _re

        _tok = _re.compile(r'\w+')

        def _tokenize(text: str) -> List[str]:
            return [t.lower() for t in _tok.findall(text)]

        query_terms = set(_tokenize(query))
        if not query_terms:
            return []

        # Collect all paragraphs across files
        paragraphs: List[str] = []
        for fname in sorted(os.listdir(self.directory)):
            if not (fname.endswith(".txt") or fname.endswith(".md")):
                continue
            fpath = os.path.join(self.directory, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except OSError:
                continue
            for para in content.split("\n\n"):
                para = para.strip()
                if para:
                    paragraphs.append(para)

        if not paragraphs:
            return []

        # Build document-frequency counts for IDF
        N = len(paragraphs)
        df: dict = {}
        tokenized_paragraphs = [_tokenize(p) for p in paragraphs]
        for tokens in tokenized_paragraphs:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        # Score each paragraph using TF-IDF for query terms
        scored: List[tuple] = []
        for idx, (para, tokens) in enumerate(zip(paragraphs, tokenized_paragraphs)):
            if not tokens:
                continue
            score = 0.0
            tf_denom = len(tokens)
            for term in query_terms:
                tf = tokens.count(term) / tf_denom
                idf = math.log((N + 1) / (df.get(term, 0) + 1)) + 1.0
                score += tf * idf
            if score > 0:
                scored.append((score, idx))

        # Sort by score descending, apply threshold, return top_k
        scored.sort(key=lambda t: t[0], reverse=True)
        results: List[str] = []
        for score, idx in scored:
            if score_threshold > 0.0 and score < score_threshold:
                continue
            results.append(paragraphs[idx])
            if len(results) >= top_k:
                break

        return results


class ChromaRagProvider(RagProvider):
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory

    def search(
        self,
        query: str,
        collection: str = "",
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[str]:
        try:
            import chromadb
        except ImportError:
            logger.warning("chromadb not installed — pip install chromadb")
            return ["[ChromaDB not installed — pip install chromadb]"]

        try:
            client = chromadb.PersistentClient(path=self.persist_directory)
            col = client.get_or_create_collection(name=collection or "default")
            results = col.query(query_texts=[query], n_results=top_k)
            docs = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]

            if score_threshold > 0.0 and distances:
                docs = [d for d, dist in zip(docs, distances) if dist <= score_threshold]

            return [str(d) for d in docs]
        except Exception as exc:
            logger.warning("ChromaRagProvider search failed: %s", exc)
            return [f"[ChromaDB error: {exc}]"]


class RagProviderRegistry:
    @staticmethod
    def get_provider(
        provider_name: str,
        config: dict,
        memory_manager=None,
        session_id: str = "",
    ) -> RagProvider:
        name = (provider_name or "ltm").lower()
        if name in ("ltm", "local", ""):
            return LtmRagProvider(memory_manager, session_id)
        elif name == "local_files":
            directory = config.get("directory", ".")
            return LocalFileRagProvider(directory)
        elif name == "chroma":
            persist_dir = config.get("persist_directory", "./chroma_db")
            return ChromaRagProvider(persist_dir)
        else:
            logger.warning("Unknown RAG provider '%s', falling back to LTM", name)
            return LtmRagProvider(memory_manager, session_id)
