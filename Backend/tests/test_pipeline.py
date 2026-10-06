import sqlite3

import pytest

from backend.app.connectors import config_db

# Seed data:
# connectors: ["Infor", "Jira", "SharePoint"]
# rules: ["Infor Sales Rules", "L3 Ticket Rules", "Knowledge Base Rules"]
# output_targets: ["PostgreSQL", "MongoDB", "Kafka", "Vector Database"]


# setup temp SQLite db for each test
@pytest.fixture
def database(monkeypatch, tmp_path):
    monkeypatch.setattr(config_db, "DB_PATH", tmp_path / "config.db")
    config_db.init_config_db()
    return config_db.DB_PATH


# pipeline schema tests
def test_pipeline_create_table(database):
    """test pipeline table creation"""
    conn = sqlite3.connect(database)

    try:
        row = conn.execute(
            """SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'pipelines'"""
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


@pytest.mark.parametrize("name", ["", "    "])
def test_pipeline_name_not_empty(database, name):
    """test pipeline name validity (cannot be empty or whitespace)"""
    conn = sqlite3.connect(database)

    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO pipelines (name, connector_id, created_at, updated_at) VALUES (?, ?, ?, ?)""",
                (name, 1, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
            )
            conn.commit()
    finally:
        conn.close()


def test_pipeline_name_not_unique(database):
    """test preventing duplicate pipeline names"""
    conn = sqlite3.connect(database)

    try:
        conn.execute(
            """INSERT INTO pipelines (name, connector_id, created_at, updated_at) VALUES (?, ?, ?, ?)""",
            ("Pipeline 2", 1, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO pipelines (name, connector_id, created_at, updated_at) VALUES (?, ?, ?, ?)""",
                (
                    "Pipeline 2",
                    1,
                    "2024-01-01T00:00:00+00:00",
                    "2024-01-01T00:00:00+00:00",
                ),
            )
    finally:
        conn.close()


