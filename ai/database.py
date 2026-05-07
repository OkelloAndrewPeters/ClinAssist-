"""
database.py — ChromaDB vector store for Uganda Clinical Guidelines RAG
"""

import os

os.environ["HF_HUB_OFFLINE"] = "1"  # use cached model, no network check


import json
import logging
from typing import Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CHROMA_PATH   = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION    = "uganda_clinical_guidelines"
EMBED_MODEL   = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K         = int(os.getenv("TOP_K", "5"))


# ── Singleton helpers ─────────────────────────────────────────────────────────

_client:     Optional[chromadb.PersistentClient]  = None
_collection: Optional[chromadb.Collection]        = None
_embedder:   Optional[SentenceTransformer]        = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info(f"ChromaDB initialised at {CHROMA_PATH}")
    return _client


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        _collection = _get_client().get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Collection '{COLLECTION}' ready — {_collection.count()} chunks loaded")
    return _collection


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info(f"Loading embedding model: {EMBED_MODEL}")
        _embedder = SentenceTransformer(EMBED_MODEL)
        logger.info("Embedding model ready")
    return _embedder


# ── Public API ─────────────────────────────────────────────────────────────────

def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings. Returns list of float vectors."""
    return _get_embedder().encode(texts, show_progress_bar=False).tolist()


def add_chunks(chunks: list[dict]) -> int:
    """
    Insert document chunks into ChromaDB.

    Each chunk dict must have:
        id       : str  — unique identifier e.g. "ucg_ch04_p087_0"
        text     : str  — the chunk text
        metadata : dict — {document, chapter, page, source_file}

    Returns the number of chunks added.
    """
    if not chunks:
        return 0

    col = _get_collection()
    ids       = [c["id"]       for c in chunks]
    texts     = [c["text"]     for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # Skip chunks already in the DB
    existing = set(col.get(ids=ids)["ids"])
    new = [c for c in chunks if c["id"] not in existing]
    if not new:
        logger.info("All chunks already in DB — skipping")
        return 0

    new_ids  = [c["id"]       for c in new]
    new_docs = [c["text"]     for c in new]
    new_meta = [c["metadata"] for c in new]
    new_embs = embed(new_docs)

    col.add(ids=new_ids, documents=new_docs, metadatas=new_meta, embeddings=new_embs)
    logger.info(f"Added {len(new)} new chunks to '{COLLECTION}'")
    return len(new)


def query(text: str, top_k: int = TOP_K) -> list[dict]:
    """
    Retrieve the top_k most relevant chunks for a query string.

    Returns a list of dicts:
        { text, metadata, distance, id }
    """
    col = _get_collection()
    if col.count() == 0:
        logger.warning("Collection is empty — no results returned")
        return []

    query_embedding = embed([text])[0]
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for i, doc in enumerate(results["documents"][0]):
        output.append({
            "text":     doc,
            "metadata": results["metadatas"][0][i],
            "distance": round(results["distances"][0][i], 4),
            "id":       results["ids"][0][i],
        })
    return output


def collection_stats() -> dict:
    """Return basic stats about what's in the vector store."""
    col = _get_collection()
    count = col.count()
    if count == 0:
        return {"total_chunks": 0, "documents": []}

    # Sample up to 500 to get unique document list
    sample = col.get(limit=count, include=["metadatas"])
    docs_seen = {}
    for meta in sample["metadatas"]:
        doc = meta.get("document", "Unknown")
        docs_seen[doc] = docs_seen.get(doc, 0) + 1

    return {
        "total_chunks": count,
        "documents": [{"name": k, "chunks": v} for k, v in docs_seen.items()],
    }


def delete_collection() -> None:
    """Wipe the entire collection. Use with care."""
    global _collection
    _get_client().delete_collection(COLLECTION)
    _collection = None
    logger.warning(f"Collection '{COLLECTION}' deleted")


def collection_is_empty() -> bool:
    return _get_collection().count() == 0