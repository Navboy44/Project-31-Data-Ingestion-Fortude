from contextlib import asynccontextmanager

import pytest
from app import main
from app.connectors import config_db
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config_db, "DB_PATH", tmp_path / "config.db")
    config_db.init_config_db()

    # disable lifespan to prevent SharePoint/Jira connector initialisation during tests
    @asynccontextmanager
    async def test_lifespan(app):
        yield

    monkeypatch.setattr(main.app.router, "lifespan_context", test_lifespan)
    with TestClient(main.app) as test_client:
        yield test_client


def test_create_pipeline(client):
    """Test creating a new pipeline with valid data"""
    response = client.post(
        "/api/config/pipelines",
        json={
            "name": "  Jira L3 Ticket  ",
            "connector_id": 2,
            "rule_ids": [2],
            "output_ids": [2, 3],
        },
    )

    assert response.status_code == 201
    pipeline = response.json()
    assert pipeline["name"] == "Jira L3 Ticket"
    assert pipeline["connector"] == {"id": 2, "name": "Jira"}
    assert pipeline["rules"] == [{"id": 2, "name": "L3 Ticket Rules"}]
    assert pipeline["outputs"] == [
        {"id": 2, "name": "MongoDB"},
        {"id": 3, "name": "Kafka"},
    ]
    assert config_db.get_pipeline(pipeline["id"]) == pipeline


def test_list_pipelines(client):
    """Test listing all pipelines"""
    pipeline1 = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [3])
    pipeline2 = config_db.add_pipeline("Infor Sales", 1, [1], [1])

    response = client.get("/api/config/pipelines")

    assert response.status_code == 200
    assert response.json() == [pipeline1, pipeline2]


def test_get_pipeline(client):
    """Test retrieving a specific pipeline by ID"""
    pipeline = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [3])
    response = client.get(f"/api/config/pipelines/{pipeline['id']}")

    assert response.status_code == 200
    assert response.json() == pipeline


