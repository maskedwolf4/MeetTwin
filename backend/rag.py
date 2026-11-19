"""Persistent FAISS retrieval for profile knowledge and chat memories."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from resources import rag_documents


class FaissRAG:
    """Small file-backed vector store, safe to use from concurrent requests."""

    def __init__(self, directory: str | Path, model_name: str | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.index_path = self.directory / "conversations.faiss"
        self.metadata_path = self.directory / "conversations.json"
        self.model = SentenceTransformer(
            model_name or os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        )
        self.dimension = self.model.get_sentence_embedding_dimension()
        self.lock = threading.RLock()
        self.index: faiss.IndexIDMap2
        self.records: dict[str, dict[str, Any]]
        self._load()
        self._refresh_profile_documents()

    @staticmethod
    def _record_id(key: str) -> int:
        # FAISS uses signed 64-bit IDs. Keep the hash in that safe range.
        return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") & ((1 << 63) - 1)

    def _load(self) -> None:
        if self.index_path.exists() and self.metadata_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            self.records = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            return
        self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(self.dimension))
        self.records = {}

    def _persist(self) -> None:
        temporary_index = self.index_path.with_suffix(".tmp")
        temporary_metadata = self.metadata_path.with_suffix(".tmp")
        faiss.write_index(self.index, str(temporary_index))
        temporary_metadata.write_text(json.dumps(self.records, ensure_ascii=False), encoding="utf-8")
        temporary_index.replace(self.index_path)
        temporary_metadata.replace(self.metadata_path)

    def _embed(self, text: str) -> np.ndarray:
        return self.model.encode([text], normalize_embeddings=True).astype("float32")

    @staticmethod
    def _chunks(text: str, size: int = 900, overlap: int = 150) -> list[str]:
        clean = re.sub(r"\s+", " ", text).strip()
        if not clean:
            return []
        return [clean[start : start + size] for start in range(0, len(clean), size - overlap)]

    def _refresh_profile_documents(self) -> None:
        """Replace profile chunks so edits to resources.py's source files take effect."""
        with self.lock:
            profile_keys = [
                key for key, record in self.records.items()
                if record["metadata"].get("kind") == "profile"
            ]
            if profile_keys:
                ids = np.array([self.records[key]["id"] for key in profile_keys], dtype="int64")
                self.index.remove_ids(ids)
                for key in profile_keys:
                    del self.records[key]
                self._persist()

        for document in rag_documents():
            for number, chunk in enumerate(self._chunks(document["text"])):
                self.upsert(
                    key=f'{document["id"]}:{number}',
                    text=chunk,
                    metadata={"kind": "profile", "source": document["source"]},
                )

    def upsert(self, key: str, text: str, metadata: dict[str, Any]) -> None:
        """Add or replace one document. Metadata is stored alongside the FAISS ID."""
        with self.lock:
            vector_id = self._record_id(key)
            if key in self.records:
                self.index.remove_ids(np.array([vector_id], dtype="int64"))
            self.index.add_with_ids(self._embed(text), np.array([vector_id], dtype="int64"))
            self.records[key] = {"id": vector_id, "text": text, "metadata": metadata}
            self._persist()

    def remember(self, session_id: str, role: str, content: str, timestamp: str) -> None:
        key = f"chat:{session_id}:{timestamp}:{role}"
        self.upsert(
            key=key,
            text=content,
            metadata={"kind": "conversation", "session_id": session_id, "role": role, "timestamp": timestamp},
        )

    def retrieve(self, query: str, session_id: str, limit: int = 6) -> list[dict[str, Any]]:
        """Return relevant profile chunks plus memories only from this session."""
        with self.lock:
            if not self.records:
                return []
            # Pull extra candidates because other visitors' conversation data is never eligible.
            distances, ids = self.index.search(self._embed(query), min(len(self.records), limit * 8))
            by_id = {record["id"]: record for record in self.records.values()}
            results: list[dict[str, Any]] = []
            for score, vector_id in zip(distances[0], ids[0]):
                record = by_id.get(int(vector_id))
                if not record or float(score) < 0.20:
                    continue
                metadata = record["metadata"]
                if metadata["kind"] == "conversation" and metadata["session_id"] != session_id:
                    continue
                results.append({**record, "score": round(float(score), 3)})
                if len(results) == limit:
                    break
            return results


def format_retrieval_context(records: list[dict[str, Any]]) -> str:
    if not records:
        return "No relevant retrieved information was found. Say you do not have that information rather than guessing."
    sections = []
    for record in records:
        metadata = record["metadata"]
        label = "past conversation" if metadata["kind"] == "conversation" else metadata["source"]
        sections.append(f"[{label}]\n{record['text']}")
    return "\n\n".join(sections)
