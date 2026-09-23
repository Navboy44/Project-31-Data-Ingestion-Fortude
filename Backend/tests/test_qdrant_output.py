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
    def __init__(self, model_name):
        self.model_name = model_name

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
        client = FakeClient(url="http://qdrant:6333", api_key=None)
        fake_qdrant = types.SimpleNamespace(QdrantClient=lambda **kwargs: client, models=FakeModels)
        fake_fastembed = types.SimpleNamespace(TextEmbedding=FakeEmbedding)

        with patch.dict(
            sys.modules,
            {"qdrant_client": fake_qdrant, "fastembed": fake_fastembed},
        ), patch.dict("os.environ", {"QDRANT_URL": "http://qdrant:6333"}, clear=False):
            collection = qdrant_output.publish_documents(
                [{"document_id": "one", "content": "hello"}]
            )

        self.assertEqual(collection, "fortude_documents")
        self.assertEqual(client.kwargs["url"], "http://qdrant:6333")
        self.assertEqual(client.created["vectors_config"].kwargs["size"], 2)
        self.assertEqual(len(client.upserted["points"]), 1)
        self.assertEqual(client.upserted["points"][0].payload["text"], "hello")


if __name__ == "__main__":
    unittest.main()