def test_update_pipeline(client):
    """Test updating an existing pipeline with valid data"""
    pipeline = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [3])

    response = client.put(
        f"/api/config/pipelines/{pipeline['id']}",
        json={
            "name": "Infor Sales",
            "connector_id": 1,
            "rule_ids": [1, 2],
            "output_ids": [1],
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Infor Sales"
    assert updated["connector"] == {"id": 1, "name": "Infor"}
    assert updated["rules"] == [
        {"id": 1, "name": "Infor Sales Rules"},
        {"id": 2, "name": "L3 Ticket Rules"},
    ]
    assert updated["outputs"] == [{"id": 1, "name": "PostgreSQL"}]
    assert updated["created_at"] == pipeline["created_at"]
    assert config_db.get_pipeline(pipeline["id"]) == updated


def test_get_missing_pipeline(client):
    """Test retrieving a non-existent pipeline returns 404"""
    response = client.get("/api/config/pipelines/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Pipeline not found."}


def test_update_missing_pipeline(client):
    """Test updating a non-existent pipeline returns 404"""
    response = client.put(
        "/api/config/pipelines/999",
        json={
            "name": "Infor Sales",
            "connector_id": 1,
            "rule_ids": [1],
            "output_ids": [1],
        },
    )
    assert response.status_code == 404


def test_delete_missing_pipeline(client):
    """Test deleting a non-existent pipeline returns 404"""
    response = client.delete("/api/config/pipelines/999")
    assert response.status_code == 404


def test_create_duplicate_pipeline(client):
    """Test creating a pipeline with a name that already exists returns 409"""
    pipeline = config_db.add_pipeline("Infor Sales", 1, [1], [1])

    response = client.post(
        "/api/config/pipelines",
        json={
            "name": "Infor Sales",
            "connector_id": 1,
            "rule_ids": [1],
            "output_ids": [1],
        },
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    assert config_db.list_pipelines() == [pipeline]


def test_update_duplicate_pipeline(client):
    """Test updating a pipeline to a name that already exists returns 409"""
    config_db.add_pipeline("Infor Sales", 1, [1], [1])
    pipeline = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [3])

    response = client.put(
        f"/api/config/pipelines/{pipeline['id']}",
        json={
            "name": "Infor Sales",
            "connector_id": 1,
            "rule_ids": [1],
            "output_ids": [1],
        },
    )

    assert response.status_code == 409
    assert config_db.get_pipeline(pipeline["id"]) == pipeline


def test_blank_pipeline_name(client):
    """Test creating a pipeline with a blank name returns 422"""
    response = client.post(
        "/api/config/pipelines",
        json={
            "name": "   ",
            "connector_id": 1,
            "rule_ids": [1],
            "output_ids": [1],
        },
    )
    assert response.status_code == 422
    assert "name must not be empty" in response.json()["detail"]


def test_missing_rule_selection(client):
    """Test creating a pipeline without selecting any rules returns 422"""
    response = client.post(
        "/api/config/pipelines",
        json={
            "name": "Infor Sales",
            "connector_id": 1,
            "rule_ids": [],
            "output_ids": [1],
        },
    )
    assert response.status_code == 422
    assert "at least one rule" in response.json()["detail"]


def test_missing_output_selection(client):
    """Test creating a pipeline without selecting any outputs returns 422"""
    response = client.post(
        "/api/config/pipelines",
        json={
            "name": "Infor Sales",
            "connector_id": 1,
            "rule_ids": [1],
            "output_ids": [],
        },
    )
    assert response.status_code == 422
    assert "at least one output" in response.json()["detail"]


def test_invalid_pipeline_update(client):
    """Test that an invalid update does not change the existing pipeline"""
    pipeline = config_db.add_pipeline("Infor Sales", 1, [1], [1])

    response = client.put(
        f"/api/config/pipelines/{pipeline['id']}",
        json={
            "name": "Jira L3 Ticket",
            "connector_id": 999,
            "rule_ids": [1],
            "output_ids": [1],
        },
    )

    assert response.status_code == 422
    assert "Connector IDs not found" in response.json()["detail"]
    assert config_db.get_pipeline(pipeline["id"]) == pipeline


def test_connector_id_must_be_int(client):
    """Test that non-integer connector_id returns 422"""
    response = client.post(
        "/api/config/pipelines",
        json={
            "name": "Infor Sales",
            "connector_id": True,
            "rule_ids": [1],
            "output_ids": [1],
        },
    )
    assert response.status_code == 422
    assert config_db.list_pipelines() == []


def test_request_requires_all_fields(client):
    """Test that missing required fields returns 422"""
    response = client.post("/api/config/pipelines", json={"name": "Infor Sales"})
    assert response.status_code == 422
    assert config_db.list_pipelines() == []


def test_cannot_delete_referenced_connector(client):
    """Test that deleting a connector that is referenced by a pipeline in use returns 409"""
    config_db.add_pipeline("Infor Sales", 1, [1], [1])
    response = client.delete("/api/config/connectors/1")
    assert response.status_code == 409
    assert response.json() == {"detail": "Connector is used by a saved pipeline."}
    assert len(config_db.list_connectors()) == 3


def test_cannot_delete_referenced_rule(client):
    """Test that deleting a rule that is referenced by a pipeline in use returns 409"""
    config_db.add_pipeline("Infor Sales", 1, [1], [1])
    response = client.delete("/api/config/rules/1")
    assert response.status_code == 409
    assert response.json() == {"detail": "Rule is used by a saved pipeline."}
    assert len(config_db.list_rules()) == 3


def test_cannot_delete_referenced_output(client):
    """Test that deleting an output that is referenced by a pipeline in use returns 409"""
    config_db.add_pipeline("Infor Sales", 1, [1], [1])
    response = client.delete("/api/config/outputs/1")
    assert response.status_code == 409
    assert response.json() == {"detail": "Output target is used by a saved pipeline."}
    assert len(config_db.list_outputs()) == 4


def test_delete_unused_configuration(client):
    """Test that deleting a connector that is not referenced by any pipeline is successful"""
    response = client.delete("/api/config/connectors/1")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_missing_configuration(client):
    """Test that deleting a non-existent connector returns 404"""
    response = client.delete("/api/config/connectors/999")
    assert response.status_code == 404
