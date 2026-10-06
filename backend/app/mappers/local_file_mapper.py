from datetime import datetime, timezone
from pathlib import Path

from .document_chunker import create_document_chunks


def map_local_file_to_canonical(raw_file):
    """Map one local or SharePoint file into the shared document format."""
    file_name = raw_file.get("file_name")
    modified_at = raw_file.get("modified_at")
    if isinstance(modified_at, (int, float)):
        modified_at = datetime.fromtimestamp(modified_at, timezone.utc).isoformat()

    canonical_document = {
        "source": raw_file.get("source", "local_folder"),
        "document_id": file_name,
        "title": Path(file_name).stem,
        "file_name": file_name,
        "file_type": raw_file.get("file_type"),
        "file_size": raw_file.get("file_size"),
        "modified_at": modified_at,
        "author": raw_file.get("author"),
        "tags": [],
        "source_url": raw_file.get("source_url"),
        "version": raw_file.get("version"),
        "view_count": raw_file.get("view_count"),
        "content": raw_file.get("content"),
    }
    canonical_document["chunks"] = create_document_chunks(
        canonical_document["document_id"],
        canonical_document["file_type"],
        canonical_document["content"],
        raw_file.get("content_units"),
    )

    return canonical_document


def map_local_files_to_canonical(raw_files):
    """Map a collection of raw file records into canonical documents."""
    canonical_documents = []

    for raw_file in raw_files:
        canonical_document = map_local_file_to_canonical(raw_file)
        canonical_documents.append(canonical_document)

    return canonical_documents
