import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module, mcp_agent
from app.main import app
from app.database import Base, get_db


SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "app": "akatosh"}



def test_user_registration_and_login():

    reg_response = client.post("/register", json={
        "email": "brewer@akatosh.com",
        "password": "securepassword123"
    })
    assert reg_response.status_code == 201
    assert reg_response.json()["email"] == "brewer@akatosh.com"


    dup_response = client.post("/register", json={
        "email": "brewer@akatosh.com",
        "password": "securepassword123"
    })
    assert dup_response.status_code == 400


    login_response = client.post("/login", data={
        "username": "brewer@akatosh.com",
        "password": "securepassword123"
    })
    assert login_response.status_code == 200
    data = login_response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_unauthorized_access():
    response = client.get("/features/")
    assert response.status_code == 401


def test_google_oauth_requires_configuration(monkeypatch):
    for setting in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "SECRET_KEY",
    ):
        monkeypatch.delenv(setting, raising=False)

    response = client.get("/auth/google/login")
    assert response.status_code == 503


def test_google_oauth_callback_issues_bearer_token(monkeypatch):
    class FakeGoogleClient:
        async def authorize_access_token(self, request):
            return {
                "userinfo": {
                    "email": "google-user@example.com",
                    "email_verified": True,
                }
            }

    monkeypatch.setattr(
        main_module, "get_google_oauth_client", lambda: FakeGoogleClient()
    )
    response = client.get("/auth/google/callback", follow_redirects=False)
    assert response.status_code == 303
    assert "#access_token=" in response.headers["location"]

    token = parse_qs(urlparse(response.headers["location"]).fragment)["access_token"][0]
    protected = client.get("/features/", headers={"Authorization": f"Bearer {token}"})
    assert protected.status_code == 200


def test_landing_page_seo_and_public_config():
    page = client.get("/")
    assert page.status_code == 200
    assert "name=\"description\"" in page.text
    assert client.get("/robots.txt").status_code == 200
    assert "Sitemap: http://testserver/sitemap.xml" in client.get(
        "/robots.txt"
    ).text
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "<loc>http://testserver/</loc>" in sitemap.text
    assert "property=\"og:url\"" in page.text
    config = client.get("/config.js")
    assert config.status_code == 200
    assert "googleAnalyticsId" in config.text
    assert "SECRET_KEY" not in config.text


