from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

EXPECTED_FORECAST_DUE_DATE = "2026-08-30"
EXPECTED_QUESTION_SET_NAME = "2026-08-30-llm.json"
SELECTION_SEED = 640064
MARKET_QUOTA = 100
DATASET_QUOTA = 100

# Frozen from ForecastBench public source metadata at commit
# 0a974b1ef296cfce661300e23f6dc57655eae519.
DATASET_SOURCES = frozenset({"acled", "dbnomics", "fred", "wikipedia", "yfinance"})
MARKET_SOURCES = frozenset({"infer", "kalshi", "manifold", "metaculus", "polymarket"})
ALL_SOURCES = DATASET_SOURCES | MARKET_SOURCES

# Exact columns written by ForecastBench create_question_set/main.py at the
# public source revision used to design this adapter. The adapter fails closed
# if the bound set changes schema unexpectedly.
EXPECTED_QUESTION_FIELDS = frozenset(
    {
        "id",
        "source",
        "question",
        "resolution_criteria",
        "background",
        "market_info_open_datetime",
        "market_info_close_datetime",
        "market_info_resolution_criteria",
        "url",
        "freeze_datetime",
        "freeze_datetime_value",
        "freeze_datetime_value_explanation",
        "source_intro",
        "resolution_dates",
    }
)

TEXT_REQUIRED_FIELDS = (
    "id",
    "source",
    "question",
    "resolution_criteria",
    "background",
)


class ForecastBenchAdapterError(ValueError):
    """Raised when a bound ForecastBench set cannot be used safely."""


@dataclass(frozen=True)
class Candidate:
    key: str
    question_id: str
    source: str
    source_type: str
    resolution_date: str | None
    rank_sha256: str
    raw_index: int


@dataclass(frozen=True)
class PromptPacket:
    key: str
    question_id: str
    source: str
    source_type: str
    resolution_date: str | None
    question_text: str
    background_info: str
    resolution_criteria: str
    fine_print: str
    synthetic_page_url: str
    snapshot_sha256: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    prefix = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(prefix + data).hexdigest()  # noqa: S324 - Git object identity is SHA-1.


