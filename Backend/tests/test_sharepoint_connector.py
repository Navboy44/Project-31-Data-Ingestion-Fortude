from app.connectors.sharepoint_connector import read_sharepoint_delta


class FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, delta_pages):
        self.delta_pages = delta_pages
        self.get_urls = []

    def post(self, url, data, timeout):
        return FakeResponse({"access_token": "token"})

    def get(self, url, headers, timeout):
        self.get_urls.append(url)
        if "/sites/example.sharepoint.com:/sites/team" in url:
            return FakeResponse({"id": "site-id"})
        if url.endswith("/sites/site-id/drives"):
            return FakeResponse({"value": [{"id": "drive-id", "name": "Documents"}]})
        if url.endswith("/drives/drive-id/root"):
            return FakeResponse({"id": "root-id"})
        if url.endswith("/items/txt-id/content"):
            return FakeResponse(content=b"hello")
        if url in self.delta_pages:
            return FakeResponse(self.delta_pages[url])
        raise AssertionError(f"Unexpected URL: {url}")


def set_sharepoint_env(monkeypatch):
    settings = {
        "TENANT_ID": "tenant",
        "CLIENT_ID": "client",
        "CLIENT_SECRET": "secret",
        "SHAREPOINT_HOST": "example.sharepoint.com",
        "SHAREPOINT_SITE_PATH": "/sites/team/",
        "SHAREPOINT_LIBRARY": "documents",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)


def test_first_delta_sync_follows_pagination_and_keeps_last_item(monkeypatch):
    set_sharepoint_env(monkeypatch)
    first = "https://graph.microsoft.com/v1.0/drives/drive-id/root/delta"
    next_url = "https://graph.microsoft.com/page-2"
    session = FakeSession({
        first: {
            "value": [{
                "id": "txt-id", "name": "old.txt", "file": {},
                "parentReference": {"id": "root-id"},
            }],
            "@odata.nextLink": next_url,
        },
        next_url: {
            "value": [
                {
                    "id": "txt-id", "name": "notes.txt", "file": {}, "size": 5,
                    "parentReference": {"id": "root-id"},
                    "lastModifiedDateTime": "2026-08-24T01:02:03Z",
                },
                {
                    "id": "nested", "name": "nested.txt", "file": {},
                    "parentReference": {"id": "folder-id"},
                },
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta-token",
        },
    })

    result = read_sharepoint_delta(session=session)

    assert result["delta_link"] == "https://graph.microsoft.com/delta-token"
    assert [change["item_id"] for change in result["changes"]] == ["txt-id", "nested"]
    assert result["changes"][0]["record"]["content"] == "hello"
    assert result["changes"][1]["supported"] is False
    assert first in session.get_urls and next_url in session.get_urls


def test_subsequent_delta_sync_uses_saved_delta_link(monkeypatch):
    set_sharepoint_env(monkeypatch)
    saved = "https://graph.microsoft.com/saved-delta"
    session = FakeSession({
        saved: {
            "value": [{"id": "gone-id", "deleted": {"state": "deleted"}}],
            "@odata.deltaLink": "https://graph.microsoft.com/new-delta",
        }
    })

    result = read_sharepoint_delta(saved, session=session)

    assert saved in session.get_urls
    assert result["changes"][0]["deleted"] is True
    assert result["delta_link"].endswith("new-delta")