def test_ai_assistant_streams_sse_when_enabled(monkeypatch):
    headers = register_and_login("assistant@example.com")
    monkeypatch.setenv("FEATURE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    admin_headers = {**headers, "X-Feature-Admin-Token": "test-admin-token"}
    enabled = client.put(
        "/features/enable_ai_suggestions",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert enabled.status_code == 200

    async def fake_gemini_stream(prompt, tenant_id):
        assert prompt == "How do I dry hop an IPA?"
        assert tenant_id
        yield 'event: progress\ndata: {"message": "Connecting to Gemini…"}\n\n'
        yield 'event: progress\ndata: {"message": "Gemini is generating a response…"}\n\n'
        yield 'data: {"text": "Add hops"}\n\n'
        yield 'data: {"text": " during fermentation."}\n\n'
        yield "event: done\ndata: {}\n\n"

    monkeypatch.setattr(main_module, "stream_gemini_response", fake_gemini_stream)
    response = client.post(
        "/api/assistant/stream",
        headers=headers,
        json={"prompt": "How do I dry hop an IPA?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert "Gemini is generating a response" in response.text
    assert '"text": "Add hops"' in response.text
    assert '"text": " during fermentation."' in response.text
    assert "event: done" in response.text



@patch("app.worker.process_recipe_file_task.delay")
@patch("app.worker.send_telegram_notification_task.delay")
def test_create_and_get_recipes(mock_telegram, mock_file_proc):

    client.post("/register", json={"email": "brewer@akatosh.com", "password": "password123"})
    login_res = client.post("/login", data={"username": "brewer@akatosh.com", "password": "password123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/recipes/",
        data={
            "title": "Akatosh Imperial Stout",
            "style": "Stout",
            "abv": 10.5,
            "ibu": 65,
            "description": "Rich dark stout with chocolate notes"
        },
        headers=headers
    )
    assert create_res.status_code == 201
    assert create_res.json()["title"] == "Akatosh Imperial Stout"

    list_res = client.get("/recipes/?skip=0&limit=5", headers=headers)
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Akatosh Imperial Stout"


def register_and_login(email: str) -> dict[str, str]:
    client.post("/register", json={"email": email, "password": "password123"})
    login_response = client.post(
        "/login", data={"username": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def test_json_recipe_crud_is_tenant_scoped():
    assert client.get("/api/recipes/").status_code == 401
    first_tenant_headers = register_and_login("first@example.com")
    second_tenant_headers = register_and_login("second@example.com")

    created = client.post(
        "/api/recipes/",
        headers=first_tenant_headers,
        json={
            "title": "Citra Pale Ale",
            "style": "Pale Ale",
            "abv": 5.2,
            "ibu": 42,
            "ingredients": [
                {"name": "Citra", "amount_grams": 25, "ingredient_type": "Hop"}
            ],
        },
    )
    assert created.status_code == 201
    recipe_id = created.json()["id"]
    assert created.json()["ingredients"][0]["name"] == "Citra"

    assert client.get(
        f"/api/recipes/{recipe_id}", headers=first_tenant_headers
    ).status_code == 200
    assert client.get(
        f"/api/recipes/{recipe_id}", headers=second_tenant_headers
    ).status_code == 404

    update = client.put(
        f"/api/recipes/{recipe_id}",
        headers=first_tenant_headers,
        json={"title": "Updated Pale Ale", "ingredients": []},
    )
    assert update.status_code == 200
    assert update.json()["title"] == "Updated Pale Ale"
    assert update.json()["ingredients"] == []

    other_tenant_list = client.get(
        "/api/recipes/", headers=second_tenant_headers
    )
    assert other_tenant_list.status_code == 200
    assert other_tenant_list.json()["total"] == 0

    deleted = client.delete(
        f"/api/recipes/{recipe_id}", headers=first_tenant_headers
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/api/recipes/{recipe_id}", headers=first_tenant_headers
    ).status_code == 404


def test_json_recipe_list_is_cached_and_invalidated(monkeypatch):
    cache = {}

    def fake_set(key, value, ex):
        assert ex == 60
        cache[key] = value

    def fake_delete(key):
        cache.pop(key, None)

    monkeypatch.setattr(main_module.redis_client, "get", lambda key: cache.get(key))
    monkeypatch.setattr(main_module.redis_client, "set", fake_set)
    monkeypatch.setattr(
        main_module.redis_client, "scan_iter", lambda pattern: iter(list(cache))
    )
    monkeypatch.setattr(main_module.redis_client, "delete", fake_delete)
    monkeypatch.setattr(main_module, "send_telegram_notification", lambda *args: None)
    headers = register_and_login("cached@example.com")

    created = client.post(
        "/api/recipes/",
        headers=headers,
        json={"title": "Cached Ale", "style": "Pale Ale", "abv": 5.2, "ibu": 42},
    )
    assert created.status_code == 201

    list_url = "/api/recipes/?skip=0&limit=10"
    first_list = client.get(list_url, headers=headers)
    assert first_list.status_code == 200
    assert first_list.json()["items"][0]["title"] == "Cached Ale"
    assert len(cache) == 1
    assert next(iter(cache)).startswith("recipes_api_tenant_")

    other_tenant_headers = register_and_login("other-cached@example.com")
    other_tenant_list = client.get(list_url, headers=other_tenant_headers)
    assert other_tenant_list.status_code == 200
    assert other_tenant_list.json()["total"] == 0
    assert len(cache) == 2

    updated = client.put(
        f"/api/recipes/{created.json()['id']}",
        headers=headers,
        json={"title": "Updated Cached Ale"},
    )
    assert updated.status_code == 200
    assert not cache

    refreshed_list = client.get(list_url, headers=headers)
    assert refreshed_list.status_code == 200
    assert refreshed_list.json()["items"][0]["title"] == "Updated Cached Ale"


def test_json_recipe_creation_queues_telegram_notification(monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://test-broker")
    queued_notifications = []
    monkeypatch.setattr(
        main_module.send_telegram_notification_task,
        "delay",
        lambda *args: queued_notifications.append(args),
    )
    headers = register_and_login("telegram@example.com")

    response = client.post(
        "/api/recipes/",
        headers=headers,
        json={"title": "Telegram Ale", "style": "Pale Ale", "abv": 5.2, "ibu": 42},
    )

    assert response.status_code == 201
    assert queued_notifications == [("Telegram Ale", "Pale Ale", 5.2)]


def test_json_recipe_creation_sends_telegram_without_queue(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    sent_notifications = []
    monkeypatch.setattr(
        main_module,
        "send_telegram_notification",
        lambda *args: sent_notifications.append(args),
    )
    headers = register_and_login("telegram-sync@example.com")

    response = client.post(
        "/api/recipes/",
        headers=headers,
        json={"title": "Direct Ale", "style": "Pale Ale", "abv": 5.2, "ibu": 42},
    )

    assert response.status_code == 201
    assert sent_notifications == [("Direct Ale", "Pale Ale", 5.2)]


def test_feature_flags_are_tenant_scoped_and_admin_managed(monkeypatch):
    headers = register_and_login("features@example.com")
    feature_url = "/features/premium_analytics"

    defaults = client.get("/features/", headers=headers)
    assert defaults.status_code == 200
    assert defaults.json()["flags"]["premium_analytics"] is True

    monkeypatch.setenv("FEATURE_ADMIN_TOKEN", "test-admin-token")
    rejected = client.put(
        feature_url,
        headers={**headers, "X-Feature-Admin-Token": "incorrect-token"},
        json={"enabled": False},
    )
    assert rejected.status_code == 403

    changed = client.put(
        feature_url,
        headers={**headers, "X-Feature-Admin-Token": "test-admin-token"},
        json={"enabled": False},
    )
    assert changed.status_code == 200
    assert changed.json()["enabled"] is False

    updated = client.get("/features/", headers=headers)
    assert updated.json()["flags"]["premium_analytics"] is False


def test_ai_feature_default_tracks_gemini_configuration(monkeypatch):
    headers = register_and_login("ai-default@example.com")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    unconfigured = client.get("/features/", headers=headers)
    assert unconfigured.json()["flags"]["enable_ai_suggestions"] is False

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    configured = client.get("/features/", headers=headers)
    assert configured.json()["flags"]["enable_ai_suggestions"] is True


def test_gemini_stream_uses_current_default_model(monkeypatch):
    class FakeResponse:
        is_error = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"Brew answer"}]}}]}'

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, **kwargs):
            assert url.endswith("/v1beta/models/gemini-3.6-flash:streamGenerateContent")
            return FakeResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("MCP_AGENT_ENABLED", raising=False)
    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)

    async def collect():
        return [
            chunk
            async for chunk in main_module.stream_gemini_response("Ales", "tenant-a")
        ]

    result = asyncio.run(collect())
    assert 'data: {"text": "Brew answer"}\n\n' in result
    assert result[-1] == "event: done\ndata: {}\n\n"
    assert any("Gemini is generating" in event for event in result)


def test_gemini_payment_error_points_to_billing(monkeypatch):
    class FakeResponse:
        is_error = True
        status_code = 402

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aread(self):
            return b""

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.delenv("MCP_AGENT_ENABLED", raising=False)
    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)

    async def collect():
        return [
            chunk
            async for chunk in main_module.stream_gemini_response("Ales", "tenant-a")
        ]

    result = "".join(asyncio.run(collect()))
    assert "HTTP 402" in result
    assert "prepaid credits may be depleted" in result
    assert "Google AI Studio billing page" in result


