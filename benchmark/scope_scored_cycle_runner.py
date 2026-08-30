from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from forecasting_tools import MetaculusClient

from scope_gate_hashes import binding_sha256, sha256_file
from scope_input_sanitization import assert_cycle1_sanitized, sanitize_question_for_cycle1
from scope_paired_dryrun import (
    SUPPORTED_TYPES,
    deterministic_arm_order,
    load_config,
    make_bot,
    question_identity,
    report_record,
    restricted_question_snapshot,
    sha256_data,
)
from scope_structured_bot import ScopeStructuredBot2026
from main import SummerTemplateBot2026


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
PREREG_PATH = ROOT / "scope_benchmark_preregistration_draft.json"
BINDING_PATH = ROOT / "scope_target_binding_template.json"
AUTH_PATH = ROOT / "scope_scored_authorization_template.json"
RUNTIME_MANIFEST_PATH = ROOT / "SCOPE_FREEZE_RUNTIME_MANIFEST_v0.1.json"
OUTPUT_DIR = ROOT / "scored_output"
OUTPUT_DIR.mkdir(exist_ok=True)

RUNTIME_FILES = {
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
    "scoring": ROOT / "scope_scoring.py",
    "statistics": ROOT / "scope_statistics.py",
    "resolution_adapter": ROOT / "scope_resolution_adapter.py",
    "config": ROOT / "scope_cycle1_config_draft.json",
    "dependency_lock": REPO_ROOT / "poetry.lock",
    "runtime_manifest": RUNTIME_MANIFEST_PATH,
}


