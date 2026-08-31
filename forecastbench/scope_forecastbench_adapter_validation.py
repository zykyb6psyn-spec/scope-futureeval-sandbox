from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from scope_forecastbench_adapter import (
    DATASET_QUOTA,
    EXPECTED_FORECAST_DUE_DATE,
    EXPECTED_QUESTION_SET_NAME,
    MARKET_QUOTA,
    ForecastBenchAdapterError,
    build_selected_packets,
    canonical_sha256,
    git_blob_sha1,
    parse_bound_question_set,
)

ROOT = Path(__file__).resolve().parents[1]
FORECASTBENCH_DIR = Path(__file__).resolve().parent
EXPECTED_SCOPE_SHA256 = "07414101681fc90a78d7e9045c337765b80db809a5fea9fdefe44320ad67620f"
EXPECTED_CONTROL_SHA256 = "c32057f1d08f34f7231ee3aa90695982048b7695b5bc22af29898206e6c2e807"
EXPECTED_TARGET_BLOB_SHA = "dd1d18715edd28102e04bc0a2ae22462120dbfb4"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(source: str, idx: int, dataset: bool) -> dict:
    if dataset:
        resolution_dates = ["2026-09-06", "2026-09-29", "2026-11-28"]
        question = (
            "As of {forecast_due_date}, will synthetic series "
            f"{idx} be above threshold on {{resolution_date}}?"
        )
        close = "N/A"
    else:
        resolution_dates = "N/A"
        question = f"Will synthetic market event {idx} occur?"
        close = "2026-10-01T00:00:00+00:00"

    return {
        "id": f"q-{source}-{idx:04d}",
        "source": source,
        "question": question,
        "resolution_criteria": "Resolves Yes if the synthetic criterion is met.",
        "background": "Synthetic background only.",
        "market_info_open_datetime": "2026-08-01T00:00:00+00:00",
        "market_info_close_datetime": close,
        "market_info_resolution_criteria": "N/A",
        "url": f"https://example.invalid/{source}/{idx}",
        "freeze_datetime": "2026-08-30T00:00:00+00:00",
        "freeze_datetime_value": "SECRET_LEAK_CANARY",
        "freeze_datetime_value_explanation": "SECRET_EXPLANATION_CANARY",
        "source_intro": "SOURCE_INTRO_CANARY",
        "resolution_dates": resolution_dates,
    }


def _fixture() -> dict:
    questions = []
    for i in range(120):
        questions.append(_row("metaculus", i, dataset=False))
        questions.append(_row("fred", i, dataset=True))
    return {
        "forecast_due_date": EXPECTED_FORECAST_DUE_DATE,
        "question_set": EXPECTED_QUESTION_SET_NAME,
        "questions": questions,
    }


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def test_valid_fixture_and_balanced_deterministic_selection() -> None:
    fixture = _fixture()
    parsed = parse_bound_question_set(_bytes(fixture))
    packets, audit = build_selected_packets(parsed)
    assert audit["market_selected"] == MARKET_QUOTA
    assert audit["dataset_selected"] == DATASET_QUOTA
    assert audit["total_selected"] == MARKET_QUOTA + DATASET_QUOTA
    assert len(packets) == 200
    assert len({packet.question_id for packet in packets}) == 200

    shuffled = _fixture()
    random.Random(12345).shuffle(shuffled["questions"])
    shuffled_parsed = parse_bound_question_set(_bytes(shuffled))
    shuffled_packets, shuffled_audit = build_selected_packets(shuffled_parsed)
    assert [packet.key for packet in packets] == [packet.key for packet in shuffled_packets]
    assert audit["selected_keys_sha256"] == shuffled_audit["selected_keys_sha256"]


def test_dataset_uses_earliest_future_resolution_date() -> None:
    parsed = parse_bound_question_set(_bytes(_fixture()))
    packets, _ = build_selected_packets(parsed)
    dataset_packets = [p for p in packets if p.source_type == "dataset"]
    assert dataset_packets
    assert {p.resolution_date for p in dataset_packets} == {"2026-09-06"}
    assert all("2026-09-06" in p.question_text for p in dataset_packets)


