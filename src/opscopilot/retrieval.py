"""Lightweight, dependency-free retrieval over markdown runbooks (BM25 over heading-level chunks).

Keyword retrieval is a deliberate choice for an ops corpus full of exact identifiers
(XID 79, DeadletteredMessages, verify-image-signatures) where lexical match beats fuzzy similarity.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.\-/]*")
_STOP = frozenset(
    "a an and are as at be by for from how i if in into is it of on or so that the then this to was "
    "what when where which why with you your".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass(frozen=True)
class Chunk:
    id: str  # "<file-stem>#<heading-slug>": stable citation key
    title: str
    heading: str
    text: str


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def chunk_markdown(path: Path) -> list[Chunk]:
    title, chunks, heading, buf = path.stem, [], "overview", []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            if "".join(buf).strip():
                chunks.append(Chunk(f"{path.stem}#{_slug(heading)}", title, heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        chunks.append(Chunk(f"{path.stem}#{_slug(heading)}", title, heading, "\n".join(buf).strip()))
    return chunks


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.docs = [tokenize(f"{c.title} {c.heading} {c.heading} {c.text}") for c in chunks]
        self.avgdl = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    @classmethod
    def from_dir(cls, directory: Path) -> BM25Index:
        return cls([c for p in sorted(directory.glob("*.md")) for c in chunk_markdown(p)])

    def search(self, query: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = sum(
                self.idf.get(t, 0.0)
                * tf[t]
                * (self.k1 + 1)
                / (tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
                for t in q
                if t in tf
            )
            if s > 0:
                scores.append((self.chunks[i], s))
        return sorted(scores, key=lambda x: -x[1])[:top_k]
