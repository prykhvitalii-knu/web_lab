import json
import os
from urllib.parse import quote

import boto3


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
        "SECRET_KEY",
        "FEATURE_ADMIN_TOKEN",
        "RDS_MASTER_SECRET_ARN",
        "RDS_HOST",
        "RDS_DATABASE_NAME",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Required secret values are missing: {', '.join(missing)}")

    secrets = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
    database_credentials = json.loads(
        secrets.get_secret_value(SecretId=os.environ["RDS_MASTER_SECRET_ARN"])[
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
    values = {key: os.getenv(key, "") for key in SECRET_KEYS}
    values["GEMINI_MODEL"] = values["GEMINI_MODEL"] or "gemini-3.6-flash"
    values["DATABASE_URL"] = database_url

    secrets.put_secret_value(
        SecretId=secret_arn,
        SecretString=json.dumps(values),
    )


if __name__ == "__main__":
    main()
