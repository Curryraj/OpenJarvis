"""FAISS dense retrieval memory backend.

Uses cosine similarity via inner-product search on L2-normalised
vectors.  Requires ``faiss-cpu`` (or ``faiss-gpu``) and ``numpy``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import faiss
except ImportError as _faiss_exc:
    raise ImportError(
        "faiss is required for FAISSMemory. Install it with: "
        "pip install faiss-cpu  (or faiss-gpu)"
    ) from _faiss_exc

from openjarvis.core.events import EventType, get_event_bus
from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import MemoryRegistry
from openjarvis.tools.storage._stubs import MemoryBackend, RetrievalResult
from openjarvis.tools.storage.embeddings import (
    Embedder,
    SentenceTransformerEmbedder,
)


@MemoryRegistry.register("faiss")
class FAISSMemory(MemoryBackend):
    """Dense retrieval backend powered by FAISS.

    Stores document embeddings in a ``faiss.IndexFlatIP`` index
    (inner-product, which equals cosine similarity when vectors
    are L2-normalised before insertion/search).
    """

    backend_id: str = "faiss"

    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        persist_dir: str | Path | None = None,
        db_path: str | Path | None = None,
        **_kwargs: Any,
    ) -> None:
        # ``db_path`` (and any other kwargs) are accepted for call-site
        # compatibility — the registry / server pass the sqlite-oriented
        # ``db_path``. FAISS persists to a *fixed* pair of files under the
        # config dir instead, so the CLI ``index`` process and the server's
        # backend share one on-disk store regardless of that argument.
        if embedder is None:
            embedder = SentenceTransformerEmbedder()
        self._embedder = embedder
        base = Path(persist_dir) if persist_dir else get_config_dir()
        self._index_path = base / "faiss_index.faiss"
        self._docs_path = base / "faiss_index.docs.json"
        self._db_path = self._index_path  # surfaced by ``memory stats``
        self._index = faiss.IndexFlatIP(self._embedder.dim())
        self._documents: Dict[str, Tuple[str, str, Dict[str, Any]]] = {}
        self._id_map: List[str] = []
        self._deleted: Set[str] = set()
        self._load()

    def _load(self) -> None:
        """Restore a previously persisted index + document store, if present."""
        if not (self._index_path.exists() and self._docs_path.exists()):
            return
        try:
            index = faiss.read_index(str(self._index_path))
            with open(self._docs_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError, RuntimeError):
            return  # corrupt/unreadable — start fresh rather than crash
        # Guard against embedder/dimension drift between runs.
        if index.d != self._embedder.dim():
            return
        self._index = index
        self._documents = {
            doc_id: (rec["content"], rec["source"], rec["metadata"])
            for doc_id, rec in payload.get("documents", {}).items()
        }
        self._id_map = list(payload.get("id_map", []))
        self._deleted = set(payload.get("deleted", []))

    def save(self) -> None:
        """Persist the index + document store to disk (atomic sidecar write)."""
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._index_path))
        payload = {
            "documents": {
                doc_id: {"content": c, "source": s, "metadata": m}
                for doc_id, (c, s, m) in self._documents.items()
            },
            "id_map": self._id_map,
            "deleted": sorted(self._deleted),
        }
        tmp = self._docs_path.with_suffix(self._docs_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        tmp.replace(self._docs_path)

    def close(self) -> None:
        """Flush to disk. Called by the CLI in a ``finally`` after indexing."""
        self.save()

    def count(self) -> int:
        """Live (non-deleted) document count — surfaced by ``memory stats``."""
        return len(self._documents) - len(self._deleted)

    # ------------------------------------------------------------------
    # MemoryBackend interface
    # ------------------------------------------------------------------

    def store(
        self,
        content: str,
        *,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Embed and store *content*, returning a unique doc id."""
        doc_id = uuid.uuid4().hex
        meta = metadata if metadata is not None else {}

        vec = self._embedder.embed([content])
        faiss.normalize_L2(vec)
        self._index.add(vec)

        self._documents[doc_id] = (content, source, meta)
        self._id_map.append(doc_id)

        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_STORE,
            {
                "backend": self.backend_id,
                "doc_id": doc_id,
                "source": source,
            },
        )
        return doc_id

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """Embed *query* and return the top-k most similar docs."""
        if not query.strip() or self._index.ntotal == 0:
            bus = get_event_bus()
            bus.publish(
                EventType.MEMORY_RETRIEVE,
                {
                    "backend": self.backend_id,
                    "query": query,
                    "num_results": 0,
                },
            )
            return []

        vec = self._embedder.embed([query])
        faiss.normalize_L2(vec)

        # Request more results to compensate for deleted docs
        k = min(
            top_k + len(self._deleted),
            self._index.ntotal,
        )
        scores, indices = self._index.search(vec, k)

        results: List[RetrievalResult] = []
        for score, idx in zip(scores[0].tolist(), indices[0].tolist()):
            if idx < 0:
                continue
            doc_id = self._id_map[idx]
            if doc_id in self._deleted:
                continue
            content, source, meta = self._documents[doc_id]
            results.append(
                RetrievalResult(
                    content=content,
                    score=float(score),
                    source=source,
                    metadata=dict(meta),
                )
            )
            if len(results) >= top_k:
                break

        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_RETRIEVE,
            {
                "backend": self.backend_id,
                "query": query,
                "num_results": len(results),
            },
        )
        return results

    def delete(self, doc_id: str) -> bool:
        """Soft-delete *doc_id*.  Return True if it existed."""
        if doc_id not in self._documents or doc_id in self._deleted:
            return False
        self._deleted.add(doc_id)
        return True

    def clear(self) -> None:
        """Reset the index and all internal storage, including on disk."""
        self._index.reset()
        self._documents.clear()
        self._id_map.clear()
        self._deleted.clear()
        for p in (self._index_path, self._docs_path):
            try:
                p.unlink()
            except OSError:
                pass


__all__ = ["FAISSMemory"]
