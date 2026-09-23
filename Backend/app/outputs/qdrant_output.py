"""Qdrant output for canonical ingestion documents."""

import hashlib
import json
import os
import uuid
from collections.abc import Iterable
from typing import Any


DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def _document_text(document: dict[str, Any]) -> str:
    """Create searchable text while retaining the complete document as payload."""
    preferred_fields = ("title", "file_name", "summary", "content", "description")
    values = [str(document[field]) for field in preferred_fields if document.get(field)]
    if values:
        return "\n\n".join(values)
    return json.dumps(document, sort_keys=True, ensure_ascii=False)


def _point_id(document: dict[str, Any], text: str) -> str:
    identity = (
        document.get("document_id")
        or document.get("ticket_key")
        or document.get("file_name")
        or text
    )
    identity_hash = hashlib.sha1(str(identity).encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity_hash))


def publish_documents(documents: Iterable[dict[str, Any]]) -> str:
    """Embed and upsert canonical documents into the configured Qdrant collection."""
    try:
        from qdrant_client import QdrantClient, models
        from fastembed import TextEmbedding
    except ImportError as error:
        raise RuntimeError(
            "Vector Database output requires qdrant-client[fastembed]."
        ) from error

    documents = list(documents)
    if not documents:
        return os.getenv("QDRANT_COLLECTION", "fortude_documents")

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY") or None
    collection = os.getenv("QDRANT_COLLECTION", "fortude_documents")
    model_name = os.getenv("QDRANT_EMBEDDING_MODEL", DEFAULT_MODEL)
    client = QdrantClient(url=url, api_key=api_key)
    embedder = TextEmbedding(model_name=model_name)

    texts = [_document_text(document) for document in documents]
    vectors = list(embedder.embed(texts))
    vector_size = len(vectors[0])

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    points = [
        models.PointStruct(
            id=_point_id(document, text),
            vector=vector,
            payload={"text": text, "document": document},
        )
        for document, text, vector in zip(documents, texts, vectors)
    ]
    client.upsert(collection_name=collection, points=points, wait=True)
    return collection