class ScoredGateClosed(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScoredGateClosed(message)


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _required_frozen_value(mapping: dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    require(value not in (None, "", "TO_BE_FROZEN"), f"Frozen field missing: {key}")
    return value


def _bundle_sha256(paths: list[Path]) -> str:
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


def compute_runtime_integrity_snapshot(
    *,
    file_overrides: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Compute the exact local runtime state that a frozen scored run depends on."""
    files = dict(RUNTIME_FILES)
    if file_overrides:
        unknown = set(file_overrides) - set(files)
        if unknown:
            raise ValueError(f"Unknown runtime file override role(s): {sorted(unknown)}")
        files.update(file_overrides)

    for role, path in files.items():
        if not path.is_file():
            raise ScoredGateClosed(f"Runtime integrity failed: required file missing: {role}")

    config = load_json(files["config"])
    runtime_manifest = load_json(files["runtime_manifest"])
    model = config.get("model", {})
    parity = config.get("parity", {})

    return {
        "protocol_sha256": sha256_file(files["protocol"]),
        "arm_spec_sha256": sha256_file(files["arm_spec"]),
        "scoring_spec_sha256": sha256_file(files["scoring_spec"]),
        "scope_code_sha256": sha256_file(files["scope_code"]),
        "control_code_sha256": sha256_file(files["control_code"]),
        "scope_prompt_sha256": sha256_file(files["scope_code"]),
        "control_prompt_sha256": sha256_file(files["control_code"]),
        "sanitizer_sha256": sha256_file(files["sanitizer"]),
        "paired_logic_sha256": sha256_file(files["paired_logic"]),
        "scored_executor_sha256": sha256_file(files["scored_executor"]),
        "freeze_gate_sha256": sha256_file(files["freeze_gate"]),
        "gate_hashes_sha256": sha256_file(files["gate_hashes"]),
        "evidence_pipeline_sha256": _bundle_sha256([files["sanitizer"], files["paired_logic"]]),
        "config_sha256": sha256_file(files["config"]),
        "dependency_lock_sha256": sha256_file(files["dependency_lock"]),
        "runtime_manifest_sha256": sha256_file(files["runtime_manifest"]),
        "scoring_implementation_sha256": sha256_file(files["scoring"]),
        "analysis_code_sha256": sha256_file(files["statistics"]),
        "resolution_adapter_sha256": sha256_file(files["resolution_adapter"]),
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
        "compute_budget_policy": runtime_manifest.get("compute_budget_policy"),
    }


def validate_frozen_runtime_integrity(
    prereg: dict[str, Any],
    *,
    file_overrides: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Fail closed if local executable state differs from the frozen preregistration.

    This check must run before any target client construction or question retrieval.
    """
    freeze = prereg.get("freeze_record", {})
    primary = prereg.get("primary_metric", {})
    uncertainty = prereg.get("uncertainty", {})
    actual = compute_runtime_integrity_snapshot(file_overrides=file_overrides)

    expected_from_freeze = {
        "protocol_sha256": _required_frozen_value(freeze, "protocol_sha256"),
        "arm_spec_sha256": _required_frozen_value(freeze, "arm_spec_sha256"),
        "scoring_spec_sha256": _required_frozen_value(freeze, "scoring_spec_sha256"),
        "scope_code_sha256": _required_frozen_value(freeze, "scope_code_sha256"),
        "control_code_sha256": _required_frozen_value(freeze, "control_code_sha256"),
        "scope_prompt_sha256": _required_frozen_value(freeze, "scope_prompt_sha256"),
        "control_prompt_sha256": _required_frozen_value(freeze, "control_prompt_sha256"),
        "sanitizer_sha256": _required_frozen_value(freeze, "sanitizer_sha256"),
        "paired_logic_sha256": _required_frozen_value(freeze, "paired_logic_sha256"),
        "scored_executor_sha256": _required_frozen_value(freeze, "scored_executor_sha256"),
        "freeze_gate_sha256": _required_frozen_value(freeze, "freeze_gate_sha256"),
        "gate_hashes_sha256": _required_frozen_value(freeze, "gate_hashes_sha256"),
        "evidence_pipeline_sha256": _required_frozen_value(freeze, "evidence_pipeline_sha256"),
        "config_sha256": _required_frozen_value(freeze, "config_sha256"),
        "dependency_lock_sha256": _required_frozen_value(freeze, "dependency_lock_sha256"),
        "runtime_manifest_sha256": _required_frozen_value(freeze, "runtime_manifest_sha256"),
        "scoring_implementation_sha256": _required_frozen_value(primary, "scoring_implementation_sha256"),
        "analysis_code_sha256": _required_frozen_value(uncertainty, "analysis_code_sha256"),
        "resolution_adapter_sha256": _required_frozen_value(primary, "resolution_adapter_sha256"),
    }

    for key, expected in expected_from_freeze.items():
        require(actual.get(key) == expected, f"Runtime integrity failed: {key} mismatch")

    require(actual["model_routes"] == freeze.get("model_routes"), "Runtime integrity failed: model_routes mismatch")
    require(
        actual["generation_parameters"] == freeze.get("generation_parameters"),
        "Runtime integrity failed: generation_parameters mismatch",
    )
    require(
        actual["compute_budget_policy"] == freeze.get("compute_budget_policy"),
        "Runtime integrity failed: compute_budget_policy mismatch",
    )
    return actual


def validate_scored_gate(
    prereg: dict[str, Any],
    binding: dict[str, Any],
    auth: dict[str, Any],
    *,
    prereg_file_sha256: str,
) -> str:
    """Validate the frozen preregistration, target binding and authorization records."""
    require(prereg.get("status") == "FROZEN_UNBOUND", "Gate 1 closed: preregistration is not FROZEN_UNBOUND")
    require(prereg.get("scored_run_enabled") is False, "Frozen preregistration may not itself enable scored execution")

    target_rule = prereg.get("target_selection", {})
    require(target_rule.get("mode") == "FIRST_ELIGIBLE_FUTURE_MINIBENCH_AFTER_FREEZE", "Frozen target-selection rule changed")
    require(target_rule.get("minimum_hours_after_freeze") == 24, "Frozen post-freeze waiting rule changed")
    require(target_rule.get("target_cycle") is None, "Frozen preregistration must remain target-unbound")
    require(target_rule.get("target_tournament_or_minibench") is None, "Frozen preregistration must not contain target ID")
    require(target_rule.get("target_questions_inspected_before_freeze") is False, "Leakage gate failed: target questions inspected before freeze")

    freeze = prereg.get("freeze_record", {})
    freeze_time = parse_utc(str(_required_frozen_value(freeze, "frozen_at_utc")))
    freeze_commit = str(_required_frozen_value(freeze, "scope_code_commit_sha"))
    require(str(_required_frozen_value(freeze, "control_code_commit_sha")) == freeze_commit, "SCOPE and control must share one frozen evaluation commit")

    for key in (
        "protocol_sha256",
        "arm_spec_sha256",
        "scoring_spec_sha256",
        "scope_code_sha256",
        "control_code_sha256",
        "scope_prompt_sha256",
        "control_prompt_sha256",
        "sanitizer_sha256",
        "paired_logic_sha256",
        "scored_executor_sha256",
        "freeze_gate_sha256",
        "gate_hashes_sha256",
        "evidence_pipeline_sha256",
        "config_sha256",
        "dependency_lock_sha256",
        "runtime_manifest_sha256",
        "compute_budget_policy",
    ):
        _required_frozen_value(freeze, key)
    require(bool(freeze.get("model_routes")), "Frozen model routes missing")
    require(bool(freeze.get("generation_parameters")), "Frozen generation parameters missing")

    primary = prereg.get("primary_metric", {})
    for key in ("scoring_implementation_sha256", "scoring_validation_record_sha256", "resolution_adapter_sha256"):
        _required_frozen_value(primary, key)
    _required_frozen_value(prereg.get("uncertainty", {}), "analysis_code_sha256")

    require(binding.get("status") == "BOUND", "Gate 2 closed: target binding is not BOUND")
    require(binding.get("selected_by_predeclared_rule") is True, "Bound target was not selected by the predeclared rule")
    require(binding.get("question_level_content_inspected_before_binding") is False, "Leakage gate failed: question content inspected before binding")
    require(str(binding.get("freeze_commit_sha")) == freeze_commit, "Binding freeze commit does not match frozen evaluation commit")

    binding_freeze_time = parse_utc(str(binding.get("freeze_timestamp_utc")))
    require(binding_freeze_time == freeze_time, "Binding freeze timestamp does not match preregistration")
    target_open = parse_utc(str(binding.get("target_open_timestamp_utc")))
    require(target_open >= freeze_time + timedelta(hours=24), "Bound target opened before the mandatory 24-hour post-freeze interval")

    target_id = binding.get("selected_target_id")
    require(target_id not in (None, ""), "Bound target ID missing")
    require(binding.get("selected_target_cycle") not in (None, ""), "Bound target cycle missing")
    require(binding.get("bound_at_utc") not in (None, ""), "Binding timestamp missing")

    computed_binding_hash = binding_sha256(binding)
    require(binding.get("binding_record_sha256") == computed_binding_hash, "Target-binding self-hash mismatch")

    require(auth.get("status") == "AUTHORIZED", "Gate 3 closed: scored authorization status is not AUTHORIZED")
    require(auth.get("authorized") is True, "Gate 3 closed: authorized flag is false")
    require(auth.get("authorization_scope") == "ONE_BOUND_FUTUREEVAL_CYCLE_ONLY", "Authorization scope changed")
    require(str(auth.get("freeze_commit_sha")) == freeze_commit, "Authorization freeze commit mismatch")
    require(auth.get("frozen_preregistration_sha256") == prereg_file_sha256, "Authorization preregistration hash mismatch")
    require(auth.get("target_binding_sha256") == computed_binding_hash, "Authorization target-binding hash mismatch")
    require(auth.get("authorized_at_utc") not in (None, ""), "Authorization timestamp missing")

    return str(target_id)


def validate_secrets_after_gate() -> None:
    missing = [name for name in ("METACULUS_TOKEN", "OPENROUTER_API_KEY") if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required secret(s) after scored gate opened: {', '.join(missing)}")


def append_fsync(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


async def execute_scored_cycle(
    *,
    question_fetcher: Callable[[str], list[Any]] | None = None,
) -> dict[str, Any]:
    prereg = load_json(PREREG_PATH)
    binding = load_json(BINDING_PATH)
    auth = load_json(AUTH_PATH)

    # CRITICAL ORDERING: formal records AND executable runtime integrity are
    # checked before secrets, client construction or target retrieval.
    target_id = validate_scored_gate(
        prereg,
        binding,
        auth,
        prereg_file_sha256=sha256_file(PREREG_PATH),
    )
    runtime_integrity = validate_frozen_runtime_integrity(prereg)
    validate_secrets_after_gate()

    config = load_config()
    if config.get("scored_run_enabled") is not False:
        raise RuntimeError("Cycle config must remain false; authorization is controlled only by the separate gate record")

    client = MetaculusClient()
    fetcher = question_fetcher or client.get_all_open_questions_from_tournament
    questions = fetcher(target_id)

    scope_bot = make_bot(ScopeStructuredBot2026, config)
    control_bot = make_bot(SummerTemplateBot2026, config)
    scope_bot.publish_reports_to_metaculus = False
    control_bot.publish_reports_to_metaculus = False
    bots = {"scope": scope_bot, "control": control_bot}

    run_manifest: dict[str, Any] = {
        "schema_version": "1.1",
        "run_kind": "AUTHORIZED_SCORED_CYCLE",
        "started_at_utc": utc_now(),
        "target_id": target_id,
        "freeze_commit_sha": binding["freeze_commit_sha"],
        "preregistration_sha256": sha256_file(PREREG_PATH),
        "target_binding_sha256": binding_sha256(binding),
        "runtime_integrity_snapshot": runtime_integrity,
        "question_count_retrieved": len(questions),
        "published_scope_reports": 0,
        "paired_records": 0,
        "excluded_records": 0,
    }

    prepublish_path = OUTPUT_DIR / "paired_prepublish_ledger.jsonl"
    publication_path = OUTPUT_DIR / "publication_ledger.jsonl"
    previous_hash = "GENESIS"
    seed = config["randomization"]["arm_execution_order_seed"]

    for raw_question in questions:
        question = sanitize_question_for_cycle1(raw_question)
        assert_cycle1_sanitized(question)
        snapshot = restricted_question_snapshot(question)
        snapshot_sha = sha256_data(snapshot)
        identity = question_identity(question)

        if not isinstance(question, SUPPORTED_TYPES):
            append_fsync(
                prepublish_path,
                {
                    **identity,
                    "kind": "exclusion",
                    "reason_code": "UNSUPPORTED_FROZEN_FORMAT",
                    "question_snapshot_sha256": snapshot_sha,
                    "recorded_at_utc": utc_now(),
                },
            )
            run_manifest["excluded_records"] += 1
            continue

        order = deterministic_arm_order(snapshot_sha, seed)
        arm_results: dict[str, Any] = {}
        raw_reports: dict[str, Any] = {}

        for arm in order:
            report = await bots[arm].forecast_question(copy.deepcopy(question), return_exceptions=True)
            raw_reports[arm] = report
            arm_results[arm] = {
                "input_snapshot_sha256": snapshot_sha,
                "result": report_record(report),
            }

        if any(arm_results[arm]["result"]["kind"] != "forecast_report" for arm in ("scope", "control")):
            failed_record = {
                **identity,
                "kind": "paired_generation_failure",
                "question_snapshot_sha256": snapshot_sha,
                "execution_order": order,
                "scope": arm_results["scope"],
                "control": arm_results["control"],
                "previous_record_sha256": previous_hash,
                "recorded_at_utc": utc_now(),
            }
            failed_hash = sha256_data(failed_record)
            failed_record["record_sha256"] = failed_hash
            append_fsync(prepublish_path, failed_record)
            previous_hash = failed_hash
            continue

        require(
            arm_results["scope"]["input_snapshot_sha256"] == arm_results["control"]["input_snapshot_sha256"],
            "Input parity failed during authorized scored cycle",
        )

        paired_record = {
            **identity,
            "kind": "paired_forecast_prepublish",
            "question_type": snapshot["question_type"],
            "question_snapshot_sha256": snapshot_sha,
            "execution_order": order,
            "scope": arm_results["scope"],
            "control": arm_results["control"],
            "previous_record_sha256": previous_hash,
            "recorded_at_utc": utc_now(),
        }
        record_hash = sha256_data(paired_record)
        paired_record["record_sha256"] = record_hash

        append_fsync(prepublish_path, paired_record)
        previous_hash = record_hash
        run_manifest["paired_records"] += 1

        scope_report = raw_reports["scope"]
        try:
            await scope_report.publish_report_to_metaculus(metaculus_client=scope_bot.metaculus_client)
            publication = {
                "question_id": identity["question_id"],
                "paired_record_sha256": record_hash,
                "status": "PUBLISHED_SCOPE_ONLY",
                "published_at_utc": utc_now(),
            }
            run_manifest["published_scope_reports"] += 1
        except Exception as exc:
            publication = {
                "question_id": identity["question_id"],
                "paired_record_sha256": record_hash,
                "status": "PUBLICATION_FAILED",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "recorded_at_utc": utc_now(),
            }
            append_fsync(publication_path, publication)
            raise

        append_fsync(publication_path, publication)

    run_manifest["completed_at_utc"] = utc_now()
    run_manifest["ledger_tip_sha256"] = previous_hash
    (OUTPUT_DIR / "scored_run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_manifest


if __name__ == "__main__":
    asyncio.run(execute_scored_cycle())
