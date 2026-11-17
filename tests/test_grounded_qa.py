from __future__ import annotations

import pytest

from app.llm.grounded_qa import GroundedQAService


class FakeChatClient:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []

    async def chat(self, messages, tools):
        self.calls.append((messages, tools))
        return self.messages.pop(0)


@pytest.mark.asyncio
async def test_grounded_qa_calls_search_tool_and_returns_sources():
    client = FakeChatClient([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {
                    "name": "search_web",
                    "arguments": {"query": "PostgreSQL indexing", "limit": 3},
                }
            }],
        },
        {
            "role": "assistant",
            "content": "PostgreSQL uses indexes to speed up selected queries [1].",
        },
    ])

    async def search(query, limit):
        assert query == "PostgreSQL indexing"
        assert limit == 3
        return [{
            "page_id": "page-1",
            "url": "https://docs.example.test/indexes",
            "title": "PostgreSQL indexes",
            "snippet": "Indexes can improve lookup performance.",
        }]

    service = GroundedQAService(client, search)
    result = await service.answer("How do PostgreSQL indexes help?")

    assert "[1]" in result["answer"]
    assert result["tool_calls"] == 1
    assert result["sources"] == [{
        "id": "1",
        "url": "https://docs.example.test/indexes",
        "title": "PostgreSQL indexes",
    }]
    assert client.calls[0][1][0]["function"]["name"] == "search_web"


@pytest.mark.asyncio
async def test_grounded_qa_bounds_tool_recursion():
    tool_message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "function": {
                "name": "search_web",
                "arguments": {"query": "more details"},
            }
        }],
    }
    client = FakeChatClient([tool_message, {
        "role": "assistant",
        "content": "Final bounded answer.",
    }])

    async def search(query, limit):
        return []

    service = GroundedQAService(client, search, max_tool_rounds=1)
    result = await service.answer("Explain this")
    assert result["answer"] == "Final bounded answer."
    assert result["tool_calls"] == 1


@pytest.mark.asyncio
async def test_grounded_qa_rejects_empty_question():
    client = FakeChatClient([])

    async def search(query, limit):
        return []

    service = GroundedQAService(client, search)
    with pytest.raises(ValueError):
        await service.answer("   ")