def test_gemini_assistant_calls_tenant_mcp_tools(monkeypatch):
    class FakeMcpSession:
        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="list_recipes",
                        description="List recipes",
                        inputSchema={
                            "type": "object",
                            "properties": {"limit": {"type": "integer"}},
                        },
                    )
                ]
            )

        async def call_tool(self, name, arguments):
            assert name == "list_recipes"
            assert arguments == {"skip": 0, "limit": 10}
            return SimpleNamespace(
                isError=False,
                structuredContent=None,
                content=[SimpleNamespace(text='{"items": [{"title": "Pale Ale"}]}')],
            )

    class FakeResponse:
        is_error = False

        def __init__(self, chunk):
            self.chunk = chunk

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            yield f"data: {json.dumps(self.chunk)}"

    class FakeClient:
        payloads = []
        chunks = [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "list_recipes",
                                        "args": {"skip": 0, "limit": 10},
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "candidates": [
                    {"content": {"parts": [{"text": "Your Pale Ale recipe is ready."}]}}
                ]
            },
        ]

        def __init__(self, **kwargs):
            self.chunk_index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, **kwargs):
            self.payloads.append(kwargs["json"])
            chunk = self.chunks[self.chunk_index]
            self.chunk_index += 1
            return FakeResponse(chunk)

    connected_tenants = []
    session = FakeMcpSession()

    @asynccontextmanager
    async def fake_connect_to_mcp(tenant_id):
        connected_tenants.append(tenant_id)
        yield session

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("MCP_AGENT_ENABLED", "true")
    monkeypatch.setattr(mcp_agent, "connect_to_mcp", fake_connect_to_mcp)
    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)
    FakeClient.payloads.clear()

    async def collect():
        return [
            event
            async for event in main_module.stream_gemini_response(
                "What recipes have I saved?", "tenant-private"
            )
        ]

    events = asyncio.run(collect())
    assert connected_tenants == ["tenant-private"]
    assert any("Using recipe tool: list recipes" in event for event in events)
    assert any("Your Pale Ale recipe is ready." in event for event in events)
    assert FakeClient.payloads[0]["tools"][0]["functionDeclarations"][0]["name"] == "list_recipes"
    assert (
        FakeClient.payloads[1]["contents"][-1]["parts"][0]["functionResponse"]["name"]
        == "list_recipes"
    )


