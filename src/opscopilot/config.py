"""Runtime configuration (env-driven, no secrets in code)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    model: str = os.environ.get("OPSCOPILOT_MODEL", "claude-opus-5-5")
    effort: str = os.environ.get("OPSCOPILOT_EFFORT", "medium")  # low|medium|high|xhigh|max
    max_tokens: int = int(os.environ.get("OPSCOPILOT_MAX_TOKENS", "16000"))
    max_iterations: int = int(os.environ.get("OPSCOPILOT_MAX_ITERATIONS", "8"))
    knowledge_dir: Path = Path(
        os.environ.get("OPSCOPILOT_KNOWLEDGE_DIR", Path(__file__).resolve().parents[2] / "knowledge")
    )
    prometheus_url: str | None = os.environ.get("PROMETHEUS_URL")
    wine_api_url: str | None = os.environ.get("WINE_API_URL")
    github_owner: str = os.environ.get("OPSCOPILOT_GITHUB_OWNER", "santoshmyakala")
    # Server-side refusal fallback (on by default): routes a declined request to a fallback model.
    fallbacks_enabled: bool = os.environ.get("OPSCOPILOT_FALLBACKS", "default") == "default"
    allowed_repos: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            os.environ.get(
                "OPSCOPILOT_REPOS",
                "wine-quality-mlops,devsecops-gitops-pipeline,cloud-solution-architectures,"
                "devsecops-reference-architectures,ai-infrastructure-hpc-gpu,agentic-genai-platform",
            ).split(",")
        )
    )
