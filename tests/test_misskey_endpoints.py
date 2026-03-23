"""Tests for Misskey /api/endpoints and /api/endpoint."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.misskey_endpoints import MISSKEY_ENDPOINTS


class TestApiEndpoints:

    def test_returns_list(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_all_strings(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        for item in resp.json():
            assert isinstance(item, str), f"Expected str, got {type(item)}: {item}"

    def test_sorted(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        data = resp.json()
        assert data == sorted(data), "Endpoint list should be sorted"

    def test_no_duplicates(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        data = resp.json()
        assert len(data) == len(set(data)), "No duplicates should exist"

    def test_contains_core_endpoints(self, client: TestClient):
        """主要エンドポイントが含まれていること"""
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        data = set(resp.json())
        required = {
            "meta",
            "endpoints",
            "stats",
            "i",
            "i/update",
            "i/notifications",
            "notes/create",
            "notes/delete",
            "notes/show",
            "notes/timeline",
            "notes/local-timeline",
            "notes/global-timeline",
            "notes/hybrid-timeline",
            "notes/reactions/create",
            "notes/reactions/delete",
            "notes/search",
            "users/show",
            "users/search",
            "users/followers",
            "users/following",
            "following/create",
            "following/delete",
            "blocking/create",
            "blocking/delete",
            "muting/create",
            "muting/delete",
            "notifications/mark-all-as-read",
            "drive/files",
            "drive/files/create",
            "emojis",
            "antennas/create",
            "antennas/list",
            "channels/create",
            "channels/timeline",
            "clips/create",
            "clips/list",
            "admin/meta",
            "admin/roles/list",
            "admin/emoji/list",
        }
        missing = required - data
        assert not missing, f"Missing required endpoints: {missing}"

    def test_contains_admin_endpoints(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        data = set(resp.json())
        admin_eps = [e for e in data if e.startswith("admin/")]
        assert len(admin_eps) >= 30, f"Should have 30+ admin endpoints, got {len(admin_eps)}"

    def test_contains_i_endpoints(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        data = set(resp.json())
        i_eps = [e for e in data if e.startswith("i/") or e == "i"]
        assert len(i_eps) >= 10, f"Should have 10+ i/ endpoints, got {len(i_eps)}"

    def test_contains_notes_endpoints(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        data = set(resp.json())
        notes_eps = [e for e in data if e.startswith("notes/") or e == "notes"]
        assert len(notes_eps) >= 15, f"Should have 15+ notes endpoints, got {len(notes_eps)}"

    def test_upstream_response_used_when_available(self, client: TestClient):
        """上流が応答した場合はその値を返す"""
        upstream_list = ["meta", "notes/create", "users/show"]
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = upstream_list
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_resp)
            resp = client.post("/api/endpoints", json={})
        assert resp.json() == upstream_list

    def test_fallback_when_upstream_returns_empty(self, client: TestClient):
        """上流が空リストを返した場合はハードコードリストを使う"""
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = []
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_resp)
            resp = client.post("/api/endpoints", json={})
        # 空リストの場合はフォールバック
        assert len(resp.json()) > 0

    def test_total_count_reasonable(self, client: TestClient):
        """エンドポイント総数が妥当な範囲にあること（Misskey は 150〜300 程度）"""
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoints", json={})
        count = len(resp.json())
        assert 150 <= count <= 400, f"Endpoint count {count} out of expected range"

    def test_hardcoded_list_has_no_duplicates(self):
        """ハードコードリスト自体に重複がないこと"""
        assert len(MISSKEY_ENDPOINTS) == len(set(MISSKEY_ENDPOINTS)), \
            "MISSKEY_ENDPOINTS has duplicates"

    def test_hardcoded_list_no_leading_slash(self):
        """エンドポイント名にスラッシュ始まりがないこと"""
        for ep in MISSKEY_ENDPOINTS:
            assert not ep.startswith("/"), f"Endpoint should not start with /: {ep}"


class TestApiEndpoint:

    def test_returns_200(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"name": "meta", "params": []}
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_resp)
            resp = client.post("/api/endpoint", json={"endpoint": "meta"})
        assert resp.status_code == 200

    def test_fallback_on_upstream_error(self, client: TestClient):
        with patch("app.api.misskey_endpoints.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("unreachable"))
            resp = client.post("/api/endpoint", json={"endpoint": "meta"})
        assert resp.status_code == 200
        assert resp.json() == {}
