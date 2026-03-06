def test_version_endpoint(app_factory, tmp_path):
    version_file = tmp_path / "version.txt"
    version_file.write_text("2.5.7\n", encoding="utf-8")
    ctx = app_factory(APP_VERSION_FILE=str(version_file))
    response = ctx["client"].get("/version")
    assert response.status_code == 200
    assert response.json["version"] == "2.5.7"


def test_remote_http_redirects_to_https_by_default(app_ctx):
    client = app_ctx["client"]
    response = client.get("/version", base_url="http://example.com")
    assert response.status_code == 301
    assert response.headers["Location"] == "https://example.com/version"


def test_localhost_http_not_redirected(app_ctx):
    client = app_ctx["client"]
    response = client.get("/version", base_url="http://localhost")
    assert response.status_code == 200


def test_ssl_redirect_can_be_disabled(app_factory):
    ctx = app_factory(FORCE_SSL_REMOTE="false")
    response = ctx["client"].get("/version", base_url="http://example.com")
    assert response.status_code == 200


def test_stream_proxy_public_without_auth(app_ctx, monkeypatch):
    import app.routes.proxy as proxy_module

    def _timeout(_url, timeout=60):  # pragma: no cover - behavior validated by status code
        raise proxy_module.requests.Timeout()

    monkeypatch.setattr(proxy_module, "stream_request", _timeout)
    response = app_ctx["client"].get("/stream-proxy/http%3A%2F%2Fprovider%2Flive%2Fu%2Fp%2F1.ts")
    # Important assertion: proxy endpoint is reachable without auth/setup checks.
    assert response.status_code == 504


def test_stream_proxy_rewrites_hls_manifest_urls(app_ctx, monkeypatch):
    import app.routes.proxy as proxy_module

    class _Resp:
        def __init__(self):
            self.headers = {"Content-Type": "application/vnd.apple.mpegurl"}
            self.url = "http://provider/live/u/p/playlist.m3u8"
            self.text = (
                "#EXTM3U\n"
                "#EXT-X-KEY:METHOD=AES-128,URI=\"key.key\"\n"
                "seg1.ts\n"
                "/hlsr/token/seg2.ts\n"
                "http://cdn.example/seg3.ts\n"
            )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(proxy_module, "stream_request", lambda _url, timeout=60: _Resp())
    response = app_ctx["client"].get("/stream-proxy/http%3A%2F%2Fprovider%2Flive%2Fu%2Fp%2Fplaylist.m3u8")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "/stream-proxy/" in body
    assert "provider%2Flive%2Fu%2Fp%2Fseg1.ts" in body
    assert "provider%2Fhlsr%2Ftoken%2Fseg2.ts" in body
    assert "cdn.example%2Fseg3.ts" in body
    assert "provider%2Flive%2Fu%2Fp%2Fkey.key" in body


