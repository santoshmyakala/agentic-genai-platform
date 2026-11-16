import importlib.util
import pathlib
from types import SimpleNamespace

from opscopilot.agent import Answer, ToolCall

spec = importlib.util.spec_from_file_location("run_evals", pathlib.Path(__file__).parents[1] / "evals/run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)


def test_case_file_is_valid_and_citations_exist(index):
    ids = {c.id for c in index.chunks}
    for case in run_evals.load_cases():
        assert set(case.get("citations_any", [])) <= ids, f"{case['id']} cites a section that does not exist"


def test_grader():
    case = {
        "id": "x",
        "question": "q",
        "tools_required": ["search_runbooks"],
        "citations_any": ["a#b"],
        "must_include": ["cordon"],
        "must_not_include": ["audit"],
        "side_effect": "proposed",
    }
    good = Answer(
        text="Cordon it [a#b]",
        stop_reason="end_turn",
        citations=["a#b"],
        tool_calls=[ToolCall("search_runbooks", {}, True), ToolCall("cordon_gpu_node", {}, False, False)],
    )
    assert all(run_evals.grade(case, good).values())
    bad = SimpleNamespace(**{**good.__dict__, "tool_calls": [], "text": "switch to audit"})
    checks = run_evals.grade(case, bad)
    assert not checks["tools"] and not checks["must_not_include"] and not checks["side_effect"]
