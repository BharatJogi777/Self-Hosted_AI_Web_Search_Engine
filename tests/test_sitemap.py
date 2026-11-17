import pytest

from app.crawler.sitemap import parse_sitemap


def test_parse_urlset_with_namespace():
    xml = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc><lastmod>2026-01-01</lastmod></url>
    </urlset>"""
    result = parse_sitemap(xml)
    assert len(result) == 1
    assert result[0].location == "https://example.com/a"
    assert result[0].last_modified == "2026-01-01"


def test_parse_sitemap_index():
    xml = b"""<sitemapindex><sitemap><loc>https://example.com/child.xml</loc></sitemap></sitemapindex>"""
    assert parse_sitemap(xml)[0].location.endswith("child.xml")


def test_entry_limit():
    xml = b"<urlset><url><loc>https://a.test/1</loc></url><url><loc>https://a.test/2</loc></url></urlset>"
    assert len(parse_sitemap(xml, max_entries=1)) == 1


def test_invalid_xml():
    with pytest.raises(ValueError):
        parse_sitemap(b"<not-closed>")
