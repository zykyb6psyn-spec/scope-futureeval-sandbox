from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import random
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "benchmark"
FORECASTBENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BENCHMARK_DIR))

from forecasting_tools import BinaryQuestion, GeneralLlm  # noqa: E402
from main import SummerTemplateBot2026  # noqa: E402
from scope_structured_bot import ScopeStructuredBot2026  # noqa: E402
from scope_forecastbench_adapter import (  # noqa: E402
    SELECTION_SEED,
    build_selected_packets,
    canonical_sha256,
    git_blob_sha1,
    parse_bound_question_set,
)

SHADOW_ID = "SCOPE-FB-SHADOW-01"
AUTH_SCOPE = "ONE_SHADOW_RUN_BOUND_2026-08-30"
TARGET_REPOSITORY = "forecastingresearch/forecastbench-datasets"
TARGET_PUBLICATION_COMMIT = "eefea7424aafb1329140b8916a8f49b62cc04744"
TARGET_PATH = "datasets/question_sets/2026-08-30-llm.json"
TARGET_BLOB_SHA = "dd1d18715edd28102e04bc0a2ae22462120dbfb4"
TARGET_SIZE_BYTES = 1312712
TARGET_URL = (
    "https://raw.githubusercontent.com/"
    f"{TARGET_REPOSITORY}/{TARGET_PUBLICATION_COMMIT}/{TARGET_PATH}"
)

REASONING_MODEL = "openrouter/openai/gpt-4o"
PARSER_MODEL = "openrouter/openai/gpt-4o-mini"
TEMPERATURE = 0.3
TIMEOUT_SECONDS = 40
ALLOWED_TRIES = 2

PREREG_PATH = FORECASTBENCH_DIR / "scope_forecastbench_shadow01_preregistration.json"
AMENDMENT_PATH = FORECASTBENCH_DIR / "scope_forecastbench_shadow01_preregistration_amendment_v0.2.json"
BINDING_PATH = FORECASTBENCH_DIR / "scope_forecastbench_shadow01_target_binding.json"
AUTH_PATH = FORECASTBENCH_DIR / "scope_forecastbench_shadow01_authorization.json"
ADAPTER_PATH = FORECASTBENCH_DIR / "scope_forecastbench_adapter.py"
RUNNER_PATH = Path(__file__).resolve()
EXECUTION_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "scope_forecastbench_shadow_run.yaml"
OUTPUT_DIR = Path(
    os.environ.get("SCOPE_FB_OUTPUT_DIR", str(FORECASTBENCH_DIR / "run_output"))
)

