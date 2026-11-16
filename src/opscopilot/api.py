"""HTTP service: POST /ask, health probes and Prometheus metrics (tokens, cost drivers, tool usage)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict

import anthropic
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field

from opscopilot import __version__
from opscopilot.agent import OpsCopilot, deny_all
from opscopilot.config import Settings
from opscopilot.guardrails import InputRejected
from opscopilot.retrieval import BM25Index
from opscopilot.tools import build_tools

TOKENS = Counter("opscopilot_tokens_total", "Tokens used", ["kind"])
TOOL_CALLS = Counter("opscopilot_tool_calls_total", "Tool calls", ["tool", "outcome"])
ANSWERS = Counter("opscopilot_answers_total", "Answers by stop reason", ["stop_reason"])
LATENCY = Histogram("opscopilot_answer_seconds", "End-to-end answer latency", buckets=(1, 2, 5, 10, 20, 40, 80))


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "agent"):  # tests inject their own agent
        settings = Settings()
        tools = build_tools(settings, BM25Index.from_dir(settings.knowledge_dir))
        # The HTTP API never auto-approves side effects: proposals come back for a human to apply.
        app.state.agent = OpsCopilot(settings, tools, approver=deny_all)
    yield


app = FastAPI(title="Ops Copilot", version=__version__, lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    try:
        answer = app.state.agent.ask(req.question)
    except InputRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(429, "Model rate limit reached; retry later.") from exc
    except anthropic.APIStatusError as exc:
        raise HTTPException(502, f"Model API error ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(503, "Model API unreachable.") from exc
    TOKENS.labels("input").inc(answer.input_tokens)
    TOKENS.labels("output").inc(answer.output_tokens)
    TOKENS.labels("cache_read").inc(answer.cache_read_tokens)
    for call in answer.tool_calls:
        TOOL_CALLS.labels(call.name, "ok" if call.ok else "error").inc()
    ANSWERS.labels(answer.stop_reason).inc()
    LATENCY.observe(answer.latency_s)
    return asdict(answer)
