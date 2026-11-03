import json
import mimetypes
import os
from pathlib import Path

import boto3

from app import seo


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def is_ai_assistant_configured(region: str) -> bool:
    secret_arn = os.getenv("APP_SECRETS_ARN")
    if not secret_arn:
        raise RuntimeError("Set APP_SECRETS_ARN to the runtime application secret")
    response = boto3.client("secretsmanager", region_name=region).get_secret_value(
        SecretId=secret_arn
    )
    settings = json.loads(response["SecretString"])
    if not isinstance(settings, dict):
        raise ValueError("The runtime application secret must contain a JSON object")
    api_key = settings.get("GEMINI_API_KEY")
    return isinstance(api_key, str) and bool(api_key.strip())


def main() -> None:
    bucket = os.getenv("STATIC_SITE_BUCKET")
    if not bucket:
        raise RuntimeError("Set AWS_S3_BUCKET to the static website bucket")

    region = os.getenv("AWS_REGION", "us-east-1")
    site_url = os.getenv("PUBLIC_SITE_URL")
    api_base_url = os.getenv("PUBLIC_API_BASE_URL", "").rstrip("/")
    if not api_base_url.startswith("https://"):
        raise RuntimeError("Set PUBLIC_API_BASE_URL to the HTTPS API URL")
    if not site_url or not site_url.startswith("https://"):
        raise RuntimeError("Set PUBLIC_SITE_URL to the HTTPS website URL")

    ai_assistant_configured = is_ai_assistant_configured(region)
    s3 = boto3.client("s3", region_name=region)
    for path in FRONTEND_DIR.rglob("*"):
        if not path.is_file():
            continue
        key = path.relative_to(FRONTEND_DIR).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        extra_args = {
            "ContentType": content_type,
            "CacheControl": "public, max-age=300",
        }
        if key == "index.html":
            extra_args["CacheControl"] = "public, max-age=60"
            body = seo.rewrite_index_canonical_url(
                path.read_text(encoding="utf-8"), site_url
            ).encode()
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                **extra_args,
            )
            continue
        if key == "robots.txt":
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=seo.build_robots_txt(site_url).encode(),
                **extra_args,
            )
            continue
        if key == "sitemap.xml":
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=seo.build_sitemap_xml(site_url).encode(),
                **extra_args,
            )
            continue
        s3.upload_file(str(path), bucket, key, ExtraArgs=extra_args)

    s3.put_object(
        Bucket=bucket,
        Key="config.js",
        Body=(
            "window.APP_CONFIG = "
            + json.dumps(
                {
                    "apiBaseUrl": api_base_url,
                    "googleAnalyticsId": os.getenv("GOOGLE_ANALYTICS_ID", ""),
                    "aiAssistantConfigured": ai_assistant_configured,
                }
            )
            + ";"
        ).encode(),
        ContentType="application/javascript",
        CacheControl="no-store",
    )


if __name__ == "__main__":
    main()