EXPECTED_SCOPE_SHA256 = "07414101681fc90a78d7e9045c337765b80db809a5fea9fdefe44320ad67620f"
EXPECTED_CONTROL_SHA256 = "c32057f1d08f34f7231ee3aa90695982048b7695b5bc22af29898206e6c2e807"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_pre_network_gate() -> dict[str, Any]:
    """Validate every administrative/runtime gate before any network access."""
    prereg = _load_json(PREREG_PATH)
    amendment = _load_json(AMENDMENT_PATH)
    binding = _load_json(BINDING_PATH)
    auth = _load_json(AUTH_PATH)

    require(prereg.get("shadow_id") == SHADOW_ID, "Wrong preregistration identity")
    require(prereg.get("official_forecastbench_submission") is False, "Shadow cannot be official")
    require(prereg["information_policy"].get("external_research") is False, "External research must be off")
    require(prereg["information_policy"].get("web_browsing") is False, "Web browsing must be off")
    require(prereg["information_policy"].get("crowd_forecast") is False, "Crowd forecast must be off")
    require(prereg["information_policy"].get("leaderboard_information") is False, "Leaderboard must be off")
    require(prereg["isolation"].get("futureeval_cycle1_must_remain_unchanged") is True, "FutureEval isolation missing")

    require(amendment.get("status") == "PREREGISTERED_PRE_RETRIEVAL_AMENDMENT", "Amendment not frozen")
    require(amendment["selection"].get("content_based_selection") is False, "Content selection prohibited")
    require(amendment["selection"].get("target_forecast_pairs") == 200, "Unexpected sample size")

    require(binding.get("status") == "BOUND_METADATA_ONLY", "Target not metadata-bound")
    require(binding["target"].get("publication_commit_sha") == TARGET_PUBLICATION_COMMIT, "Wrong publication commit")
    require(binding["target"].get("git_blob_sha") == TARGET_BLOB_SHA, "Wrong target blob")
    require(binding["target"].get("file_size_bytes") == TARGET_SIZE_BYTES, "Wrong target size")
    require(binding["selection"].get("question_level_content_inspected_before_binding") is False, "Pre-binding inspection flag invalid")

    # Gate 4 is deliberately checked before target retrieval or model construction.
    require(auth.get("shadow_id") == SHADOW_ID, "Wrong authorization identity")
    require(auth.get("status") == "AUTHORIZED", "Gate 4 is closed: status is not AUTHORIZED")
    require(auth.get("authorized") is True, "Gate 4 is closed: authorized is false")
    require(auth.get("explicit_user_authorization_recorded") is True, "No explicit user authorization recorded")
    require(auth.get("authorization_scope") == AUTH_SCOPE, "Authorization scope mismatch")
    freeze_commit = auth.get("runner_freeze_commit_sha")
    require(isinstance(freeze_commit, str) and len(freeze_commit) == 40, "Missing runner freeze commit")

    expected_hashes = {
        PREREG_PATH: auth.get("preregistration_sha256"),
        AMENDMENT_PATH: auth.get("amendment_sha256"),
        BINDING_PATH: auth.get("binding_sha256"),
        ADAPTER_PATH: auth.get("adapter_sha256"),
        RUNNER_PATH: auth.get("runner_sha256"),
        EXECUTION_WORKFLOW_PATH: auth.get("execution_workflow_sha256"),
    }
    for path, expected in expected_hashes.items():
        require(isinstance(expected, str) and len(expected) == 64, f"Missing authorized hash for {path.name}")
        require(sha256_file(path) == expected, f"Runtime integrity mismatch for {path.name}")

    require(
        sha256_file(BENCHMARK_DIR / "scope_structured_bot.py") == EXPECTED_SCOPE_SHA256,
        "Frozen SCOPE treatment source changed",
    )
    require(
        sha256_file(ROOT / "main.py") == EXPECTED_CONTROL_SHA256,
        "Frozen control source changed",
    )
    require(os.environ.get("OPENROUTER_API_KEY"), "OPENROUTER_API_KEY is required")

    return {
        "runner_freeze_commit_sha": freeze_commit,
        "authorized_at_utc": auth.get("authorized_at_utc"),
        "preregistration_sha256": sha256_file(PREREG_PATH),
        "amendment_sha256": sha256_file(AMENDMENT_PATH),
        "binding_sha256": sha256_file(BINDING_PATH),
        "adapter_sha256": sha256_file(ADAPTER_PATH),
        "runner_sha256": sha256_file(RUNNER_PATH),
        "execution_workflow_sha256": sha256_file(EXECUTION_WORKFLOW_PATH),
    }


