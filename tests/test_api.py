from conftest import FakeClient, response, text, tool_use
from fastapi.testclient import TestClient

from opscopilot import api
from opscopilot.agent import OpsCopilot


def test_ask_endpoint_and_metrics(settings, make_tools):
    fake = FakeClient(
        [
            response([tool_use("t1", "search_runbooks", {"query": "dead letter"})], stop="tool_use"),
            response([text("Fix the root cause before redriving [orders-dead-letter-queue#actions].")]),
        ]
    )
    api.app.state.agent = OpsCopilot(settings, make_tools(), client=fake)
    with TestClient(api.app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        body = client.post("/ask", json={"question": "Orders DLQ alarm fired"}).json()
        assert body["citations"] == ["orders-dead-letter-queue#actions"]
        assert body["tool_calls"][0]["name"] == "search_runbooks"
        metrics = client.get("/metrics/").text
        assert 'opscopilot_tool_calls_total{outcome="ok",tool="search_runbooks"}' in metrics
        assert client.post("/ask", json={"question": ""}).status_code == 422
    del api.app.state.agent
