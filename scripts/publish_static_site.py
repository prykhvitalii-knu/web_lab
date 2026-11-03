import json
import mimetypes
import os
from pathlib import Path

import boto3


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


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
                    "aiAssistantConfigured": bool(os.getenv("GEMINI_API_KEY")),
                }
            )
            + ";"
        ).encode(),
        ContentType="application/javascript",
        CacheControl="no-store",
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{site_url.rstrip('/')}/</loc>"
        "<changefreq>weekly</changefreq><priority>1.0</priority></url>"
        "</urlset>"
    )
    s3.put_object(
        Bucket=bucket,
        Key="sitemap.xml",
        Body=sitemap.encode(),
        ContentType="application/xml",
        CacheControl="public, max-age=300",
    )


if __name__ == "__main__":
    main()
