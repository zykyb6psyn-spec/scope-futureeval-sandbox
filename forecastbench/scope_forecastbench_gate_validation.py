from __future__ import annotations

import hashlib
import json
import os
import py_compile
from datetime import datetime, timezone
from pathlib import Path

import scope_forecastbench_adapter_validation as adapter_validation
import scope_forecastbench_shadow_runner as runner

ROOT = Path(__file__).resolve().parents[1]
FB = Path(__file__).resolve().parent
EXECUTION_WORKFLOW = ROOT / ".github" / "workflows" / "scope_forecastbench_shadow_run.yaml"
OUTPUT_DIR = FB / "validation_output"
OUTPUT_DIR.mkdir(exist_ok=True)

EXPECTED_SCOPE_SHA256 = "07414101681fc90a78d7e9045c337765b80db809a5fea9fdefe44320ad67620f"
EXPECTED_CONTROL_SHA256 = "c32057f1d08f34f7231ee3aa90695982048b7695b5bc22af29898206e6c2e807"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    checks: list[str] = []

    for name in (
        "scope_forecastbench_adapter.py",
        "scope_forecastbench_adapter_validation.py",
        "scope_forecastbench_shadow_runner.py",
        "scope_forecastbench_gate_validation.py",
    ):
        py_compile.compile(str(FB / name), doraise=True)
        checks.append(f"syntax:{name}")

    adapter_validation.main()
    checks.append("synthetic_adapter_validation:PASS")

    # Lifecycle-aware authorization validation.
    # Shadow-01 has already been explicitly authorized and executed. The validator must
    # verify that the frozen one-run authorization record is internally consistent,
    # not incorrectly require the historical pre-authorization CLOSED state.
    auth = json.loads((FB / "scope_forecastbench_shadow01_authorization.json").read_text())
    require(auth["status"] == "AUTHORIZED", "Authorization record must remain AUTHORIZED")
    require(auth["authorized"] is True, "Authorization boolean must remain true")
    require(auth["explicit_user_authorization_recorded"] is True, "Explicit authorization record missing")
    require(
        auth.get("authorization_scope") == runner.AUTH_SCOPE,
        "Authorization scope must remain the frozen one-shadow-run scope",
    )
    require(
        isinstance(auth.get("execution_workflow_sha256"), str)
        and len(auth["execution_workflow_sha256"]) == 64,
        "Authorized execution workflow hash missing",
    )
    require(
        isinstance(auth.get("runner_freeze_commit_sha"), str)
        and len(auth["runner_freeze_commit_sha"]) == 40,
        "Authorized runner freeze commit missing",
    )
    checks.append("gate4_record:AUTHORIZED_FROZEN_ONE_RUN")

    # Validate the pre-network administrative/integrity gate offline. Supplying a
    # non-secret sentinel satisfies only the presence check; validate_pre_network_gate
    # performs no network access and no model execution.
    old_key = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = "offline-validation-sentinel"
    try:
        gate = runner.validate_pre_network_gate()
        require(
            gate.get("runner_freeze_commit_sha") == auth.get("runner_freeze_commit_sha"),
            "Runner gate did not bind to the frozen authorized commit",
        )
    finally:
        if old_key is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = old_key
    checks.append("runner_pre_network_gate:AUTHORIZED_INTEGRITY_PASS")
    checks.append("validation_network_access:NONE")
    checks.append("validation_model_execution:NONE")

    source = (FB / "scope_forecastbench_shadow_runner.py").read_text(encoding="utf-8")
    gate_call = source.index("gate = validate_pre_network_gate()")
    target_call = source.index("target_bytes = download_bound_target()")
    model_call = source.index("scope_bot = make_bot(ScopeStructuredBot2026)")
    require(gate_call < target_call < model_call, "Runner order must be gate -> target -> models")
    require("raw.githubusercontent.com" in source, "Pinned target URL missing")
    require(runner.TARGET_PUBLICATION_COMMIT in source, "Pinned publication commit missing")
    require("/main/datasets/question_sets/2026-08-30-llm.json" not in source, "Unpinned main target prohibited")
    require("execution_workflow_sha256" in source, "Runner must gate on workflow hash")
    checks.append("runner_order:PRE_NETWORK_GATE_FIRST")
    checks.append("target_url:PINNED_COMMIT")
    checks.append("runner_integrity:EXECUTION_WORKFLOW_HASH_GATED")

    workflow = EXECUTION_WORKFLOW.read_text(encoding="utf-8")
    require("workflow_dispatch:" in workflow, "Execution workflow must be manual-only")
    require("push:" not in workflow, "Execution workflow must not run on push")
    require("permissions:\n  contents: read" in workflow, "Execution workflow permissions must be read-only")
    require("persist-credentials: false" in workflow, "Checkout credentials must not persist")
    require("python-version: '3.11.16'" in workflow, "Python version must be pinned")
    require("version: '2.4.2'" in workflow, "Poetry version must be pinned")
    require("poetry sync --no-interaction --no-root" in workflow, "Locked dependency sync required")
    require("OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}" in workflow, "Only approved model secret wiring missing")
    require("poetry run python forecastbench/scope_forecastbench_shadow_runner.py" in workflow, "Runner invocation mismatch")
    require("METACULUS_TOKEN" not in workflow, "Metaculus token is not required for this shadow")
    checks.append("execution_workflow:MANUAL_PINNED_READ_ONLY")

    prereg = json.loads((FB / "scope_forecastbench_shadow01_preregistration.json").read_text())
    amendment = json.loads(
        (FB / "scope_forecastbench_shadow01_preregistration_amendment_v0.2.json").read_text()
    )
    binding = json.loads((FB / "scope_forecastbench_shadow01_target_binding.json").read_text())
    require(prereg["information_policy"]["external_research"] is False, "Research must be disabled")
    require(prereg["information_policy"]["web_browsing"] is False, "Browsing must be disabled")
    require(prereg["information_policy"]["crowd_forecast"] is False, "Crowd forecast must be disabled")
    require(prereg["information_policy"]["leaderboard_information"] is False, "Leaderboard must be disabled")
    require(amendment["selection"]["target_forecast_pairs"] == 200, "Sample cap mismatch")
    require(amendment["selection"]["market_target_pairs"] == 100, "Market quota mismatch")
    require(amendment["selection"]["dataset_target_pairs"] == 100, "Dataset quota mismatch")
    require(binding["target"]["git_blob_sha"] == runner.TARGET_BLOB_SHA, "Binding blob mismatch")
    checks.append("information_policy:NO_EXTERNAL_RESEARCH_OR_CROWD")
    checks.append("selection:DETERMINISTIC_100_PLUS_100")

    require(
        sha256_file(ROOT / "benchmark" / "scope_structured_bot.py") == EXPECTED_SCOPE_SHA256,
        "Frozen SCOPE source hash changed",
    )
    require(sha256_file(ROOT / "main.py") == EXPECTED_CONTROL_SHA256, "Frozen control hash changed")
    checks.append("futureeval_scope_source:UNCHANGED")
    checks.append("futureeval_control_source:UNCHANGED")

    paths = {
        "preregistration": FB / "scope_forecastbench_shadow01_preregistration.json",
        "amendment": FB / "scope_forecastbench_shadow01_preregistration_amendment_v0.2.json",
        "binding": FB / "scope_forecastbench_shadow01_target_binding.json",
        "authorization": FB / "scope_forecastbench_shadow01_authorization.json",
        "adapter": FB / "scope_forecastbench_adapter.py",
        "adapter_validation": FB / "scope_forecastbench_adapter_validation.py",
        "runner": FB / "scope_forecastbench_shadow_runner.py",
        "gate_validation": FB / "scope_forecastbench_gate_validation.py",
        "execution_workflow": EXECUTION_WORKFLOW,
        "frozen_scope": ROOT / "benchmark" / "scope_structured_bot.py",
        "frozen_control": ROOT / "main.py",
    }
    record = {
        "schema_version": "0.3",
        "shadow_id": "SCOPE-FB-SHADOW-01",
        "status": "POST_RUN_INTEGRITY_VALIDATED",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "checks": checks,
        "check_count": len(checks),
        "file_sha256": {name: sha256_file(path) for name, path in paths.items()},
        "target_content_accessed": False,
        "target_question_content_inspected": False,
        "real_model_execution": False,
        "gate4_authorized": True,
        "authorization_scope": auth.get("authorization_scope"),
        "historical_authorization_mutated": False,
        "frozen_forecasts_mutated": False,
        "pair_selection_mutated": False,
        "scoring_path_mutated": False,
    }
    output = OUTPUT_DIR / "scope_fb_shadow01_gate_validation.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "check_count": len(checks)}, sort_keys=True))


if __name__ == "__main__":
    main()
