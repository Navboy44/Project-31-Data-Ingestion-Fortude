"""Check optional Infor configuration in a fresh Python process."""
import os
from pathlib import Path
import subprocess
import sys


def test_app_imports_without_infor_credentials_and_requests_fail_clearly():
    script = '''
import asyncio
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from fastapi import HTTPException
with patch("dotenv.load_dotenv", return_value=False):
    from app import main, connector_config
    from app.connectors import Infor_API_connector as connector
    assert connector_config.INFOR_TENANT is None
    client = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(client=client)))
    async def check():
        for operation in [connector.get_infor_token(client),
                          connector.get_purchase_order_lines("1", request),
                          connector.get_customer_order_lines("1", request),
                          connector.get_inventory_by_order("1", "780", request, "001", "ITEM")]:
            try:
                await operation
            except HTTPException as exc:
                assert exc.status_code == 503
                assert "Infor configuration missing" in exc.detail
            else:
                raise AssertionError("Expected missing-configuration error")
    asyncio.run(check())
    client.post.assert_not_called()
    client.get.assert_not_called()
'''
    env = {key: value for key, value in os.environ.items() if not key.startswith('INFOR_')}
    completed = subprocess.run([sys.executable, '-c', script],
                               cwd=Path(__file__).parents[1], env=env,
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
