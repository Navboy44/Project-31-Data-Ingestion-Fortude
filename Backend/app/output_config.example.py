"""Example configuration for output destinations.

Copy this file to output_config.py and set values for your environment.
"""

QDRANT_URL = "http://localhost:6333"
QDRANT_API_KEY: str | None = None
QDRANT_COLLECTION = "fortude_documents"
QDRANT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
