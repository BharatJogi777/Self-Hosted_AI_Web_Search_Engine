from __future__ import annotations

import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.schemas import (
    CrawlRequest,
    CrawlResponse,
    DocumentDetail,
    DocumentSummary,
    HealthResponse,
    SearchItem,
    SearchResponse,
)
from app.crawler.fetcher import FetchError, SafeHTTPFetcher
from app.crawler.url_policy import URLPolicy, URLRejected
from app.database.models import Page
from app.database.repository import PageRepository
from app.search.postgres_search import PostgresSearchRepository
from app.services.ingestion import IngestionService, RobotsDeniedError


def configured_domains() -> frozenset[str]:
    values = os.getenv("ALLOWED_DOMAINS", "")
    return frozenset(value.strip() for value in values.split(",") if value.strip())


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://search:search@localhost:5432/search_engine",
        )
        engine = create_async_engine(database_url, pool_pre_ping=True)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        domains = configured_domains()
        policy = URLPolicy(allowed_domains=domains) if domains else None
        fetcher = SafeHTTPFetcher(policy) if policy else None

        app.state.engine = engine
        app.state.sessions = sessions
        app.state.page_repository = PageRepository(sessions)
        app.state.search_repository = PostgresSearchRepository(sessions)
        app.state.ingestion_service = (
            IngestionService(policy, fetcher, app.state.page_repository)
            if policy and fetcher else None
        )
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="Self-Hosted AI Web Search Engine",
        version="0.1.0",
        description="Scoped crawling and lexical search over permitted websites.",
        lifespan=lifespan,
    )

    @app.get("/health/live", response_model=HealthResponse)
    async def health_live():
        return HealthResponse(status="ok")

    @app.get("/health/ready", response_model=HealthResponse)
    async def health_ready(request: Request):
        sessions = getattr(request.app.state, "sessions", None)
        if sessions is None:
            raise HTTPException(status_code=503, detail="Database is not initialized")
        try:
            from sqlalchemy import text
            async with sessions() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
        return HealthResponse(status="ready")

    @app.post("/crawl", response_model=CrawlResponse)
    async def crawl(request: Request, payload: CrawlRequest):
        service = getattr(request.app.state, "ingestion_service", None)
        if service is None:
            raise HTTPException(
                status_code=503,
                detail="Crawling is disabled; configure ALLOWED_DOMAINS first",
            )
        try:
            saved, final_url = await service.crawl_one(str(payload.url))
        except URLRejected as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RobotsDeniedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return CrawlResponse(
            page_id=saved.page_id,
            version_id=saved.version_id,
            version_number=saved.version_number,
            page_created=saved.page_created,
            content_changed=saved.content_changed,
            final_url=final_url,
        )

    @app.get("/search", response_model=SearchResponse)
    async def search(
        request: Request,
        q: str = Query(min_length=1, max_length=300),
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        domain: str | None = Query(default=None, max_length=255),
    ):
        repository = request.app.state.search_repository
        try:
            results = await repository.search(
                q, limit=limit, offset=offset, domain=domain
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return SearchResponse(
            query=q,
            limit=limit,
            offset=offset,
            results=[SearchItem(**item.__dict__) for item in results],
        )

    @app.get("/documents", response_model=list[DocumentSummary])
    async def list_documents(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        sessions = request.app.state.sessions
        async with sessions() as session:
            rows = await session.scalars(
                select(Page).order_by(Page.last_crawled_at.desc())
                .limit(limit).offset(offset)
            )
            pages = rows.all()
        return [
            DocumentSummary(
                id=page.id,
                url=page.normalized_url,
                title=page.title,
                domain=page.domain,
                current_content_hash=page.current_content_hash,
                last_crawled_at=page.last_crawled_at,
            )
            for page in pages
        ]

    @app.get("/documents/{document_id}", response_model=DocumentDetail)
    async def get_document(request: Request, document_id: str):
        from uuid import UUID
        from uuid import UUID as UUIDType
        try:
            parsed_id = UUID(document_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid document ID") from exc
        sessions = request.app.state.sessions
        async with sessions() as session:
            page = await session.get(Page, parsed_id)
        if page is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentDetail(
            id=page.id,
            url=page.normalized_url,
            title=page.title,
            domain=page.domain,
            current_content_hash=page.current_content_hash,
            last_crawled_at=page.last_crawled_at,
            description=page.description,
            language=page.language,
        )

    return app


app = create_app()
