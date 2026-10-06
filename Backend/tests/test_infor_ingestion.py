import asyncio
import json

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException, Request, FastAPI
from pydantic import ValidationError

from backend.app import main
from app.connectors import Infor_API_connector as infor
from app.mappers.infor_mapper import map_infor_response


@pytest.mark.parametrize(
    "order_type,record",
    [
        (
            "purchase",
            {
                "PNLI": "1",
                "PNLS": "0",
                "ITNO": "ITEM",
                "ORQA": "10",
                "RVQA": "5",
                "IVQA": "2",
            },
        ),
        (
            "customer",
            {
                "PONR": "1",
                "POSX": "0",
                "ITNO": "ITEM",
                "ORQT": "10",
                "DLQT": "5",
                "IVQT": "2",
            },
        ),
    ],
)
def test_ingests_order_and_records_actual_output(
    monkeypatch, tmp_path, order_type, record
):
    async def fetch(kind, number, request):
        assert (kind, number) == (order_type, "123")
        return {
            "nrOfFailedTransactions": 0,
            "results": [{"records": [record]}],
        }

    history = []

    monkeypatch.setattr(main, "fetch_order_lines", fetch)
    monkeypatch.setattr(main, "OUTPUT_FOLDER", tmp_path)
    monkeypatch.setattr(
        main,
        "add_history_entry",
        lambda **entry: history.append(entry),
    )

    result = asyncio.run(
        main.ingest_local_folder(
            main.IngestionRequest(
                connector="Infor Sales",
                order_type=order_type,
                order_number=" 123 ",
                rule="Infor Sales Rules",
                outputs="PostgreSQL",
                mapper="Sales Schema Mapper",
            ),
            BackgroundTasks(),
            Request({"type": "http", "app": main.app}),
        )
    )

    assert result["processed"] == 1

    documents = json.loads((tmp_path / f"infor_{order_type}_123.json").read_text())

    assert documents[0]["content"]["ITNO"] == "ITEM"
    assert documents[0]["tags"] == ["sales"]
    assert history[0]["outputs"] == "Local JSON"
    assert history[0]["status"] == "completed"


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"order_type": "customer", "order_number": "../bad"},
        {"order_type": "invalid", "order_number": "123"},
    ],
)
def test_invalid_infor_input(fields):
    with pytest.raises(ValidationError):
        main.IngestionRequest(
            connector="Infor Sales",
            **fields,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "nrOfFailedTransactions": 0,
            "results": [
                {
                    "errorMessage": "invalid order",
                    "records": [],
                }
            ],
        },
        {
            "nrOfFailedTransactions": 0,
            "results": [{"records": None}],
        },
        {
            "nrOfFailedTransactions": 0,
        },
    ],
)
def test_rejects_failed_or_malformed_response(payload):
    with pytest.raises(ValueError):
        map_infor_response(
            payload,
            "customer",
            "test_tenant",
            "123",
        )


def test_empty_order_is_valid():
    payload = {
        "nrOfFailedTransactions": 0,
        "results": [{"records": []}],
    }

    assert (
        map_infor_response(
            payload,
            "purchase",
            "test_tenant",
            "123",
        )
        == []
    )


@pytest.mark.parametrize(
    "kind,transaction,param",
    [
        ("customer", "OIS100MI", "ORNO"),
        ("purchase", "PPS200MI", "PUNO"),
    ],
)
def test_infor_authentication_and_transaction(monkeypatch, kind, transaction, param):
    for name in [
        "CLIENT_ID",
        "CLIENT_SECRET",
        "USERNAME",
        "PASSWORD",
    ]:
        monkeypatch.setenv(
            "INFOR_" + name,
            "test-value",
        )

    monkeypatch.setenv(
        "INFOR_TOKEN_URL",
        "https://infor.test/token",
    )
    monkeypatch.setenv(
        "INFOR_BASE_URL",
        "https://infor.test/m3",
    )

    def handler(request):
        if request.url.path == "/token":
            assert request.method == "POST"
            return httpx.Response(
                200,
                json={"access_token": "test-token"},
            )

        assert request.url.path == f"/m3/{transaction}/LstLine"
        assert request.url.params[param] == "123"
        assert request.headers["Authorization"] == "Bearer test-token"

        return httpx.Response(
            200,
            json={"results": [{"records": []}]},
        )

    real_client = httpx.AsyncClient

    monkeypatch.setattr(
        infor.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    async def run():
        app = FastAPI()

        async with infor.httpx.AsyncClient() as client:
            app.state.client = client

            return await infor.fetch_order_lines(
                kind,
                "123",
                Request(
                    {
                        "type": "http",
                        "app": app,
                    }
                ),
            )

    assert asyncio.run(run()) == {"results": [{"records": []}]}


def test_upstream_failure_does_not_write_output_or_history(monkeypatch, tmp_path):
    async def fail(*args):
        raise HTTPException(
            502,
            "Infor request failed.",
        )

    monkeypatch.setattr(
        main,
        "fetch_order_lines",
        fail,
    )
    monkeypatch.setattr(
        main,
        "OUTPUT_FOLDER",
        tmp_path,
    )
    monkeypatch.setattr(
        main,
        "add_history_entry",
        lambda **kwargs: pytest.fail("Unexpected history"),
    )

    with pytest.raises(HTTPException):
        asyncio.run(
            main.ingest_local_folder(
                main.IngestionRequest(
                    connector="Infor Sales",
                    order_type="purchase",
                    order_number="123",
                ),
                BackgroundTasks(),
                Request(
                    {
                        "type": "http",
                        "app": main.app,
                    }
                ),
            )
        )

    assert list(tmp_path.iterdir()) == []


def test_http_validation_and_registered_raw_route(monkeypatch):
    from fastapi.testclient import TestClient

    class Client:
        async def post(self, url, **kwargs):
            return httpx.Response(
                200,
                json={"access_token": "test-token"},
                request=httpx.Request("POST", url),
            )

        async def get(self, url, **kwargs):
            return httpx.Response(
                200,
                json={"records": [{"ORNO": kwargs["params"]["ORNO"]}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setenv(
        "INFOR_BASE_URL",
        "https://infor.test/m3",
    )

    monkeypatch.setattr(
        main.app.state,
        "client",
        Client(),
        raising=False,
    )

    client = TestClient(main.app)

    response = client.post(
        "/api/ingest/local-folder",
        json={"connector": "Infor Sales"},
    )

    assert response.status_code == 422

    response = client.get("/infor/customer-orders/123/lines")

    assert response.status_code == 200
    assert response.json()["records"][0]["ORNO"] == "123"


def test_missing_credentials_report_configuration_error(
    monkeypatch,
):
    from unittest.mock import AsyncMock

    for name in [
        "CLIENT_ID",
        "CLIENT_SECRET",
        "USERNAME",
        "PASSWORD",
    ]:
        monkeypatch.setenv(
            "INFOR_" + name,
            "test-value",
        )

    monkeypatch.delenv(
        "INFOR_TOKEN_URL",
        raising=False,
    )
    monkeypatch.delattr(
        infor.connector_config,
        "INFOR_TOKEN_URL",
        raising=False,
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(infor.get_infor_token(AsyncMock()))

    assert error.value.status_code == 503
    assert "INFOR_TOKEN_URL" in error.value.detail
