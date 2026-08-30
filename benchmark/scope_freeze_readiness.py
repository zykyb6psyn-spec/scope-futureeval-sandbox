from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scope_benchmark_freeze_check import check_common, check_draft


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
OUT_DIR = ROOT / "freeze_readiness_output"
OUT_DIR.mkdir(exist_ok=True)

PREREG_PATH = ROOT / "scope_benchmark_preregistration_draft.json"
CONFIG_PATH = ROOT / "scope_cycle1_config_draft.json"
BINDING_PATH = ROOT / "scope_target_binding_template.json"
AUTH_PATH = ROOT / "scope_scored_authorization_template.json"
RUNTIME_MANIFEST_PATH = ROOT / "SCOPE_FREEZE_RUNTIME_MANIFEST_v0.1.json"

FILES = {
    "protocol": ROOT / "SCOPE_BENCHMARK_PROTOCOL_v0.1.md",
    "arm_spec": ROOT / "SCOPE_ARM_SPEC_v0.1.md",
    "scoring_spec": ROOT / "SCOPE_SCORING_SPEC_v0.1.md",
    "scope_code": ROOT / "scope_structured_bot.py",
    "control_code": REPO_ROOT / "main.py",
    "sanitizer": ROOT / "scope_input_sanitization.py",
    "paired_logic": ROOT / "scope_paired_dryrun.py",
    "scored_executor": ROOT / "scope_scored_cycle_runner.py",
    "freeze_gate": ROOT / "scope_benchmark_freeze_check.py",
    "gate_hashes": ROOT / "scope_gate_hashes.py",
    "scored_gate_validation": ROOT / "scope_scored_gate_validation.py",
    "runtime_integrity_validation": ROOT / "scope_runtime_integrity_validation.py",
    "scoring": ROOT / "scope_scoring.py",
    "statistics": ROOT / "scope_statistics.py",
    "resolution_adapter": ROOT / "scope_resolution_adapter.py",
    "config": CONFIG_PATH,
    "dependency_lock": REPO_ROOT / "poetry.lock",
    "runtime_manifest": RUNTIME_MANIFEST_PATH,
    "freeze_readiness_gate": ROOT / "scope_freeze_readiness.py",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle_sha256(paths: list[Path]) -> str:
    payload = []
    for path in sorted(paths, key=lambda p: str(p.relative_to(REPO_ROOT))):
        payload.append(
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(path),
            }
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise RuntimeError(message)
    checks.append(message)


def main() -> None:
    checks: list[str] = []

    prereg = load_json(PREREG_PATH)
    config = load_json(CONFIG_PATH)
    binding = load_json(BINDING_PATH)
    auth = load_json(AUTH_PATH)
    runtime = load_json(RUNTIME_MANIFEST_PATH)

    check_common(prereg, binding, auth)
    check_draft(prereg, binding, auth)
    checks.extend([
        "formal common governance gates pass",
        "formal design-draft gate passes",
    ])

    require(config.get("status") == "DESIGN_DRAFT", "cycle config remains DESIGN_DRAFT", checks)
    require(config.get("scored_target") is None, "cycle config contains no scored target", checks)
    require(config.get("scored_run_enabled") is False, "cycle config scored execution remains disabled", checks)
    require(config.get("publish_during_dryrun") is False, "dry-run publication remains disabled", checks)

    info = config.get("information_policy", {})
    require(info.get("external_research") == "DISABLED_CYCLE1", "external research remains disabled for Cycle 1", checks)
    require(info.get("community_prediction") == "PROHIBITED", "community prediction remains prohibited", checks)
    require(info.get("leaderboard_signal") == "PROHIBITED", "leaderboard signal remains prohibited", checks)
    require(info.get("cross_arm_forecast_visibility") == "PROHIBITED", "cross-arm visibility remains prohibited", checks)

    scoring_parity = prereg.get("scoring_parity", {})
    require(scoring_parity.get("offline_validation_status") == "PASS", "offline scoring parity evidence is PASS", checks)
    require(scoring_parity.get("offline_validation_test_count", 0) >= 19, "offline scoring parity has at least 19 tests", checks)
    require(scoring_parity.get("resolved_record_adapter_validation_complete") is True, "resolution adapter validation is complete", checks)

    input_parity = prereg.get("input_parity_validation", {})
    require(input_parity.get("offline_validation_status") == "PASS", "offline input-parity validation is PASS", checks)
    require(input_parity.get("sanitized_end_to_end_status") == "PASS", "sanitized end-to-end validation is PASS", checks)
    require(input_parity.get("paired_question_count", 0) > 0, "sanitized end-to-end validation contains paired questions", checks)
    require(input_parity.get("scope_failure_count") == 0, "sanitized end-to-end SCOPE failure count is zero", checks)
    require(input_parity.get("control_failure_count") == 0, "sanitized end-to-end control failure count is zero", checks)
    require(input_parity.get("input_parity_failure_count") == 0, "sanitized end-to-end parity failure count is zero", checks)

    for role, path in FILES.items():
        require(path.is_file(), f"required freeze source exists: {role}", checks)

    model = config.get("model", {})
    runtime_routes = runtime.get("model_routes", {})
    require(runtime.get("status") == "FREEZE_CANDIDATE", "runtime manifest is a FREEZE_CANDIDATE", checks)
    require(runtime_routes.get("reasoning") == model.get("reasoning"), "runtime reasoning route matches cycle config", checks)
    require(runtime_routes.get("parser") == model.get("parser"), "runtime parser route matches cycle config", checks)
    require("fails closed" in runtime.get("runtime_integrity_policy", ""), "runtime manifest requires fail-closed integrity verification", checks)

    params = runtime.get("generation_parameters", {})
    parity = config.get("parity", {})
    require(params.get("temperature") == model.get("temperature"), "runtime temperature matches cycle config", checks)
    require(params.get("timeout_seconds") == model.get("timeout_seconds"), "runtime timeout matches cycle config", checks)
    require(params.get("allowed_tries") == model.get("allowed_tries"), "runtime retry budget matches cycle config", checks)
    require(params.get("research_reports_per_question") == parity.get("research_reports_per_question"), "runtime research-report count matches cycle config", checks)
    require(params.get("predictions_per_research_report") == parity.get("predictions_per_research_report"), "runtime prediction count matches cycle config", checks)
    require(params.get("enable_summarize_research") == parity.get("enable_summarize_research"), "runtime summarization setting matches cycle config", checks)
    require(params.get("use_research_summary_to_forecast") == parity.get("use_research_summary_to_forecast"), "runtime research-summary setting matches cycle config", checks)
    require(params.get("arm_execution_order_seed") == config.get("randomization", {}).get("arm_execution_order_seed"), "runtime randomization seed matches cycle config", checks)

    target_policy = runtime.get("target_policy", {})
    target_selection = prereg.get("target_selection", {})
    require(target_policy.get("selection_rule") == target_selection.get("mode"), "runtime target rule matches preregistration", checks)
    require(target_policy.get("minimum_hours_after_freeze") == target_selection.get("minimum_hours_after_freeze"), "runtime post-freeze delay matches preregistration", checks)
    require(target_selection.get("target_questions_inspected_before_freeze") is False, "no target questions were inspected before freeze", checks)
    require(binding.get("status") == "UNBOUND", "target binding remains UNBOUND", checks)
    require(auth.get("status") == "NOT_AUTHORIZED" and auth.get("authorized") is False, "scored authorization remains closed", checks)

    file_hashes = {role: sha256_file(path) for role, path in FILES.items()}
    evidence_pipeline_sha = bundle_sha256([FILES["sanitizer"], FILES["paired_logic"]])

    candidate_commit = os.environ.get("GITHUB_SHA", "").strip()
    require(len(candidate_commit) == 40, "candidate evaluation commit SHA is available", checks)

    freeze_values = {
        "frozen_at_utc": None,
        "protocol_sha256": file_hashes["protocol"],
        "arm_spec_sha256": file_hashes["arm_spec"],
        "scoring_spec_sha256": file_hashes["scoring_spec"],
        "scope_code_commit_sha": candidate_commit,
        "scope_code_sha256": file_hashes["scope_code"],
        "control_code_commit_sha": candidate_commit,
        "control_code_sha256": file_hashes["control_code"],
        "scope_prompt_sha256": file_hashes["scope_code"],
        "control_prompt_sha256": file_hashes["control_code"],
        "sanitizer_sha256": file_hashes["sanitizer"],
        "paired_logic_sha256": file_hashes["paired_logic"],
        "scored_executor_sha256": file_hashes["scored_executor"],
        "freeze_gate_sha256": file_hashes["freeze_gate"],
        "gate_hashes_sha256": file_hashes["gate_hashes"],
        "evidence_pipeline_sha256": evidence_pipeline_sha,
        "config_sha256": file_hashes["config"],
        "dependency_lock_sha256": file_hashes["dependency_lock"],
        "runtime_manifest_sha256": file_hashes["runtime_manifest"],
        "runtime_integrity_validation_sha256": file_hashes["runtime_integrity_validation"],
        "freeze_readiness_gate_sha256": file_hashes["freeze_readiness_gate"],
        "model_routes": [model.get("reasoning"), model.get("parser")],
        "generation_parameters": {
            "temperature": model.get("temperature"),
            "timeout_seconds": model.get("timeout_seconds"),
            "allowed_tries": model.get("allowed_tries"),
            "research_reports_per_question": parity.get("research_reports_per_question"),
            "predictions_per_research_report": parity.get("predictions_per_research_report"),
            "enable_summarize_research": parity.get("enable_summarize_research"),
            "use_research_summary_to_forecast": parity.get("use_research_summary_to_forecast"),
            "arm_execution_order_seed": config.get("randomization", {}).get("arm_execution_order_seed"),
        },
        "compute_budget_policy": runtime.get("compute_budget_policy"),
    }

    record = {
        "schema_version": "1.1",
        "status": "READY_FOR_FORMAL_FREEZE",
        "checked_at_utc": utc_now(),
        "candidate_evaluation_commit_sha": candidate_commit,
        "check_count": len(checks),
        "checks": checks,
        "file_sha256": file_hashes,
        "evidence_pipeline_sha256": evidence_pipeline_sha,
        "freeze_values": freeze_values,
        "primary_metric_freeze_values": {
            "scoring_implementation_sha256": file_hashes["scoring"],
            "scoring_validation_record_sha256": scoring_parity.get("offline_validation_record_sha256"),
            "resolution_adapter_sha256": file_hashes["resolution_adapter"],
        },
        "uncertainty_freeze_values": {
            "analysis_code_sha256": file_hashes["statistics"],
        },
        "validation_sources": {
            "scored_gate_validation_sha256": file_hashes["scored_gate_validation"],
            "runtime_integrity_validation_sha256": file_hashes["runtime_integrity_validation"],
        },
        "pre_target_state": {
            "preregistration_status": prereg.get("status"),
            "target_binding_status": binding.get("status"),
            "authorization_status": auth.get("status"),
            "target_questions_inspected_before_freeze": target_selection.get("target_questions_inspected_before_freeze"),
        },
    }

    out_path = OUT_DIR / "freeze_readiness_record.json"
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SCOPE FREEZE READINESS: READY_FOR_FORMAL_FREEZE")
    print(f"candidate_evaluation_commit_sha={candidate_commit}")
    print(f"check_count={len(checks)}")
    print(f"readiness_record_sha256={sha256_file(out_path)}")


if __name__ == "__main__":
    main()
