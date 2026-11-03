import json
import os
import secrets
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError


SECRET_KEYS = (
    "SECRET_KEY",
    "FEATURE_ADMIN_TOKEN",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PUBLIC_SITE_URL",
    "PUBLIC_API_BASE_URL",
)


def main() -> None:
    secret_arn = os.getenv("APP_SECRETS_ARN")
    if not secret_arn:
        raise RuntimeError("Set APP_SECRETS_ARN to the Terraform Secrets Manager output")

    required = (
        "RDS_MASTER_SECRET_ARN",
        "RDS_HOST",
        "RDS_DATABASE_NAME",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Required secret values are missing: {', '.join(missing)}")

    secrets_client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
    try:
        existing_secret = secrets_client.get_secret_value(SecretId=secret_arn)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        existing_values = {}
    else:
        existing_values = json.loads(existing_secret["SecretString"])
        if not isinstance(existing_values, dict):
            raise ValueError("The existing application secret must contain a JSON object")

    database_credentials = json.loads(
        secrets_client.get_secret_value(SecretId=os.environ["RDS_MASTER_SECRET_ARN"])[
            "SecretString"
        ]
    )
    database_url = (
        "postgresql+psycopg2://"
        f"{quote(database_credentials['username'], safe='')}:"
        f"{quote(database_credentials['password'], safe='')}@"
        f"{os.environ['RDS_HOST']}:{os.getenv('RDS_PORT', '5432')}/"
        f"{quote(os.environ['RDS_DATABASE_NAME'], safe='')}?sslmode=require"
    )
    values = existing_values
    for key in SECRET_KEYS:
        configured_value = os.getenv(key)
        if configured_value:
            values[key] = configured_value
    values["SECRET_KEY"] = values.get("SECRET_KEY") or secrets.token_urlsafe(48)
    values["FEATURE_ADMIN_TOKEN"] = (
        values.get("FEATURE_ADMIN_TOKEN") or secrets.token_urlsafe(32)
    )
    values["GEMINI_MODEL"] = values.get("GEMINI_MODEL") or "gemini-3.6-flash"
    values["DATABASE_URL"] = database_url

    secrets_client.put_secret_value(
        SecretId=secret_arn,
        SecretString=json.dumps(values),
    )


if __name__ == "__main__":
    main()