def download_bound_target() -> bytes:
    request = urllib.request.Request(
        TARGET_URL,
        headers={"User-Agent": "SCOPE-ForecastBench-Shadow-01/0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - pinned HTTPS target
        data = response.read(TARGET_SIZE_BYTES + 1)
    require(len(data) == TARGET_SIZE_BYTES, "Downloaded target size mismatch")
    require(git_blob_sha1(data) == TARGET_BLOB_SHA, "Downloaded target Git blob mismatch")
    return data


def make_llms() -> dict[str, Any]:
    return {
        "default": GeneralLlm(
            model=REASONING_MODEL,
            temperature=TEMPERATURE,
            timeout=TIMEOUT_SECONDS,
            allowed_tries=ALLOWED_TRIES,
        ),
        "summarizer": PARSER_MODEL,
        "researcher": "no_research",
        "parser": PARSER_MODEL,
    }


def make_bot(bot_class: type):
    return bot_class(
        research_reports_per_question=1,
        predictions_per_research_report=1,
        use_research_summary_to_forecast=False,
        enable_summarize_research=False,
        publish_reports_to_metaculus=False,
        folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=False,
        extra_metadata_in_explanation=False,
        llms=make_llms(),
    )


def deterministic_arm_order(snapshot_sha256: str) -> list[str]:
    derived = int(snapshot_sha256[:16], 16) ^ SELECTION_SEED
    rng = random.Random(derived)
    order = ["scope", "control"]
    rng.shuffle(order)
    return order


def _prediction_record(prediction: Any) -> dict[str, Any]:
    value = float(prediction.prediction_value)
    require(0.0 <= value <= 1.0, "Prediction outside [0,1]")
    reasoning = str(prediction.reasoning)
    return {
        "prediction": value,
        "reasoning_sha256": hashlib.sha256(reasoning.encode("utf-8", errors="replace")).hexdigest(),
        "reasoning_length": len(reasoning),
    }


def _append_fsync_jsonl(path: Path, value: dict[str, Any]) -> None:
    line = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


async def run() -> None:
    # Nothing below this point, including target retrieval or model construction,
    # is reached until Gate 4 and file integrity are validated.
    gate = validate_pre_network_gate()

    target_bytes = download_bound_target()
    question_set = parse_bound_question_set(target_bytes)
    packets, selection_audit = build_selected_packets(question_set)
    require(packets, "No selected targets")
    require(len(packets) <= 200, "Selection exceeded preregistered cap")

    scope_bot = make_bot(ScopeStructuredBot2026)
    control_bot = make_bot(SummerTemplateBot2026)
    bots = {"scope": scope_bot, "control": control_bot}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger_path = OUTPUT_DIR / "scope_fb_shadow01_paired_ledger.jsonl"
    manifest_path = OUTPUT_DIR / "scope_fb_shadow01_manifest.json"
    if ledger_path.exists() or manifest_path.exists():
        raise RuntimeError("Refusing to overwrite existing Shadow-01 output")

    started_at = utc_now()
    previous_hash = "GENESIS"
    failures: list[dict[str, Any]] = []
    pair_count = 0

    for packet in packets:
        question = BinaryQuestion(
            question_text=packet.question_text,
            background_info=packet.background_info,
            resolution_criteria=packet.resolution_criteria,
            fine_print=packet.fine_print,
        )
        order = deterministic_arm_order(packet.snapshot_sha256)
        arm_results: dict[str, Any] = {}

        for arm in order:
            arm_started = utc_now()
            try:
                prediction = await bots[arm]._run_forecast_on_binary(  # noqa: SLF001 - frozen benchmark interface
                    copy.deepcopy(question),
                    "",
                )
                result = {
                    "kind": "prediction",
                    **_prediction_record(prediction),
                }
            except Exception as exc:  # keep paired ledger complete; never replace a failed target
                result = {
                    "kind": "exception",
                    "exception_type": type(exc).__name__,
                    "exception_message_sha256": hashlib.sha256(
                        str(exc).encode("utf-8", errors="replace")
                    ).hexdigest(),
                }
                failures.append({"key": packet.key, "arm": arm, "type": type(exc).__name__})
            arm_results[arm] = {
                "started_at_utc": arm_started,
                "finished_at_utc": utc_now(),
                "input_snapshot_sha256": packet.snapshot_sha256,
                "result": result,
            }

        require(
            arm_results["scope"]["input_snapshot_sha256"]
            == arm_results["control"]["input_snapshot_sha256"],
            "Input parity failure",
        )
        record = {
            "shadow_id": SHADOW_ID,
            "key": packet.key,
            "question_id": packet.question_id,
            "source": packet.source,
            "source_type": packet.source_type,
            "resolution_date": packet.resolution_date,
            "question_snapshot_sha256": packet.snapshot_sha256,
            "execution_order": order,
            "scope": arm_results["scope"],
            "control": arm_results["control"],
            "previous_record_sha256": previous_hash,
        }
        record_hash = canonical_sha256(record)
        record["record_sha256"] = record_hash
        _append_fsync_jsonl(ledger_path, record)
        previous_hash = record_hash
        pair_count += 1

    completed_at = utc_now()
    ledger_sha256 = sha256_file(ledger_path)
    manifest = {
        "schema_version": "0.1",
        "shadow_id": SHADOW_ID,
        "status": "FORECASTS_FROZEN_NO_OUTCOMES_ACCESSED",
        "official_forecastbench_submission": False,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "gate": gate,
        "target": {
            "repository": TARGET_REPOSITORY,
            "publication_commit": TARGET_PUBLICATION_COMMIT,
            "path": TARGET_PATH,
            "git_blob_sha": TARGET_BLOB_SHA,
            "size_bytes": TARGET_SIZE_BYTES,
        },
        "target_content_sha256": hashlib.sha256(target_bytes).hexdigest(),
        "selection_audit": selection_audit,
        "pair_count": pair_count,
        "failure_count": len(failures),
        "failures": failures,
        "ledger_tip_sha256": previous_hash,
        "ledger_file_sha256": ledger_sha256,
        "models": {
            "reasoning": REASONING_MODEL,
            "parser": PARSER_MODEL,
            "temperature": TEMPERATURE,
            "timeout_seconds": TIMEOUT_SECONDS,
            "allowed_tries": ALLOWED_TRIES,
            "external_research": False,
            "publish": False,
        },
        "outcome_accessed_during_run": False,
        "interpretation_guardrail": (
            "Late prospective shadow only; not an official ForecastBench submission and not "
            "leaderboard-equivalent because forecasts occur after the official 2026-08-30 window."
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with manifest_path.open("r+") as handle:
        os.fsync(handle.fileno())

    print(json.dumps({
        "status": manifest["status"],
        "pair_count": pair_count,
        "failure_count": len(failures),
        "ledger_tip_sha256": previous_hash,
        "ledger_file_sha256": ledger_sha256,
    }, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
