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

    # Synthetic-only adapter tests. These do not load the bound target file.
    adapter_validation.main()
    checks.append("synthetic_adapter_validation:PASS")

    auth = json.loads((FB / "scope_forecastbench_shadow01_authorization.json").read_text())
    require(auth["status"] == "NOT_AUTHORIZED", "Authorization gate must remain closed")
    require(auth["authorized"] is False, "Authorization boolean must remain false")
    require(auth["explicit_user_authorization_recorded"] is False, "No authorization may be pre-recorded")
    checks.append("gate4_record:CLOSED")

    # prove fail-closed behavior. This call must stop before OPENROUTER key check,
    # target retrieval, or model construction because Gate 4 is still closed.
    old_key = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        try:
            runner.validate_pre_network_gate()
        except RuntimeError as exc:
            require("Gate 4 is closed" in str(exc), f"Unexpected gate failure: {exc}")
        else:
            raise AssertionError("Runner unexpectedly passed closed Gate 4")
    finally:
        if old_key is not None:
            os.environ["OPENROUTER_API_KEY"] = old_key
    checks.append("runner_fail_closed_before_network:PASS")

    source = (FB / "scope_forecastbench_shadow_runner.py").read_text(encoding="utf-8")
    gate_call = source.index("gate = validate_pre_network_gate()")
    target_call = source.index("target_bytes = download_bound_target()")
    model_call = source.index("scope_bot = make_bot(ScopeStructuredBot2026)")
    require(gate_call < target_call < model_call, "Runner order must be gate -> target -> models")
    require("raw.githubusercontent.com" in source, "Pinned target URL missing")
    require(runner.TARGET_PUBLICATION_COMMIT in source, "Pinned publication commit missing")
    require("/main/datasets/question_sets/2026-08-30-llm.json" not in source, "Unpinned main target prohibited")
    checks.append("runner_order:PRE_NETWORK_GATE_FIRST")
    checks.append("target_url:PINNED_COMMIT")

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
        "authorization_closed": FB / "scope_forecastbench_shadow01_authorization.json",
        "adapter": FB / "scope_forecastbench_adapter.py",
        "adapter_validation": FB / "scope_forecastbench_adapter_validation.py",
        "runner": FB / "scope_forecastbench_shadow_runner.py",
        "gate_validation": FB / "scope_forecastbench_gate_validation.py",
        "frozen_scope": ROOT / "benchmark" / "scope_structured_bot.py",
        "frozen_control": ROOT / "main.py",
    }
    record = {
        "schema_version": "0.1",
        "shadow_id": "SCOPE-FB-SHADOW-01",
        "status": "READY_FOR_RUNNER_FREEZE_GATE4_CLOSED",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "checks": checks,
        "check_count": len(checks),
        "file_sha256": {name: sha256_file(path) for name, path in paths.items()},
        "target_content_accessed": False,
        "target_question_content_inspected": False,
        "real_model_execution": False,
        "gate4_authorized": False,
    }
    output = OUTPUT_DIR / "scope_fb_shadow01_gate_validation.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "check_count": len(checks)}, sort_keys=True))


if __name__ == "__main__":
    main()
