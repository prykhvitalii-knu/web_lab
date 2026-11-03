import json

import pytest
from botocore.exceptions import ClientError

from scripts import set_cloud_secrets


class FakeSecretsManager:
    def __init__(self, app_secret=None):
        self.app_secret = app_secret
        self.saved_secret = None

    def get_secret_value(self, SecretId):
        if SecretId == "app-config-arn":
            if self.app_secret is None:
                raise ClientError(
                    {"Error": {"Code": "ResourceNotFoundException"}},
                    "GetSecretValue",
                )
            return {"SecretString": json.dumps(self.app_secret)}
        if SecretId == "database-secret-arn":
            return {
                "SecretString": json.dumps(
                    {"username": "beer_user", "password": "beer_password"}
                )
            }
        raise AssertionError("Unexpected secret identifier")

    def put_secret_value(self, SecretId, SecretString):
        assert SecretId == "app-config-arn"
        self.saved_secret = json.loads(SecretString)


def configure_environment(monkeypatch):
    for key, value in {
        "APP_SECRETS_ARN": "app-config-arn",
        "AWS_REGION": "us-east-1",
        "RDS_MASTER_SECRET_ARN": "database-secret-arn",
        "RDS_HOST": "db.example",
        "RDS_PORT": "5432",
        "RDS_DATABASE_NAME": "beer",
    }.items():
        monkeypatch.setenv(key, value)
    for key in set_cloud_secrets.SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_existing_runtime_secrets_are_preserved(monkeypatch):
    configure_environment(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "new-google-client")
    client = FakeSecretsManager(
        {
            "SECRET_KEY": "existing-secret-key",
            "FEATURE_ADMIN_TOKEN": "existing-admin-token",
            "TELEGRAM_BOT_TOKEN": "existing-telegram-token",
            "TELEGRAM_CHAT_ID": "existing-chat-id",
        }
    )
    monkeypatch.setattr(set_cloud_secrets.boto3, "client", lambda *args, **kwargs: client)

    set_cloud_secrets.main()

    assert client.saved_secret["SECRET_KEY"] == "existing-secret-key"
    assert client.saved_secret["FEATURE_ADMIN_TOKEN"] == "existing-admin-token"
    assert client.saved_secret["TELEGRAM_BOT_TOKEN"] == "existing-telegram-token"
    assert client.saved_secret["TELEGRAM_CHAT_ID"] == "existing-chat-id"
    assert client.saved_secret["GOOGLE_CLIENT_ID"] == "new-google-client"
    assert client.saved_secret["GEMINI_MODEL"] == "gemini-3.6-flash"


def test_first_deployment_generates_required_secrets(monkeypatch):
    configure_environment(monkeypatch)
    client = FakeSecretsManager()
    monkeypatch.setattr(set_cloud_secrets.boto3, "client", lambda *args, **kwargs: client)

    set_cloud_secrets.main()

    assert len(client.saved_secret["SECRET_KEY"]) >= 64
    assert len(client.saved_secret["FEATURE_ADMIN_TOKEN"]) >= 40
    assert client.saved_secret["DATABASE_URL"].startswith(
        "postgresql+psycopg2://beer_user:"
    )
