from html import escape
from xml.sax.saxutils import escape as escape_xml


def build_robots_txt(site_url: str) -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {site_url.rstrip('/')}/sitemap.xml\n"
    )


def build_sitemap_xml(site_url: str) -> str:
    canonical_url = escape_xml(f"{site_url.rstrip('/')}/")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{canonical_url}</loc>"
        "<changefreq>weekly</changefreq><priority>1.0</priority></url>"
        "</urlset>"
    )


def rewrite_index_canonical_url(index_html: str, site_url: str) -> str:
    canonical_url = escape(f"{site_url.rstrip('/')}/", quote=True)
    return (
        index_html.replace(
            '<link rel="canonical" href="/">',
            f'<link rel="canonical" href="{canonical_url}">',
        )
        .replace(
            '<meta property="og:url" content="/">',
            f'<meta property="og:url" content="{canonical_url}">',
        )
    )