def parse_bound_question_set(data: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - explicit fail-closed boundary
        raise ForecastBenchAdapterError("Target is not valid UTF-8 JSON") from exc

    if not isinstance(parsed, dict):
        raise ForecastBenchAdapterError("Top-level target must be a JSON object")

    expected_top = {"forecast_due_date", "question_set", "questions"}
    if set(parsed) != expected_top:
        raise ForecastBenchAdapterError(
            f"Unexpected top-level schema: {sorted(set(parsed) - expected_top)}"
        )
    if parsed["forecast_due_date"] != EXPECTED_FORECAST_DUE_DATE:
        raise ForecastBenchAdapterError("Unexpected forecast_due_date")
    if parsed["question_set"] != EXPECTED_QUESTION_SET_NAME:
        raise ForecastBenchAdapterError("Unexpected question_set identity")
    if not isinstance(parsed["questions"], list) or not parsed["questions"]:
        raise ForecastBenchAdapterError("questions must be a non-empty list")

    seen = set()
    for index, row in enumerate(parsed["questions"]):
        _validate_question_row(row, index)
        identity = (str(row["source"]), str(row["id"]))
        if identity in seen:
            raise ForecastBenchAdapterError(
                f"Duplicate source/id identity at row {index}: {identity}"
            )
        seen.add(identity)
    return parsed


def _validate_question_row(row: Any, index: int) -> None:
    if not isinstance(row, dict):
        raise ForecastBenchAdapterError(f"Question row {index} is not an object")
    fields = set(row)
    if fields != EXPECTED_QUESTION_FIELDS:
        missing = sorted(EXPECTED_QUESTION_FIELDS - fields)
        extra = sorted(fields - EXPECTED_QUESTION_FIELDS)
        raise ForecastBenchAdapterError(
            f"Question row {index} schema mismatch; missing={missing}, extra={extra}"
        )

    for field in TEXT_REQUIRED_FIELDS:
        value = row[field]
        if not isinstance(value, str) or not value.strip():
            raise ForecastBenchAdapterError(
                f"Question row {index} has invalid required field {field}"
            )

    source = row["source"]
    if source not in ALL_SOURCES:
        raise ForecastBenchAdapterError(
            f"Question row {index} uses unknown source {source!r}"
        )

    resolution_dates = row["resolution_dates"]
    if source in DATASET_SOURCES:
        if not isinstance(resolution_dates, list) or not resolution_dates:
            raise ForecastBenchAdapterError(
                f"Dataset question row {index} has no resolution_dates list"
            )
        for value in resolution_dates:
            _parse_iso_date(value, f"row {index} resolution_date")
    else:
        # ForecastBench currently writes N/A for market forecast_horizons.
        # Accept only the two structurally empty forms rather than guessing.
        if resolution_dates not in ("N/A", [], None):
            raise ForecastBenchAdapterError(
                f"Market question row {index} unexpectedly has resolution_dates"
            )
        close = row["market_info_close_datetime"]
        if not isinstance(close, str) or not close.strip() or close == "N/A":
            raise ForecastBenchAdapterError(
                f"Market question row {index} has no close datetime"
            )


def _parse_iso_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ForecastBenchAdapterError(f"{label} is not a string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ForecastBenchAdapterError(f"{label} is not ISO YYYY-MM-DD") from exc


def _rank(source: str, question_id: str, resolution_date: str | None) -> str:
    target = resolution_date if resolution_date is not None else "MARKET"
    value = f"{SELECTION_SEED}|{source}|{question_id}|{target}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def select_candidates(question_set: dict[str, Any]) -> tuple[list[Candidate], dict[str, Any]]:
    due = _parse_iso_date(question_set["forecast_due_date"], "forecast_due_date")
    market: list[Candidate] = []
    dataset: list[Candidate] = []
    exclusions: list[dict[str, Any]] = []

    for index, row in enumerate(question_set["questions"]):
        source = row["source"]
        qid = str(row["id"])
        if source in MARKET_SOURCES:
            key = f"{source}|{qid}|MARKET"
            market.append(
                Candidate(
                    key=key,
                    question_id=qid,
                    source=source,
                    source_type="market",
                    resolution_date=None,
                    rank_sha256=_rank(source, qid, None),
                    raw_index=index,
                )
            )
            continue

        future_dates = sorted(
            value
            for value in row["resolution_dates"]
            if _parse_iso_date(value, f"row {index} resolution_date") > due
        )
        if not future_dates:
            exclusions.append(
                {
                    "source": source,
                    "id": qid,
                    "reason": "NO_RESOLUTION_DATE_AFTER_FORECAST_DUE_DATE",
                }
            )
            continue
        chosen_date = future_dates[0]
        key = f"{source}|{qid}|{chosen_date}"
        dataset.append(
            Candidate(
                key=key,
                question_id=qid,
                source=source,
                source_type="dataset",
                resolution_date=chosen_date,
                rank_sha256=_rank(source, qid, chosen_date),
                raw_index=index,
            )
        )

    market_selected = sorted(market, key=lambda c: c.rank_sha256)[:MARKET_QUOTA]
    dataset_selected = sorted(dataset, key=lambda c: c.rank_sha256)[:DATASET_QUOTA]
    selected = sorted(market_selected + dataset_selected, key=lambda c: c.key)

    audit = {
        "selection_seed": SELECTION_SEED,
        "market_candidates": len(market),
        "dataset_candidates": len(dataset),
        "market_selected": len(market_selected),
        "dataset_selected": len(dataset_selected),
        "total_selected": len(selected),
        "mechanical_exclusions": exclusions,
        "selected_keys_sha256": canonical_sha256([c.key for c in selected]),
    }
    return selected, audit


def build_prompt_packet(row: dict[str, Any], candidate: Candidate, forecast_due_date: str) -> PromptPacket:
    if str(row["id"]) != candidate.question_id or row["source"] != candidate.source:
        raise ForecastBenchAdapterError("Candidate identity does not match question row")

    question_text = row["question"]
    if candidate.source_type == "dataset":
        if candidate.resolution_date is None:
            raise ForecastBenchAdapterError("Dataset candidate lacks resolution_date")
        try:
            question_text = question_text.format(
                forecast_due_date=forecast_due_date,
                resolution_date=candidate.resolution_date,
            )
        except (KeyError, IndexError, ValueError) as exc:
            raise ForecastBenchAdapterError(
                f"Dataset question {candidate.key} could not be formatted safely"
            ) from exc

    background = row["background"].strip()
    market_resolution_criteria = row["market_info_resolution_criteria"]
    if isinstance(market_resolution_criteria, str):
        market_resolution_criteria = market_resolution_criteria.strip()
        if market_resolution_criteria and market_resolution_criteria != "N/A":
            background = f"{background}\n{market_resolution_criteria}"

    if candidate.source_type == "market":
        fine_print = (
            "ForecastBench static target metadata: market close datetime "
            f"{row['market_info_close_datetime']}."
        )
    else:
        fine_print = (
            "ForecastBench static target metadata: resolution date "
            f"{candidate.resolution_date}."
        )

    # Deliberately excluded from the packet: url, source_intro, freeze_datetime,
    # freeze_datetime_value, and freeze_datetime_value_explanation. In this late
    # shadow, especially the freeze value is prohibited by preregistration.
    snapshot = {
        "key": candidate.key,
        "question_text": question_text,
        "background_info": background,
        "resolution_criteria": row["resolution_criteria"].strip(),
        "fine_print": fine_print,
    }
    return PromptPacket(
        key=candidate.key,
        question_id=candidate.question_id,
        source=candidate.source,
        source_type=candidate.source_type,
        resolution_date=candidate.resolution_date,
        question_text=question_text,
        background_info=background,
        resolution_criteria=row["resolution_criteria"].strip(),
        fine_print=fine_print,
        synthetic_page_url=f"forecastbench-shadow://{candidate.key}",
        snapshot_sha256=canonical_sha256(snapshot),
    )


def build_selected_packets(question_set: dict[str, Any]) -> tuple[list[PromptPacket], dict[str, Any]]:
    selected, audit = select_candidates(question_set)
    by_identity = {
        (str(row["source"]), str(row["id"])): row
        for row in question_set["questions"]
    }
    packets = [
        build_prompt_packet(
            by_identity[(candidate.source, candidate.question_id)],
            candidate,
            question_set["forecast_due_date"],
        )
        for candidate in selected
    ]
    if len({packet.key for packet in packets}) != len(packets):
        raise ForecastBenchAdapterError("Selected packet keys are not unique")
    audit = dict(audit)
    audit["packet_snapshots_sha256"] = canonical_sha256(
        [(packet.key, packet.snapshot_sha256) for packet in packets]
    )
    return packets, audit
