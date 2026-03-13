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

        words = [w.lower() for w in query.split() if w]
        matches: List[str] = []

        for fname in os.listdir(self.directory):
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
                if not para:
                    continue
                lower_para = para.lower()
                if any(w in lower_para for w in words):
                    matches.append(para)
                    if len(matches) >= top_k:
                        return matches

        return matches[:top_k]


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
