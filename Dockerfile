# syntax=docker/dockerfile:1
FROM python:3.15-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.15-slim
LABEL org.opencontainers.image.source="https://github.com/santoshmyakala/agentic-genai-platform" \
      org.opencontainers.image.description="Ops Copilot: retrieval-grounded Claude agent for platform operations" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPSCOPILOT_KNOWLEDGE_DIR=/app/knowledge
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app
COPY --from=build /install /usr/local
WORKDIR /app
COPY --chown=app:app knowledge ./knowledge
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
# Credentials come from the environment at runtime (ANTHROPIC_API_KEY, or workload identity federation).
CMD ["uvicorn", "opscopilot.api:app", "--host", "0.0.0.0", "--port", "8080"]
