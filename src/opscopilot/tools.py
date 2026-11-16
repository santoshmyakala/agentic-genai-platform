"""Tools the agent may call. Each has a strict JSON schema (validated again server-side with Pydantic)
and a side-effect flag: read-only tools run automatically, side-effecting tools need human approval."""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opscopilot.config import Settings
from opscopilot.retrieval import BM25Index

# Strict tool schemas don't accept these keywords; Pydantic still enforces them client-side in execute().
_UNSUPPORTED_STRICT_KEYWORDS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "title",
}


def _strict_schema(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _strict_schema(v) for k, v in node.items() if k not in _UNSUPPORTED_STRICT_KEYWORDS}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strict_schema(v) for v in node]
    return node


class ToolError(Exception):
    """Raised for expected tool failures; returned to the model as is_error tool results."""


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[BaseModel], str]
    side_effect: bool = False

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "strict": True,
            "input_schema": _strict_schema(self.input_model.model_json_schema()),
        }


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchRunbooksInput(_Strict):
    query: str = Field(
        min_length=2, max_length=300, description="Keywords: error codes, metric names, component names."
    )


class GpuHealthInput(_Strict):
    node: str = Field(
        pattern=r"^[a-z0-9][a-z0-9.\-]{0,62}$", description="Kubernetes node or Slurm host name, e.g. gpu01."
    )


class CiStatusInput(_Strict):
    repo: str = Field(
        pattern=r"^[a-z0-9][a-z0-9\-]{1,99}$", description="Repository name (owner is fixed by configuration)."
    )


class WineSample(_Strict):
    fixed_acidity: float = Field(ge=0)
    volatile_acidity: float = Field(ge=0)
    citric_acid: float = Field(ge=0)
    residual_sugar: float = Field(ge=0)
    chlorides: float = Field(ge=0)
    free_sulfur_dioxide: float = Field(ge=0)
    total_sulfur_dioxide: float = Field(ge=0)
    density: float = Field(gt=0)
    pH: float = Field(gt=0, lt=14)
    sulphates: float = Field(ge=0)
    alcohol: float = Field(ge=0, le=100)
    is_red: bool


class PredictWineInput(_Strict):
    samples: list[WineSample] = Field(min_length=1, max_length=20)


class CordonNodeInput(_Strict):
    node: str = Field(pattern=r"^[a-z0-9][a-z0-9.\-]{0,62}$")
    reason: str = Field(min_length=5, max_length=200, description="Why the node should be taken out of scheduling.")


def build_tools(settings: Settings, index: BM25Index, http: httpx.Client | None = None) -> dict[str, Tool]:
    http = http or httpx.Client(timeout=10.0)

    def search_runbooks(args: SearchRunbooksInput) -> str:
        hits = index.search(args.query, top_k=3)
        if not hits:
            return "No runbook section matched. Say so instead of guessing."
        return "\n\n".join(f"[{c.id}] {c.title} — {c.heading}\n{c.text}" for c, _ in hits)

    def get_gpu_health(args: GpuHealthInput) -> str:
        if not settings.prometheus_url:
            raise ToolError("PROMETHEUS_URL is not configured; GPU metrics are unavailable.")
        queries = {
            "xid_errors_10m": f'increase(DCGM_FI_DEV_XID_ERRORS{{Hostname="{args.node}"}}[10m])',
            "temperature_c": f'DCGM_FI_DEV_GPU_TEMP{{Hostname="{args.node}"}}',
            "utilization_pct": f'DCGM_FI_DEV_GPU_UTIL{{Hostname="{args.node}"}}',
            "row_remap_pending": f'DCGM_FI_DEV_ROW_REMAP_PENDING{{Hostname="{args.node}"}}',
        }
        out: dict[str, dict[str, float]] = {}
        for name, q in queries.items():
            r = http.get(f"{settings.prometheus_url}/api/v1/query", params={"query": q})
            r.raise_for_status()
            out[name] = {s["metric"].get("gpu", "?"): float(s["value"][1]) for s in r.json()["data"]["result"]}
        if not any(out.values()):
            raise ToolError(f"No DCGM metrics found for node '{args.node}'.")
        return json.dumps(out, sort_keys=True)

    def get_ci_status(args: CiStatusInput) -> str:
        if args.repo not in settings.allowed_repos:
            raise ToolError(f"Repository '{args.repo}' is not in the allowlist: {', '.join(settings.allowed_repos)}")
        r = http.get(
            f"https://api.github.com/repos/{settings.github_owner}/{args.repo}/actions/runs",
            params={"branch": "main", "per_page": 5},
            headers={"Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()
        runs = [
            {
                "workflow": run["name"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "commit": run["head_sha"][:7],
                "started": run["run_started_at"],
            }
            for run in r.json().get("workflow_runs", [])
        ]
        return json.dumps(runs)

    def predict_wine_quality(args: PredictWineInput) -> str:
        if not settings.wine_api_url:
            raise ToolError("WINE_API_URL is not configured.")
        alias = {
            "fixed_acidity": "fixed acidity",
            "volatile_acidity": "volatile acidity",
            "citric_acid": "citric acid",
            "residual_sugar": "residual sugar",
            "free_sulfur_dioxide": "free sulfur dioxide",
            "total_sulfur_dioxide": "total sulfur dioxide",
        }
        payload = {"samples": [{alias.get(k, k): v for k, v in s.model_dump().items()} for s in args.samples]}
        r = http.post(f"{settings.wine_api_url}/predict", json=payload)
        r.raise_for_status()
        return r.text

    def cordon_gpu_node(args: CordonNodeInput) -> str:
        # Only reached after explicit human approval (see agent.py). Emits the exact change for the operator.
        cmd = (
            f"kubectl cordon {shlex.quote(args.node)} && kubectl annotate node {shlex.quote(args.node)} "
            f"ops-copilot/reason={shlex.quote(args.reason)} --overwrite"
        )
        return json.dumps(
            {
                "approved_change": cmd,
                "executed": False,
                "note": "Change approved; apply with the platform's change pipeline.",
            }
        )

    tools = [
        Tool(
            "search_runbooks",
            "Search the platform's operational runbooks. Returns sections with citation ids "
            "like [file#section]. Use before answering any operational question.",
            SearchRunbooksInput,
            search_runbooks,
        ),
        Tool(
            "get_gpu_health",
            "Current DCGM health for one GPU node: XID errors (10 min), temperature, utilisation, "
            "pending row remaps, per GPU index.",
            GpuHealthInput,
            get_gpu_health,
        ),
        Tool(
            "get_ci_status",
            "Latest GitHub Actions runs on main for one of the platform's repositories.",
            CiStatusInput,
            get_ci_status,
        ),
        Tool(
            "predict_wine_quality",
            "Score wine samples with the production wine-quality model API.",
            PredictWineInput,
            predict_wine_quality,
        ),
        Tool(
            "cordon_gpu_node",
            "Request to cordon a GPU node (stop new pods scheduling). SIDE EFFECT: requires human "
            "approval; only propose it when a runbook says to.",
            CordonNodeInput,
            cordon_gpu_node,
            side_effect=True,
        ),
    ]
    return {t.name: t for t in tools}


def execute(tool: Tool, raw_input: dict[str, Any]) -> str:
    try:
        args = tool.input_model.model_validate(raw_input)
    except ValidationError as exc:
        raise ToolError(f"Invalid input: {exc.errors(include_url=False)}") from exc
    try:
        return tool.run(args)
    except httpx.HTTPError as exc:
        raise ToolError(f"Upstream call failed: {exc}") from exc
