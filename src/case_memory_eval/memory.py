"""Leakage-resistant reviewed-case memory with explainable ranking."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal, Protocol

import duckdb
from pydantic import Field

from case_memory_eval.canonical import canonical_json, content_id
from case_memory_eval.contracts import ClinicalCase, FailureLabel, ScenarioFamily, StrictModel

Split = Literal["train", "validation", "holdout"]
Intervention = Literal["accepted", "edited", "rejected"]


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> tuple[float, ...]: ...


class HashEmbedding:
    """Stable local feature hashing suitable for deterministic tests and demos."""

    name = "sha256-feature-hash-v1"

    def __init__(self, dimension: int = 128) -> None:
        if dimension < 8:
            raise ValueError("embedding dimension must be at least 8")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4]) % self.dimension
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return tuple(value / norm for value in vector) if norm else tuple(vector)


class ScoreComponents(StrictModel):
    vector: float = Field(ge=-1, le=1)
    family: float = Field(ge=0, le=1)
    failure_mode: float = Field(ge=0, le=1)


class RetrievedPrecedent(StrictModel):
    rank: int = Field(ge=1)
    case_id: str
    title: str
    scenario_family: ScenarioFamily
    failure_modes: tuple[FailureLabel, ...]
    intervention: Intervention
    score: float
    components: ScoreComponents
    influence: str
    guidance: str


class RetrievalResult(StrictModel):
    query_case_id: str
    embedding_provider: str
    precedents: tuple[RetrievedPrecedent, ...]


def _case_text(case: ClinicalCase) -> str:
    return f"{case.title}\n{case.transcript}\n{case.generated_note}"


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class ReviewedCaseMemory:
    """Persist reviewed precedents and retrieve only promoted training examples."""

    def __init__(self, path: Path | str, embedder: EmbeddingProvider | None = None) -> None:
        self.path = str(path)
        self.embedder = embedder or HashEmbedding()
        self.connection = duckdb.connect(self.path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewed_cases (
                case_id VARCHAR PRIMARY KEY,
                case_json VARCHAR NOT NULL,
                split VARCHAR NOT NULL,
                intervention VARCHAR NOT NULL,
                promoted BOOLEAN NOT NULL,
                embedding_json VARCHAR NOT NULL,
                embedding_provider VARCHAR NOT NULL
            )
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ReviewedCaseMemory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def add(
        self,
        case: ClinicalCase,
        *,
        split: Split = "train",
        intervention: Intervention = "accepted",
        promoted: bool = True,
    ) -> None:
        embedding = self.embedder.embed(_case_text(case))
        self.connection.execute(
            """
            INSERT INTO reviewed_cases VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (case_id) DO UPDATE SET
                case_json = excluded.case_json,
                split = excluded.split,
                intervention = excluded.intervention,
                promoted = excluded.promoted,
                embedding_json = excluded.embedding_json,
                embedding_provider = excluded.embedding_provider
            """,
            [
                case.case_id,
                canonical_json(case.model_dump(mode="json")),
                split,
                intervention,
                promoted,
                canonical_json(embedding),
                self.embedder.name,
            ],
        )

    def snapshot_id(self) -> str:
        rows = self.connection.execute(
            """
            SELECT case_id, split, intervention, promoted, embedding_provider
            FROM reviewed_cases ORDER BY case_id
            """
        ).fetchall()
        return content_id(
            {
                "embedding_provider": self.embedder.name,
                "records": [list(row) for row in rows],
            }
        )

    def retrieve(
        self,
        query: ClinicalCase,
        *,
        top_k: int = 3,
        query_split: Split = "holdout",
        family: ScenarioFamily | None = None,
        failure_mode: FailureLabel | None = None,
        excluded_case_ids: frozenset[str] = frozenset(),
    ) -> RetrievalResult:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query_vector = self.embedder.embed(_case_text(query))
        rows = self.connection.execute(
            """
            SELECT case_json, intervention, embedding_json
            FROM reviewed_cases
            WHERE promoted = TRUE AND split = 'train' AND embedding_provider = ?
            ORDER BY case_id
            """,
            [self.embedder.name],
        ).fetchall()
        ranked: list[tuple[float, ClinicalCase, Intervention, ScoreComponents]] = []
        query_labels = {item.label for item in query.expected_failures}
        for case_json, intervention, embedding_json in rows:
            candidate = ClinicalCase.model_validate_json(case_json)
            if candidate.case_id == query.case_id or candidate.case_id in excluded_case_ids:
                continue
            candidate_labels = {item.label for item in candidate.expected_failures}
            if family is not None and candidate.scenario_family is not family:
                continue
            if failure_mode is not None and failure_mode not in candidate_labels:
                continue
            vector_score = _cosine(query_vector, tuple(json.loads(embedding_json)))
            family_score = float(candidate.scenario_family is query.scenario_family)
            label_score = float(bool(query_labels & candidate_labels))
            components = ScoreComponents(
                vector=vector_score, family=family_score, failure_mode=label_score
            )
            total = 0.75 * vector_score + 0.15 * family_score + 0.10 * label_score
            ranked.append((total, candidate, intervention, components))
        ranked.sort(key=lambda item: (-item[0], item[1].case_id))
        precedents = tuple(
            self._precedent(rank, *item) for rank, item in enumerate(ranked[:top_k], start=1)
        )
        return RetrievalResult(
            query_case_id=query.case_id,
            embedding_provider=self.embedder.name,
            precedents=precedents,
        )

    @staticmethod
    def _precedent(
        rank: int,
        score: float,
        case: ClinicalCase,
        intervention: Intervention,
        components: ScoreComponents,
    ) -> RetrievedPrecedent:
        labels = tuple(failure.label for failure in case.expected_failures)
        label_text = ", ".join(label.value for label in labels) or "clean"
        influence = (
            f"vector={components.vector:.3f}; family={components.family:.0f}; "
            f"failure_mode={components.failure_mode:.0f}"
        )
        return RetrievedPrecedent(
            rank=rank,
            case_id=case.case_id,
            title=case.title,
            scenario_family=case.scenario_family,
            failure_modes=labels,
            intervention=intervention,
            score=score,
            components=components,
            influence=influence,
            guidance=f"Reviewed as {intervention}; compare against {label_text} evidence.",
        )
