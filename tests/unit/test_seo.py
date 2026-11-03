from pathlib import Path
from xml.etree import ElementTree

from app.seo import build_robots_txt, build_sitemap_xml, rewrite_index_canonical_url
from scripts import publish_static_site


def test_sitemap_has_an_absolute_escaped_homepage_url():
    sitemap = build_sitemap_xml("https://example.test/brew&share")
    root = ElementTree.fromstring(sitemap)
    location = root.find(
        "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
        "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
    )
    assert location is not None
    assert location.text == "https://example.test/brew&share/"


def test_robots_points_to_the_public_sitemap():
    assert build_robots_txt("https://example.test/") == (
        "User-agent: *\nAllow: /\nSitemap: https://example.test/sitemap.xml\n"
    )


def test_static_html_uses_the_deployed_canonical_and_social_url():
    html = (
        '<link rel="canonical" href="/">'
        '<meta property="og:url" content="/">'
    )
    result = rewrite_index_canonical_url(html, "https://example.test/")
    assert '<link rel="canonical" href="https://example.test/">' in result
    assert '<meta property="og:url" content="https://example.test/">' in result


def test_static_publisher_writes_absolute_crawl_metadata(tmp_path, monkeypatch):
    class FakeS3:
        objects = {}

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = kwargs

        def upload_file(self, filename, bucket, key, ExtraArgs):
            self.objects[key] = {"Body": Path(filename).read_bytes(), **ExtraArgs}

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        '<link rel="canonical" href="/">'
        '<meta property="og:url" content="/">',
        encoding="utf-8",
    )
    (frontend / "robots.txt").write_text("Sitemap: /sitemap.xml", encoding="utf-8")
    (frontend / "sitemap.xml").write_text("<urlset />", encoding="utf-8")
    s3 = FakeS3()
    monkeypatch.setattr(publish_static_site, "FRONTEND_DIR", frontend)
    monkeypatch.setattr(publish_static_site.boto3, "client", lambda *args, **kwargs: s3)
    monkeypatch.setenv("STATIC_SITE_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://example.test")
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test")

    publish_static_site.main()

    assert b'href="https://example.test/"' in s3.objects["index.html"]["Body"]
    assert b"Sitemap: https://example.test/sitemap.xml" in s3.objects["robots.txt"]["Body"]
    assert (
        b"<loc>https://example.test/</loc>"
        in s3.objects["sitemap.xml"]["Body"]
    )
