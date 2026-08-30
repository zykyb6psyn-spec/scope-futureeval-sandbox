from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path

from scope_gate_hashes import binding_sha256
from scope_scored_cycle_runner import (
    AUTH_PATH,
    BINDING_PATH,
    PREREG_PATH,
    ScoredGateClosed,
    execute_scored_cycle,
    load_json,
    validate_scored_gate,
)


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "scored_gate_validation_output"
OUT.mkdir(exist_ok=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_closed(fn, contains: str) -> None:
    try:
        fn()
    except ScoredGateClosed as exc:
        require(contains in str(exc), f"expected gate message containing {contains!r}, got {exc!r}")
    else:
        raise AssertionError(f"expected ScoredGateClosed containing {contains!r}")


def synthetic_authorized_records() -> tuple[dict, dict, dict, str]:
    prereg = load_json(PREREG_PATH)
    prereg = copy.deepcopy(prereg)
    prereg["status"] = "FROZEN_UNBOUND"
    prereg["scored_run_enabled"] = False

    freeze = prereg["freeze_record"]
    freeze.update(
        {
            "frozen_at_utc": "2026-09-01T00:00:00+00:00",
            "protocol_sha256": "p" * 64,
            "scope_code_commit_sha": "a" * 40,
            "scope_code_sha256": "s" * 64,
            "control_code_commit_sha": "a" * 40,
            "control_code_sha256": "c" * 64,
            "scope_prompt_sha256": "q" * 64,
            "control_prompt_sha256": "r" * 64,
            "evidence_pipeline_sha256": "e" * 64,
            "config_sha256": "f" * 64,
            "dependency_lock_sha256": "d" * 64,
            "runtime_manifest_sha256": "m" * 64,
            "model_routes": ["openrouter/openai/gpt-4o", "openrouter/openai/gpt-4o-mini"],
            "generation_parameters": {"temperature": 0.3, "timeout_seconds": 40, "allowed_tries": 2},
            "compute_budget_policy": "ONE_REASONING_GENERATION_PER_ARM_PER_QUESTION",
        }
    )
    prereg["primary_metric"]["scoring_implementation_sha256"] = "1" * 64
    prereg["primary_metric"]["scoring_validation_record_sha256"] = "2" * 64
    prereg["primary_metric"]["resolution_adapter_sha256"] = "3" * 64
    prereg["uncertainty"]["analysis_code_sha256"] = "4" * 64

    prereg_file_hash = "9" * 64

    binding = load_json(BINDING_PATH)
    binding = copy.deepcopy(binding)
    binding.update(
        {
            "status": "BOUND",
            "freeze_commit_sha": "a" * 40,
            "freeze_timestamp_utc": "2026-09-01T00:00:00+00:00",
            "selected_target_cycle": "synthetic-future-minibench",
            "selected_target_id": "synthetic-target-id",
            "target_open_timestamp_utc": "2026-09-02T01:00:00+00:00",
            "selected_by_predeclared_rule": True,
            "question_level_content_inspected_before_binding": False,
            "bound_at_utc": "2026-09-02T01:00:01+00:00",
            "binding_record_sha256": None,
        }
    )
    binding["binding_record_sha256"] = binding_sha256(binding)

    auth = load_json(AUTH_PATH)
    auth = copy.deepcopy(auth)
    auth.update(
        {
            "status": "AUTHORIZED",
            "authorized": True,
            "freeze_commit_sha": "a" * 40,
            "frozen_preregistration_sha256": prereg_file_hash,
            "target_binding_sha256": binding_sha256(binding),
            "authorized_at_utc": "2026-09-02T01:00:02+00:00",
        }
    )
    return prereg, binding, auth, prereg_file_hash


async def verify_current_files_fail_before_fetch() -> None:
    fetch_called = False

    def sentinel_fetch(_target: str):
        nonlocal fetch_called
        fetch_called = True
        raise AssertionError("question fetch must never occur while scored gate is closed")

    try:
        await execute_scored_cycle(question_fetcher=sentinel_fetch)
    except ScoredGateClosed as exc:
        require("Gate 1 closed" in str(exc), f"unexpected current gate failure: {exc!r}")
    else:
        raise AssertionError("current DESIGN_DRAFT files unexpectedly opened the scored executor")

    require(fetch_called is False, "network/question fetch was reached before scored authorization")


def main() -> None:
    tests: list[str] = []

    current_prereg = load_json(PREREG_PATH)
    current_binding = load_json(BINDING_PATH)
    current_auth = load_json(AUTH_PATH)
    expect_closed(
        lambda: validate_scored_gate(
            current_prereg,
            current_binding,
            current_auth,
            prereg_file_sha256=sha256_file(PREREG_PATH),
        ),
        "Gate 1 closed",
    )
    tests.append("current design draft cannot pass Gate 1")

    asyncio.run(verify_current_files_fail_before_fetch())
    tests.append("current closed gate stops before target retrieval/network fetch")

    prereg, binding, auth, prereg_hash = synthetic_authorized_records()
    target = validate_scored_gate(prereg, binding, auth, prereg_file_sha256=prereg_hash)
    require(target == "synthetic-target-id", "fully valid synthetic three-gate record did not open target")
    tests.append("synthetic frozen + bound + authorized triple gate opens exactly one target")

    early = copy.deepcopy(binding)
    early["target_open_timestamp_utc"] = "2026-09-01T23:59:59+00:00"
    early["binding_record_sha256"] = None
    early["binding_record_sha256"] = binding_sha256(early)
    early_auth = copy.deepcopy(auth)
    early_auth["target_binding_sha256"] = binding_sha256(early)
    expect_closed(
        lambda: validate_scored_gate(prereg, early, early_auth, prereg_file_sha256=prereg_hash),
        "24-hour",
    )
    tests.append("target opening before 24-hour post-freeze interval is rejected")

    inspected = copy.deepcopy(binding)
    inspected["question_level_content_inspected_before_binding"] = True
    inspected["binding_record_sha256"] = None
    inspected["binding_record_sha256"] = binding_sha256(inspected)
    inspected_auth = copy.deepcopy(auth)
    inspected_auth["target_binding_sha256"] = binding_sha256(inspected)
    expect_closed(
        lambda: validate_scored_gate(prereg, inspected, inspected_auth, prereg_file_sha256=prereg_hash),
        "question content inspected",
    )
    tests.append("pre-binding question inspection is rejected")

    tampered = copy.deepcopy(binding)
    tampered["selected_target_id"] = "tampered-after-hash"
    expect_closed(
        lambda: validate_scored_gate(prereg, tampered, auth, prereg_file_sha256=prereg_hash),
        "self-hash mismatch",
    )
    tests.append("target-binding mutation after self-hash is rejected")

    wrong_prereg_auth = copy.deepcopy(auth)
    wrong_prereg_auth["frozen_preregistration_sha256"] = "0" * 64
    expect_closed(
        lambda: validate_scored_gate(prereg, binding, wrong_prereg_auth, prereg_file_sha256=prereg_hash),
        "preregistration hash mismatch",
    )
    tests.append("authorization for wrong frozen preregistration is rejected")

    wrong_binding_auth = copy.deepcopy(auth)
    wrong_binding_auth["target_binding_sha256"] = "0" * 64
    expect_closed(
        lambda: validate_scored_gate(prereg, binding, wrong_binding_auth, prereg_file_sha256=prereg_hash),
        "target-binding hash mismatch",
    )
    tests.append("authorization for wrong target binding is rejected")

    unauthorized = copy.deepcopy(auth)
    unauthorized["authorized"] = False
    expect_closed(
        lambda: validate_scored_gate(prereg, binding, unauthorized, prereg_file_sha256=prereg_hash),
        "authorized flag is false",
    )
    tests.append("explicit authorization flag is independently required")

    record = {
        "schema_version": "1.0",
        "status": "PASS",
        "test_count": len(tests),
        "tests": tests,
        "implementation_hashes": {
            "scope_gate_hashes.py": sha256_file(ROOT / "scope_gate_hashes.py"),
            "scope_scored_cycle_runner.py": sha256_file(ROOT / "scope_scored_cycle_runner.py"),
            "scope_scored_gate_validation.py": sha256_file(ROOT / "scope_scored_gate_validation.py"),
        },
        "critical_property": (
            "The current DESIGN_DRAFT / UNBOUND / NOT_AUTHORIZED repository state aborts the scored executor "
            "before target retrieval. A scored target becomes reachable only when frozen preregistration, "
            "post-freeze target binding and explicit one-cycle authorization all cryptographically agree."
        ),
    }
    (OUT / "scored_gate_validation_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
