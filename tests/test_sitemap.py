import pytest

from app.crawler.sitemap import parse_sitemap, parse_sitemap_document


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



def test_parser_identifies_sitemap_index():
    xml = b"<sitemapindex><sitemap><loc>https://example.com/child.xml</loc></sitemap></sitemapindex>"
    kind, entries = parse_sitemap_document(xml)
    assert kind == "index"
    assert entries[0].location.endswith("child.xml")


def test_parser_identifies_urlset():
    kind, entries = parse_sitemap_document(b"<urlset><url><loc>https://example.com/a</loc></url></urlset>")
    assert kind == "urlset"
    assert entries[0].location.endswith("/a")


def test_rejects_entity_expansion_payload():
    malicious = b'''<!DOCTYPE foo [<!ENTITY x "expanded">]>
    <urlset><url><loc>&x;</loc></url></urlset>'''
    with pytest.raises(ValueError):
        parse_sitemap(malicious)
