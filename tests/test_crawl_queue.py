from uuid import uuid4

import pytest

from app.database.queue import CrawlJobRepository


@pytest.mark.asyncio
async def test_enqueue_requires_database_session_factory():
    with pytest.raises(TypeError):
        CrawlJobRepository(None)
