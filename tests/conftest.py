from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from opscopilot.config import Settings
from opscopilot.retrieval import BM25Index
from opscopilot.tools import build_tools

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def response(blocks, stop="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop,
        model=model,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=80),
    )


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic(): records every request, replays responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        # Snapshot messages: the agent mutates the list after the call.
        self.requests.append({**params, "messages": [dict(m) for m in params["messages"]]})
        return self._responses.pop(0)


def mock_http(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        for (method, prefix), payload in routes.items():
            if request.method == method and str(request.url).startswith(prefix):
                status, body = payload if isinstance(payload, tuple) else (200, payload)
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "no route"})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def settings():
    return Settings(prometheus_url="http://prom.test", wine_api_url="http://wine.test")


@pytest.fixture
def index():
    return BM25Index.from_dir(KNOWLEDGE)


@pytest.fixture
def make_tools(settings, index):
    def _make(routes=None):
        return build_tools(settings, index, http=mock_http(routes or {}))

    return _make


__all__ = ["FakeClient", "json", "mock_http", "response", "text", "tool_use"]