def test_pipeline_connector_must_exist(database):
    """test preventing insertion of a pipeline with a non-existent connector_id"""
    conn = sqlite3.connect(database)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO pipelines (name, connector_id, created_at, updated_at) VALUES (?, ?, ?, ?)""",
                (
                    "Pipeline 3",
                    32,
                    "2024-01-01T00:00:00+00:00",
                    "2024-01-01T00:00:00+00:00",
                ),
            )
    finally:
        conn.close()


def test_pipeline_delete_successful(database):
    """test deleting a pipeline that is not in use, removing rule/output associations"""
    conn = sqlite3.connect(database)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        cursor = conn.execute(
            """INSERT INTO pipelines (name, connector_id, created_at, updated_at) VALUES (?, ?, ?, ?)""",
            ("Pipeline 4", 1, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
        )

        pipeline_id = cursor.lastrowid
        conn.execute(
            """INSERT INTO pipeline_rules (pipeline_id, rule_id) VALUES (?, ?)""",
            (pipeline_id, 1),
        )

        conn.execute(
            """INSERT INTO pipeline_outputs (pipeline_id, output_id) VALUES (?, ?)""",
            (pipeline_id, 1),
        )

        conn.commit()

        conn.execute(
            """DELETE FROM pipelines WHERE id = ?""",
            (pipeline_id,),
        )

        conn.commit()

        row = conn.execute(
            """SELECT * FROM pipelines WHERE id = ?""",
            (pipeline_id,),
        ).fetchone()

        assert row is None

        rule_association = conn.execute(
            """SELECT * FROM pipeline_rules WHERE pipeline_id = ?""",
            (pipeline_id,),
        ).fetchone()

        assert rule_association is None

        output_association = conn.execute(
            """SELECT * FROM pipeline_outputs WHERE pipeline_id = ?""",
            (pipeline_id,),
        ).fetchone()

        assert output_association is None

    finally:
        conn.close()


def test_delete_connector_while_in_use(database):
    """test deleting a connector that is in use by a pipeline, should raise an error and prevent the action"""
    conn = sqlite3.connect(database)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        conn.execute(
            """INSERT INTO pipelines (name, connector_id, created_at, updated_at) VALUES (?, ?, ?, ?)""",
            ("Pipeline 5", 1, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
        )

        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """DELETE FROM connectors WHERE id = ?""",
                (1,),
            )
            conn.commit()

        row = conn.execute(
            """SELECT id FROM connectors WHERE id = ?""",
            (1,),
        ).fetchone()

        assert row is not None

    finally:
        conn.close()


def test_pipeline_has_updated_at_field(database):
    """test that updated_at field exists in pipeline tables"""
    conn = sqlite3.connect(database)

    try:
        columns = conn.execute("""PRAGMA table_info(pipelines)""").fetchall()

        column_names = [col[1] for col in columns]

        assert "updated_at" in column_names

    finally:
        conn.close()


# pipeline CRUD tests
def test_add_pipeline(database):
    """test pipeline creation"""
    pipeline = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [2, 3])

    assert pipeline["name"] == "Jira L3 Ticket"
    assert pipeline["connector"] == {"id": 2, "name": "Jira"}
    assert pipeline["rules"] == [{"id": 2, "name": "L3 Ticket Rules"}]
    assert pipeline["outputs"] == [
        {"id": 2, "name": "MongoDB"},
        {"id": 3, "name": "Kafka"},
    ]


def test_get_pipeline(database):
    """test pipeline retrieval"""
    pipeline = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [2, 3])
    saved_pipeline = config_db.get_pipeline(pipeline["id"])
    assert saved_pipeline == pipeline


def test_list_pipelines(database):
    """test listing all pipelines"""
    pipeline1 = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [2, 3])
    pipeline2 = config_db.add_pipeline("Infor Sales", 1, [1], [1])

    pipelines = config_db.list_pipelines()

    assert pipelines == [pipeline1, pipeline2]


def test_update_pipeline(database, monkeypatch):
    """test updating pipeline"""
    monkeypatch.setattr(config_db, "_now_iso", lambda: "2026-09-17T01:00:00+00:00")
    pipeline = config_db.add_pipeline("Jira L3 Ticket", 2, [2], [3])
    monkeypatch.setattr(config_db, "_now_iso", lambda: "2026-09-17T02:00:00+00:00")

    updated_pipeline = config_db.update_pipeline(
        pipeline["id"], "Infor Sales", 1, [1, 2], [1, 2]
    )

    assert updated_pipeline["id"] == pipeline["id"]
    assert updated_pipeline["name"] == "Infor Sales"
    assert updated_pipeline["connector"] == {"id": 1, "name": "Infor"}
    assert updated_pipeline["rules"] == [
        {"id": 1, "name": "Infor Sales Rules"},
        {"id": 2, "name": "L3 Ticket Rules"},
    ]
    assert updated_pipeline["outputs"] == [
        {"id": 1, "name": "PostgreSQL"},
        {"id": 2, "name": "MongoDB"},
    ]
    assert updated_pipeline["created_at"] == "2026-09-17T01:00:00+00:00"
    assert updated_pipeline["updated_at"] == "2026-09-17T02:00:00+00:00"
    assert config_db.get_pipeline(pipeline["id"]) == updated_pipeline


def test_delete_pipeline(database):
    """test deleting pipeline"""
    pipeline = config_db.add_pipeline("Infor Sales", 1, [1], [3])

    deleted = config_db.delete_pipeline(pipeline["id"])

    assert deleted is True
    assert config_db.get_pipeline(pipeline["id"]) is None


def test_add_pipeline_blank_name(database):
    """test that a pipeline cannot be created with a blank name"""
    with pytest.raises(ValueError, match="Pipeline name must not be empty"):
        config_db.add_pipeline("   ", 1, [2], [3])

    assert config_db.list_pipelines() == []


def test_pipeline_requires_rule(database):
    """test that a pipeline must select at least one rule"""
    with pytest.raises(ValueError, match="at least one rule"):
        config_db.add_pipeline("Infor Sales", 1, [], [3])

    assert config_db.list_pipelines() == []


def test_pipeline_requires_output(database):
    """test that a pipeline must select at least one output"""
    with pytest.raises(ValueError, match="at least one output"):
        config_db.add_pipeline("Infor Sales", 1, [1], [])

    assert config_db.list_pipelines() == []


def test_add_pipeline_non_existent_connector(database):
    """test that a pipeline cannot be created with a non-existent connector"""
    with pytest.raises(ValueError, match="Connector IDs not found"):
        config_db.add_pipeline("Infor Sales", 999, [1], [3])

    assert config_db.list_pipelines() == []


def test_add_pipeline_non_existent_rule(database):
    """test that a pipeline cannot be created with a non-existent rule"""
    with pytest.raises(ValueError, match="Rule IDs not found"):
        config_db.add_pipeline("Infor Sales", 1, [999], [3])

    assert config_db.list_pipelines() == []


def test_add_pipeline_non_existent_output(database):
    """test that a pipeline cannot be created with a non-existent output"""
    with pytest.raises(ValueError, match="Output IDs not found"):
        config_db.add_pipeline("Infor Sales", 1, [1], [999])

    assert config_db.list_pipelines() == []


def test_pipeline_duplicate_name(database):
    """test that a pipeline cannot be created with a duplicate name"""
    pipeline = config_db.add_pipeline("Infor Sales", 1, [1], [3])

    with pytest.raises(config_db.PipelineDuplicateNameError, match="already exists"):
        config_db.add_pipeline("Infor Sales", 1, [1], [1])

    assert config_db.list_pipelines() == [pipeline]