def test_stream_proxy_falls_back_on_https_port_80(app_ctx, monkeypatch):
    import app.routes.proxy as proxy_module

    calls = []

    class _Resp:
        def __init__(self):
            self.headers = {"Content-Type": "video/MP2T"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"TS"

    def _request(url, timeout=60):
        calls.append(url)
        if url.startswith("https://provider:80/"):
            raise proxy_module.requests.exceptions.SSLError("wrong version number")
        return _Resp()

    monkeypatch.setattr(proxy_module, "stream_request", _request)
    response = app_ctx["client"].get("/stream-proxy/https%3A%2F%2Fprovider%3A80%2Flive%2Fu%2Fp%2F1.ts")

    assert response.status_code == 200
    assert calls == [
        "https://provider:80/live/u/p/1.ts",
        "http://provider:80/live/u/p/1.ts",
    ]


def test_protected_route_requires_setup_then_login(app_ctx):
    client = app_ctx["client"]

    no_setup = client.get("/profiles")
    assert no_setup.status_code == 403
    assert "Setup Required" in no_setup.json["error"]

    setup = client.post("/auth/setup", json={"username": "admin", "password": "password123"})
    assert setup.status_code == 200
    client.post("/auth/logout")

    unauthorized = client.get("/profiles")
    assert unauthorized.status_code == 401
    assert unauthorized.json["error"] == "Unauthorized"


def test_categories_endpoint_with_mocked_upstream(admin_ctx, monkeypatch):
    client = admin_ctx["client"]
    api = admin_ctx["api"]

    monkeypatch.setattr(
        api,
        "validate_xtream_credentials",
        lambda url, username, password: ({"user_info": {}, "server_info": {}}, None, None),
    )
    monkeypatch.setattr(
        api,
        "fetch_categories_and_channels",
        lambda url, username, password, include_vod, include_all_streams=False: (
            [{"category_id": "1", "category_name": "News", "content_type": "live"}],
            [{"stream_id": "99", "name": "News A", "category_id": "1", "content_type": "live"}],
            None,
            None,
        ),
    )

    response = client.get("/categories?url=http://provider&username=u&password=p")
    assert response.status_code == 200
    assert len(response.json["categories"]) == 1
    assert len(response.json["streams"]) == 1


def test_subscription_endpoint_with_mocked_upstream(admin_ctx, monkeypatch):
    client = admin_ctx["client"]
    api = admin_ctx["api"]

    monkeypatch.setattr(
        api,
        "validate_xtream_credentials",
        lambda url, username, password: (
            {
                "user_info": {
                    "username": "u",
                    "status": "Active",
                    "exp_date": "1773553663",
                    "created_at": "1663220863",
                    "is_trial": "0",
                    "active_cons": "2",
                    "max_connections": "5",
                    "allowed_output_formats": ["m3u8", "ts"],
                },
                "server_info": {
                    "url": "host",
                    "port": "826",
                    "https_port": "8443",
                    "server_protocol": "http",
                    "timezone": "America/New_York",
                    "timestamp_now": 1772774362,
                    "time_now": "2026-03-06 00:19:22",
                },
            },
            None,
            None,
        ),
    )

    response = client.get("/subscription?url=http://provider&username=u&password=p")
    assert response.status_code == 200
    assert response.json["status"] == "Active"
    assert response.json["server_port"] == 826


def test_stream_link_endpoint_with_mocked_validation(admin_ctx, monkeypatch):
    client = admin_ctx["client"]
    api = admin_ctx["api"]

    monkeypatch.setattr(
        api,
        "validate_xtream_credentials",
        lambda url, username, password: (
            {
                "user_info": {"username": username, "password": password},
                "server_info": {"url": "provider.host", "port": "80", "server_protocol": "http"},
            },
            None,
            None,
        ),
    )

    response = client.get("/stream-link?url=http://provider&username=u&password=p&stream_id=72&content_type=live&extension=ts")
    assert response.status_code == 200
    assert "/stream-proxy/" in response.json["url"]
    assert "http%3A%2F%2Fprovider.host%3A80%2Flive%2Fu%2Fp%2F72.ts" in response.json["url"]


def test_stream_link_secure_request_still_uses_provider_url(admin_ctx, monkeypatch):
    client = admin_ctx["client"]
    api = admin_ctx["api"]

    monkeypatch.setattr(
        api,
        "validate_xtream_credentials",
        lambda url, username, password: (
            {
                "user_info": {"username": username, "password": password},
                "server_info": {
                    "url": "provider.host",
                    "port": "80",
                    "https_port": "443",
                    "server_protocol": "http",
                },
            },
            None,
            None,
        ),
    )

    response = client.get(
        "/stream-link?url=http://provider&username=u&password=p&stream_id=72&content_type=live&extension=ts",
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    assert "/stream-proxy/" in response.json["url"]
    assert "http%3A%2F%2Fprovider.host%3A80%2Flive%2Fu%2Fp%2F72.ts" in response.json["url"]
    assert response.json["candidates"][0] == response.json["url"]


def test_public_m3u_endpoint_without_auth(app_ctx, monkeypatch):
    client = app_ctx["client"]
    api = app_ctx["api"]

    monkeypatch.setattr(
        api,
        "validate_xtream_credentials",
        lambda url, username, password: (
            {
                "user_info": {"username": username, "password": password},
                "server_info": {"url": "provider.host", "port": "80"},
            },
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        api,
        "fetch_categories_and_channels",
        lambda url, username, password, include_vod: (
            [{"category_id": "1", "category_name": "News"}],
            [{"stream_id": "1", "name": "News A", "category_id": "1", "content_type": "live"}],
            None,
            None,
        ),
    )
    monkeypatch.setattr(api, "generate_m3u_playlist", lambda **kwargs: "#EXTM3U\n")

    response = client.get("/m3u?url=http://provider&username=u&password=p")
    assert response.status_code == 200
    assert response.data.decode("utf-8").startswith("#EXTM3U")


def test_public_xmltv_endpoint_without_auth(app_ctx, monkeypatch):
    client = app_ctx["client"]
    api = app_ctx["api"]

    monkeypatch.setattr(
        api,
        "validate_xtream_credentials",
        lambda url, username, password: (
            {
                "user_info": {"username": username, "password": password},
                "server_info": {"url": "provider.host", "port": "80"},
            },
            None,
            None,
        ),
    )
    monkeypatch.setattr(api, "build_xmltv_from_config", lambda cfg: ("<?xml version='1.0'?><tv></tv>", None, None))

    response = client.get("/xmltv?url=http://provider&username=u&password=p")
    assert response.status_code == 200
    assert "<tv>" in response.data.decode("utf-8")


def test_parse_and_match_helpers():
    from app.utils import group_matches, parse_group_list

    assert parse_group_list("News,Sports, Movies ") == ["News", "Sports", "Movies"]
    assert group_matches("Sky Sports 1", "*sports*")
    assert group_matches("US News", "news")
    assert not group_matches("Movies", "Sports")
