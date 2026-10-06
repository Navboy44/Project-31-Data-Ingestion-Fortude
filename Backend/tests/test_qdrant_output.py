import sys
import types
import unittest
from unittest.mock import patch

from backend.app.outputs import qdrant_output


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.created = None
        self.upserted = None

    def collection_exists(self, collection):
        return False

    def create_collection(self, **kwargs):
        self.created = kwargs

    def upsert(self, **kwargs):
        self.upserted = kwargs


class FakeEmbedding:
    last_model_name = None

    def __init__(self, model_name):
        self.model_name = model_name
        type(self).last_model_name = model_name

    def embed(self, texts):
        return [[float(index), 1.0] for index, _ in enumerate(texts)]


class FakeModels:
    class Distance:
        COSINE = "Cosine"

    class VectorParams:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class PointStruct:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


class QdrantOutputTests(unittest.TestCase):
    def test_embeds_and_upserts_documents(self):
        clients = []

        def create_client(**kwargs):
            client = FakeClient(**kwargs)
            clients.append(client)
            return client

        fake_qdrant = types.SimpleNamespace(QdrantClient=create_client, models=FakeModels)
        fake_fastembed = types.SimpleNamespace(TextEmbedding=FakeEmbedding)

        with patch.multiple(
            qdrant_output.output_config,
            QDRANT_URL="http://qdrant:6333",
            QDRANT_API_KEY="test-api-key",
            QDRANT_COLLECTION="test_documents",
            QDRANT_EMBEDDING_MODEL="test-model",
        ), patch.dict(
            sys.modules,
            {"qdrant_client": fake_qdrant, "fastembed": fake_fastembed},
        ):
            collection = qdrant_output.publish_documents(
                [{"document_id": "one", "content": "hello"}]
            )

        client = clients[0]
        self.assertEqual(collection, "test_documents")
        self.assertEqual(client.kwargs["url"], "http://qdrant:6333")
        self.assertEqual(client.kwargs["api_key"], "test-api-key")
        self.assertEqual(client.upserted["collection_name"], "test_documents")
        self.assertEqual(FakeEmbedding.last_model_name, "test-model")
        self.assertEqual(client.created["vectors_config"].kwargs["size"], 2)
        self.assertEqual(len(client.upserted["points"]), 1)
        self.assertEqual(client.upserted["points"][0].payload["text"], "hello")


if __name__ == "__main__":
    unittest.main()