def test_recipe_file_upload_and_tenant_scoped_download(monkeypatch, tmp_path):
    owner_headers = register_and_login("file-owner@example.com")
    other_headers = register_and_login("file-other@example.com")
    recipe = client.post(
        "/api/recipes/",
        headers=owner_headers,
        json={"title": "File Ale", "style": "Pale Ale", "abv": 5, "ibu": 30},
    ).json()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)

    uploaded = client.post(
        f"/api/recipes/{recipe['id']}/file",
        headers=owner_headers,
        files={"file": ("recipe.txt", b"private recipe", "text/plain")},
    )
    assert uploaded.status_code == 201
    local_path = tmp_path / uploaded.json()["file_path"]
    assert local_path.read_bytes() == b"private recipe"
    local_download = client.get(
        f"/api/recipes/{recipe['id']}/file",
        headers=owner_headers,
    )
    assert local_download.status_code == 200
    assert local_download.content == b"private recipe"

    denied = client.post(
        f"/api/recipes/{recipe['id']}/file",
        headers=other_headers,
        files={"file": ("other.txt", b"not yours", "text/plain")},
    )
    assert denied.status_code == 404

    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    monkeypatch.setattr(
        main_module,
        "save_recipe_upload",
        lambda file: "s3://test-bucket/recipes/recipe.txt",
    )
    uploaded_to_s3 = client.post(
        f"/api/recipes/{recipe['id']}/file",
        headers=owner_headers,
        files={"file": ("recipe.txt", b"private recipe", "text/plain")},
    )
    assert uploaded_to_s3.status_code == 201
    class FakeS3:
        def generate_presigned_url(self, operation, *, Params, ExpiresIn):
            assert operation == "get_object"
            assert Params == {"Bucket": "test-bucket", "Key": "recipes/recipe.txt"}
            assert ExpiresIn == 300
            return "https://storage.example/temporary-download"

    monkeypatch.setattr(main_module.boto3, "client", lambda *args, **kwargs: FakeS3())
    download = client.get(
        f"/api/recipes/{recipe['id']}/file?redirect=false",
        headers=owner_headers,
    )
    assert download.status_code == 200
    assert download.json()["download_url"] == "https://storage.example/temporary-download"