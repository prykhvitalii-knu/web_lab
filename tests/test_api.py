from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


# --- HEALTHCHECK TEST ---
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



@patch("app.worker.process_recipe_file_task.delay")
@patch("app.worker.send_telegram_notification_task.delay")
def test_create_and_get_recipes(mock_telegram, mock_file_proc):

    client.post("/register", json={"email": "brewer@akatosh.com", "password": "password123"})
    login_res = client.post("/login", data={"username": "brewer@akatosh.com", "password": "password123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a recipe
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

    # Get paginated recipes list
    list_res = client.get("/recipes/?skip=0&limit=5")
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Akatosh Imperial Stout"