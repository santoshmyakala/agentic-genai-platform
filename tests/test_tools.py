import json

import pytest

from opscopilot.tools import _UNSUPPORTED_STRICT_KEYWORDS, ToolError, execute


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_specs_are_valid_strict_schemas(make_tools):
    for tool in make_tools().values():
        spec = tool.spec()
        assert spec["strict"] is True
        for node in _walk(spec["input_schema"]):
            assert not (_UNSUPPORTED_STRICT_KEYWORDS & set(node)), f"{tool.name}: unsupported keyword in {node}"
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False


def test_only_cordon_has_side_effects(make_tools):
    assert {n for n, t in make_tools().items() if t.side_effect} == {"cordon_gpu_node"}


def test_client_side_validation_still_enforces_constraints(make_tools):
    tools = make_tools()
    with pytest.raises(ToolError, match="Invalid input"):
        execute(tools["get_gpu_health"], {"node": "gpu01; rm -rf /"})
    with pytest.raises(ToolError, match="Invalid input"):
        execute(tools["search_runbooks"], {"query": "x", "extra": 1})


def test_ci_status_is_allowlisted_and_parsed(make_tools):
    runs = {
        "workflow_runs": [
            {
                "name": "ci",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "abcdef123",
                "run_started_at": "2026-11-16T12:00:00Z",
            }
        ]
    }
    tools = make_tools({("GET", "https://api.github.com/repos/santoshmyakala/wine-quality-mlops"): runs})
    assert json.loads(execute(tools["get_ci_status"], {"repo": "wine-quality-mlops"}))[0]["commit"] == "abcdef1"
    with pytest.raises(ToolError, match="allowlist"):
        execute(tools["get_ci_status"], {"repo": "someone-elses-repo"})


def test_gpu_health_reads_dcgm_from_prometheus(make_tools):
    result = {"status": "success", "data": {"result": [{"metric": {"gpu": "3"}, "value": [0, "2"]}]}}
    tools = make_tools({("GET", "http://prom.test/api/v1/query"): result})
    health = json.loads(execute(tools["get_gpu_health"], {"node": "gpu01"}))
    assert health["xid_errors_10m"] == {"3": 2.0}


def test_wine_prediction_maps_field_names_for_the_api(make_tools):
    tools = make_tools({("POST", "http://wine.test/predict"): {"predictions": [5.025], "model_version": "1.0.0"}})
    sample = {
        "fixed_acidity": 7.4,
        "volatile_acidity": 0.7,
        "citric_acid": 0,
        "residual_sugar": 1.9,
        "chlorides": 0.076,
        "free_sulfur_dioxide": 11,
        "total_sulfur_dioxide": 34,
        "density": 0.9978,
        "pH": 3.51,
        "sulphates": 0.56,
        "alcohol": 9.4,
        "is_red": True,
    }
    assert json.loads(execute(tools["predict_wine_quality"], {"samples": [sample]}))["predictions"] == [5.025]


def test_upstream_failure_becomes_tool_error(make_tools):
    tools = make_tools({("GET", "http://prom.test/api/v1/query"): (503, {"error": "down"})})
    with pytest.raises(ToolError, match="Upstream call failed"):
        execute(tools["get_gpu_health"], {"node": "gpu01"})
