import hashlib
from dataclasses import replace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.repository import PageRepository
from app.extraction.html_extractor import ExtractedDocument


@pytest_asyncio.fixture
async def repository():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield PageRepository(sessions)
    await engine.dispose()


def make_document(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        source_url="https://example.com/article",
        canonical_url="https://example.com/article",
        title="Example article",
        description="A test page",
        language="en",
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        extractor="test",
    )


@pytest.mark.asyncio
async def test_first_save_creates_page_and_version(repository):
    result = await repository.save_extracted_document(make_document("first revision"), "https://example.com/article")
    assert result.page_created is True
    assert result.content_changed is True
    assert result.version_number == 1
    assert result.version_id is not None


@pytest.mark.asyncio
async def test_same_content_does_not_create_duplicate_version(repository):
    url = "https://example.com/article"
    first = await repository.save_extracted_document(make_document("same text"), url)
    second = await repository.save_extracted_document(make_document("same text"), url)
    versions = await repository.list_versions(first.page_id)
    assert first.page_id == second.page_id
    assert second.page_created is False
    assert second.content_changed is False
    assert second.version_id is None
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_changed_content_appends_new_version(repository):
    url = "https://example.com/article"
    first = await repository.save_extracted_document(make_document("revision one"), url)
    second = await repository.save_extracted_document(make_document("revision two"), url)
    versions = await repository.list_versions(first.page_id)
    assert second.page_id == first.page_id
    assert second.content_changed is True
    assert second.version_number == 2
    assert [version.extracted_text for version in versions] == ["revision one", "revision two"]


@pytest.mark.asyncio
async def test_page_metadata_refresh_does_not_create_version(repository):
    url = "https://example.com/article"
    original = make_document("unchanged body")
    await repository.save_extracted_document(original, url)
    await repository.save_extracted_document(replace(original, title="Updated title"), url)
    page = await repository.get_page(url)
    assert page is not None
    assert page.title == "Updated title"
    assert len(await repository.list_versions(page.id)) == 1
