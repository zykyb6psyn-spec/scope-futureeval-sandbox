from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from scope_scored_cycle_runner import (
    PREREG_PATH,
    ScoredGateClosed,
    compute_runtime_integrity_snapshot,
    load_json,
    validate_frozen_runtime_integrity,
)


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "runtime_integrity_validation_output"
OUT.mkdir(exist_ok=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def frozen_prereg_for_current_runtime() -> dict:
    prereg = copy.deepcopy(load_json(PREREG_PATH))
    prereg["status"] = "FROZEN_UNBOUND"
    snapshot = compute_runtime_integrity_snapshot()

    freeze = prereg["freeze_record"]
    freeze.update(
        {
            "frozen_at_utc": "2026-09-01T00:00:00+00:00",
            "protocol_sha256": snapshot["protocol_sha256"],
            "arm_spec_sha256": snapshot["arm_spec_sha256"],
            "scoring_spec_sha256": snapshot["scoring_spec_sha256"],
            "scope_code_commit_sha": "a" * 40,
            "scope_code_sha256": snapshot["scope_code_sha256"],
            "control_code_commit_sha": "a" * 40,
            "control_code_sha256": snapshot["control_code_sha256"],
            "scope_prompt_sha256": snapshot["scope_prompt_sha256"],
            "control_prompt_sha256": snapshot["control_prompt_sha256"],
            "sanitizer_sha256": snapshot["sanitizer_sha256"],
            "paired_logic_sha256": snapshot["paired_logic_sha256"],
            "scored_executor_sha256": snapshot["scored_executor_sha256"],
            "freeze_gate_sha256": snapshot["freeze_gate_sha256"],
            "gate_hashes_sha256": snapshot["gate_hashes_sha256"],
            "evidence_pipeline_sha256": snapshot["evidence_pipeline_sha256"],
            "config_sha256": snapshot["config_sha256"],
            "dependency_lock_sha256": snapshot["dependency_lock_sha256"],
            "runtime_manifest_sha256": snapshot["runtime_manifest_sha256"],
            "model_routes": snapshot["model_routes"],
            "generation_parameters": snapshot["generation_parameters"],
            "compute_budget_policy": snapshot["compute_budget_policy"],
        }
    )
    prereg["primary_metric"]["scoring_implementation_sha256"] = snapshot["scoring_implementation_sha256"]
    prereg["primary_metric"]["resolution_adapter_sha256"] = snapshot["resolution_adapter_sha256"]
    prereg["primary_metric"]["scoring_validation_record_sha256"] = "b" * 64
    prereg["uncertainty"]["analysis_code_sha256"] = snapshot["analysis_code_sha256"]
    return prereg


def expect_integrity_failure(prereg: dict, overrides: dict[str, Path], contains: str) -> None:
    try:
        validate_frozen_runtime_integrity(prereg, file_overrides=overrides)
    except ScoredGateClosed as exc:
        require(contains in str(exc), f"expected {contains!r}, got {exc!r}")
    else:
        raise AssertionError(f"expected runtime integrity failure containing {contains!r}")


def main() -> None:
    tests: list[str] = []
    prereg = frozen_prereg_for_current_runtime()

    snapshot = validate_frozen_runtime_integrity(prereg)
    require(snapshot["scope_code_sha256"] == prereg["freeze_record"]["scope_code_sha256"], "valid current runtime failed")
    tests.append("current runtime exactly matching frozen hashes passes")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        scope_tamper = tmpdir / "scope_structured_bot.py"
        scope_tamper.write_bytes((ROOT / "scope_structured_bot.py").read_bytes() + b"\n# tamper canary\n")
        expect_integrity_failure(prereg, {"scope_code": scope_tamper}, "scope_code_sha256 mismatch")
        tests.append("treatment source mutation is rejected")

        config = json.loads((ROOT / "scope_cycle1_config_draft.json").read_text(encoding="utf-8"))
        config["model"]["temperature"] = 0.31
        config_tamper = tmpdir / "scope_cycle1_config_draft.json"
        config_tamper.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        expect_integrity_failure(prereg, {"config": config_tamper}, "config_sha256 mismatch")
        tests.append("cycle-config mutation is rejected")

        runtime = json.loads((ROOT / "SCOPE_FREEZE_RUNTIME_MANIFEST_v0.1.json").read_text(encoding="utf-8"))
        runtime["compute_budget_policy"] = "TAMPERED"
        runtime_tamper = tmpdir / "SCOPE_FREEZE_RUNTIME_MANIFEST_v0.1.json"
        runtime_tamper.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
        expect_integrity_failure(prereg, {"runtime_manifest": runtime_tamper}, "runtime_manifest_sha256 mismatch")
        tests.append("runtime-manifest mutation is rejected")

    record = {
        "schema_version": "1.0",
        "status": "PASS",
        "test_count": len(tests),
        "tests": tests,
        "critical_property": (
            "After formal freeze, the scored executor recomputes the local executable, prompt, sanitizer, "
            "scoring, statistics, configuration, dependency-lock and runtime-manifest hashes before any target "
            "client construction or question retrieval. Any mismatch fails closed."
        ),
    }
    (OUT / "runtime_integrity_validation_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
