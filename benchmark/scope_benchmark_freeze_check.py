from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PREREG_PATH = ROOT / "scope_benchmark_preregistration_draft.json"
BINDING_PATH = ROOT / "scope_target_binding_template.json"
AUTH_PATH = ROOT / "scope_scored_authorization_template.json"
PROTOCOL_PATH = ROOT / "SCOPE_BENCHMARK_PROTOCOL_v0.1.md"
ARM_SPEC_PATH = ROOT / "SCOPE_ARM_SPEC_v0.1.md"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_common(prereg: dict[str, Any], binding: dict[str, Any], auth: dict[str, Any]) -> None:
    require(prereg.get("target_selection", {}).get("target_questions_inspected_before_freeze") is False,
            "Leakage gate: target questions must not be inspected before freeze")
    require(prereg.get("experimental_design", {}).get("information_parity_required") is True,
            "Design gate: information parity must remain required")
    require(prereg.get("experimental_design", {}).get("cross_arm_forecast_visibility") is False,
            "Blinding gate: arms may not see each other's forecasts")
    require(prereg.get("eligibility", {}).get("performance_based_exclusion_forbidden") is True,
            "Selection gate: performance-based exclusion must remain forbidden")
    require(prereg.get("failure_gate", {}).get("failed_cases_may_be_silently_dropped") is False,
            "Failure gate: failed cases may not be silently dropped")
    require(prereg.get("development_separation", {}).get("outcome_driven_changes_retroactively_applied") is False,
            "Versioning gate: outcome-driven changes may not be retroactively applied")
    require(binding.get("question_level_content_inspected_before_binding") is False,
            "Binding gate: target question content may not be inspected before binding")
    require(auth.get("authorization_scope") == "ONE_BOUND_FUTUREEVAL_CYCLE_ONLY",
            "Authorization gate must remain scoped to one bound cycle")


def check_draft(prereg: dict[str, Any], binding: dict[str, Any], auth: dict[str, Any]) -> None:
    require(prereg.get("status") == "DESIGN_DRAFT", "Draft check expects DESIGN_DRAFT status")
    require(prereg.get("scored_run_enabled") is False, "Scored run must remain disabled in draft")
    target = prereg.get("target_selection", {})
    require(target.get("target_cycle") is None, "No target cycle may be selected in design draft")
    require(target.get("target_tournament_or_minibench") is None,
            "No target ID may be selected in design draft")
    require(binding.get("status") == "UNBOUND", "Target binding must remain UNBOUND in design draft")
    require(binding.get("selected_target_id") is None, "No target may be bound in design draft")
    require(auth.get("authorized") is False, "Scored authorization must remain false in design draft")
    require(auth.get("status") == "NOT_AUTHORIZED", "Authorization status must remain NOT_AUTHORIZED")


