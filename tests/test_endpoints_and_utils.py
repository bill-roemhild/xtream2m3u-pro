def test_version_endpoint(app_factory):
    ctx = app_factory(APP_VERSION="2.5.7")
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
    assert response.json["url"].endswith("/live/u/p/72.ts")


def test_stream_link_secure_request_prefers_https_candidate(admin_ctx, monkeypatch):
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
    assert response.json["url"] == "https://provider.host:443/live/u/p/72.ts"
    assert response.json["candidates"][0] == "https://provider.host:443/live/u/p/72.ts"


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
