import sys
import types
import unittest
from unittest.mock import patch

from app.outputs.kafka_output import publish_documents


class KafkaOutputTests(unittest.TestCase):
    @patch.dict(
        sys.modules,
        {"kafka": types.SimpleNamespace(KafkaProducer=lambda **kwargs: FakeKafkaProducer())},
    )
    def test_publishes_each_document_to_configured_topic(self):
        with patch.dict(
            "os.environ",
            {
                "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
                "KAFKA_TOPIC": "test.ingestion",
            },
        ):
            topic = publish_documents([{"document_id": "one"}, {"document_id": "two"}])

        producer = FakeKafkaProducer.instances[-1]
        self.assertEqual(topic, "test.ingestion")
        self.assertEqual(len(producer.messages), 2)
        self.assertEqual(producer.messages[0], ("test.ingestion", {"document_id": "one"}))
        self.assertTrue(producer.flushed)
        self.assertTrue(producer.closed)


class FakeKafkaProducer:
    instances = []

    def __init__(self):
        self.messages = []
        self.flushed = False
        self.closed = False
        self.__class__.instances.append(self)

    def send(self, topic, value):
        self.messages.append((topic, value))

    def flush(self):
        self.flushed = True

    def close(self):
        self.closed = True


if __name__ == "__main__":
    unittest.main()