def test_leak_fields_never_enter_prompt_packets() -> None:
    parsed = parse_bound_question_set(_bytes(_fixture()))
    packets, _ = build_selected_packets(parsed)
    serialized = json.dumps([p.__dict__ for p in packets], ensure_ascii=False)
    assert "SECRET_LEAK_CANARY" not in serialized
    assert "SECRET_EXPLANATION_CANARY" not in serialized
    assert "SOURCE_INTRO_CANARY" not in serialized
    assert "example.invalid" not in serialized


def test_schema_drift_fails_closed() -> None:
    fixture = _fixture()
    fixture["questions"][0]["unexpected_future_field"] = "x"
    try:
        parse_bound_question_set(_bytes(fixture))
    except ForecastBenchAdapterError:
        return
    raise AssertionError("Schema drift was not rejected")


def test_wrong_due_date_fails_closed() -> None:
    fixture = _fixture()
    fixture["forecast_due_date"] = "2026-08-31"
    try:
        parse_bound_question_set(_bytes(fixture))
    except ForecastBenchAdapterError:
        return
    raise AssertionError("Wrong due date was not rejected")


def test_unknown_source_fails_closed() -> None:
    fixture = _fixture()
    fixture["questions"][0]["source"] = "unknown-source"
    try:
        parse_bound_question_set(_bytes(fixture))
    except ForecastBenchAdapterError:
        return
    raise AssertionError("Unknown source was not rejected")


def test_duplicate_identity_fails_closed() -> None:
    fixture = _fixture()
    fixture["questions"].append(dict(fixture["questions"][0]))
    try:
        parse_bound_question_set(_bytes(fixture))
    except ForecastBenchAdapterError:
        return
    raise AssertionError("Duplicate identity was not rejected")


def test_git_blob_hash_implementation() -> None:
    # Git's documented empty-blob object id.
    assert git_blob_sha1(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_frozen_futureeval_arm_sources_are_unchanged() -> None:
    assert _sha256_file(ROOT / "benchmark" / "scope_structured_bot.py") == EXPECTED_SCOPE_SHA256
    assert _sha256_file(ROOT / "main.py") == EXPECTED_CONTROL_SHA256


def test_administrative_gates_and_binding_are_closed_correctly() -> None:
    prereg = json.loads(
        (FORECASTBENCH_DIR / "scope_forecastbench_shadow01_preregistration.json").read_text()
    )
    amendment = json.loads(
        (
            FORECASTBENCH_DIR
            / "scope_forecastbench_shadow01_preregistration_amendment_v0.2.json"
        ).read_text()
    )
    binding = json.loads(
        (FORECASTBENCH_DIR / "scope_forecastbench_shadow01_target_binding.json").read_text()
    )
    assert prereg["official_forecastbench_submission"] is False
    assert prereg["information_policy"]["external_research"] is False
    assert prereg["information_policy"]["web_browsing"] is False
    assert prereg["isolation"]["futureeval_cycle1_must_remain_unchanged"] is True
    assert amendment["selection"]["content_based_selection"] is False
    assert amendment["selection"]["question_level_content_inspected_before_this_amendment"] is False
    assert binding["status"] == "BOUND_METADATA_ONLY"
    assert binding["target"]["git_blob_sha"] == EXPECTED_TARGET_BLOB_SHA
    assert binding["selection"]["question_level_content_inspected_before_binding"] is False
    assert binding["gates_after_binding"]["gate_3_runner_integrity_validation"] == "OPEN"
    assert binding["gates_after_binding"]["gate_4_explicit_real_run_authorization"] == "OPEN"
    assert binding["gates_after_binding"]["real_model_execution_allowed"] is False


def test_selection_hash_is_stable() -> None:
    parsed = parse_bound_question_set(_bytes(_fixture()))
    packets, audit = build_selected_packets(parsed)
    assert audit["selected_keys_sha256"] == canonical_sha256([p.key for p in packets])


def main() -> None:
    tests = [
        test_valid_fixture_and_balanced_deterministic_selection,
        test_dataset_uses_earliest_future_resolution_date,
        test_leak_fields_never_enter_prompt_packets,
        test_schema_drift_fails_closed,
        test_wrong_due_date_fails_closed,
        test_unknown_source_fails_closed,
        test_duplicate_identity_fails_closed,
        test_git_blob_hash_implementation,
        test_frozen_futureeval_arm_sources_are_unchanged,
        test_administrative_gates_and_binding_are_closed_correctly,
        test_selection_hash_is_stable,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(json.dumps({"status": "PASS", "tests": len(tests)}, sort_keys=True))


if __name__ == "__main__":
    main()