def check_frozen_unbound(prereg: dict[str, Any], binding: dict[str, Any], auth: dict[str, Any]) -> None:
    require(prereg.get("status") == "FROZEN_UNBOUND", "Freeze check expects FROZEN_UNBOUND status")
    require(prereg.get("scored_run_enabled") is False,
            "Frozen preregistration alone must not authorize scored execution")

    target = prereg.get("target_selection", {})
    require(target.get("mode") == "FIRST_ELIGIBLE_FUTURE_MINIBENCH_AFTER_FREEZE",
            "Target selection rule changed")
    require(target.get("minimum_hours_after_freeze") == 24,
            "Minimum post-freeze delay must remain 24 hours")
    require(target.get("target_cycle") is None and target.get("target_tournament_or_minibench") is None,
            "Frozen preregistration must remain target-unbound")

    freeze = prereg.get("freeze_record", {})
    required_nonempty = [
        "frozen_at_utc",
        "protocol_sha256",
        "scope_code_commit_sha",
        "scope_code_sha256",
        "control_code_commit_sha",
        "control_code_sha256",
        "scope_prompt_sha256",
        "control_prompt_sha256",
        "evidence_pipeline_sha256",
        "config_sha256",
        "dependency_lock_sha256",
        "runtime_manifest_sha256",
        "compute_budget_policy",
    ]
    for key in required_nonempty:
        require(freeze.get(key) not in (None, "", "TO_BE_FROZEN"), f"Freeze field missing: {key}")

    require(bool(freeze.get("model_routes")), "At least one exact model route must be frozen")
    require(bool(freeze.get("generation_parameters")), "Generation parameters must be frozen")

    require(prereg.get("primary_metric", {}).get("scoring_implementation_sha256") not in (None, ""),
            "Scoring implementation hash must be frozen")
    require(prereg.get("primary_metric", {}).get("scoring_validation_record_sha256") not in (None, ""),
            "Scoring validation record hash must be frozen")
    require(prereg.get("uncertainty", {}).get("analysis_code_sha256") not in (None, ""),
            "Analysis implementation hash must be frozen")
    require(prereg.get("information_policy", {}).get("evidence_source_policy") not in (None, "", "TO_BE_FROZEN"),
            "Evidence source policy must be frozen")
    require(prereg.get("information_policy", {}).get("information_cutoff_rule") not in (None, "", "TO_BE_FROZEN"),
            "Information cutoff rule must be frozen")

    require(binding.get("status") == "UNBOUND", "Binding must still be UNBOUND at freeze")
    require(auth.get("authorized") is False, "Authorization must remain false at freeze")


def check_bound(prereg: dict[str, Any], binding: dict[str, Any], auth: dict[str, Any]) -> None:
    check_frozen_unbound(prereg, {**binding, "status": "UNBOUND", "selected_target_id": None}, auth)
    require(binding.get("status") == "BOUND", "Bound check expects BOUND status")
    for key in [
        "freeze_commit_sha",
        "freeze_timestamp_utc",
        "selected_target_cycle",
        "selected_target_id",
        "target_open_timestamp_utc",
        "bound_at_utc",
        "binding_record_sha256",
    ]:
        require(binding.get(key) not in (None, ""), f"Binding field missing: {key}")
    require(binding.get("selected_by_predeclared_rule") is True,
            "Target must be selected by the predeclared rule")
    require(auth.get("authorized") is False,
            "Binding alone must not authorize scored execution")


def check_authorized(prereg: dict[str, Any], binding: dict[str, Any], auth: dict[str, Any]) -> None:
    check_bound(prereg, binding, {**auth, "authorized": False})
    require(auth.get("status") == "AUTHORIZED", "Authorization check expects AUTHORIZED status")
    require(auth.get("authorized") is True, "Scored authorization flag must be true")
    for key in [
        "freeze_commit_sha",
        "frozen_preregistration_sha256",
        "target_binding_sha256",
        "authorized_at_utc",
    ]:
        require(auth.get(key) not in (None, ""), f"Authorization field missing: {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["draft", "frozen-unbound", "bound", "authorized"], default="draft")
    args = parser.parse_args()

    prereg = load_json(PREREG_PATH)
    binding = load_json(BINDING_PATH)
    auth = load_json(AUTH_PATH)

    check_common(prereg, binding, auth)

    if args.mode == "draft":
        check_draft(prereg, binding, auth)
    elif args.mode == "frozen-unbound":
        check_frozen_unbound(prereg, binding, auth)
    elif args.mode == "bound":
        check_bound(prereg, binding, auth)
    elif args.mode == "authorized":
        check_authorized(prereg, binding, auth)

    print(f"SCOPE benchmark gate check: PASS ({args.mode})")
    print(f"protocol_sha256={sha256_file(PROTOCOL_PATH)}")
    print(f"arm_spec_sha256={sha256_file(ARM_SPEC_PATH)}")
    print(f"preregistration_sha256={sha256_file(PREREG_PATH)}")
    print(f"target_binding_template_sha256={sha256_file(BINDING_PATH)}")
    print(f"authorization_template_sha256={sha256_file(AUTH_PATH)}")


if __name__ == "__main__":
    main()
