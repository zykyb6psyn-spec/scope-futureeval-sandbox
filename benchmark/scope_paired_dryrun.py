from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forecasting_tools import (
    BinaryQuestion,
    DateQuestion,
    GeneralLlm,
    MetaculusClient,
    MultipleChoiceQuestion,
    NumericQuestion,
)

from main import SummerTemplateBot2026
from scope_structured_bot import ScopeStructuredBot2026


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "scope_cycle1_config_draft.json"
OUTPUT_DIR = ROOT / "dryrun_output"
OUTPUT_DIR.mkdir(exist_ok=True)

SUPPORTED_TYPES = (BinaryQuestion, MultipleChoiceQuestion, NumericQuestion, DateQuestion)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_data(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def restricted_question_snapshot(question: Any) -> dict[str, Any]:
    """Only fields intentionally available to both reasoning arms.

    Community/aggregate/leaderboard fields are deliberately not serialized.
    """
    data: dict[str, Any] = {
        "question_type": type(question).__name__,
        "page_url": str(getattr(question, "page_url", "")),
        "question_text": getattr(question, "question_text", None),
        "background_info": getattr(question, "background_info", None),
        "resolution_criteria": getattr(question, "resolution_criteria", None),
        "fine_print": getattr(question, "fine_print", None),
        "open_time": str(getattr(question, "open_time", None)),
        "close_time": str(getattr(question, "close_time", None)),
    }

    if isinstance(question, MultipleChoiceQuestion):
        data["options"] = list(question.options)

    if isinstance(question, (NumericQuestion, DateQuestion)):
        data.update(
            {
                "lower_bound": str(getattr(question, "lower_bound", None)),
                "upper_bound": str(getattr(question, "upper_bound", None)),
                "open_lower_bound": getattr(question, "open_lower_bound", None),
                "open_upper_bound": getattr(question, "open_upper_bound", None),
                "unit_of_measure": getattr(question, "unit_of_measure", None),
            }
        )

    return data


def serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except Exception:
            return value.model_dump()
    return repr(value)


def report_record(report: Any) -> dict[str, Any]:
    if isinstance(report, BaseException):
        return {
            "kind": "exception",
            "exception_type": type(report).__name__,
            "exception_message": str(report),
        }

    prediction = getattr(report, "prediction", None)
    explanation = getattr(report, "explanation", None)
    errors = getattr(report, "errors", None)
    return {
        "kind": "forecast_report",
        "report_type": type(report).__name__,
        "prediction": serialize_value(prediction),
        "prediction_sha256": sha256_data(serialize_value(prediction)),
        "explanation_sha256": hashlib.sha256(str(explanation).encode("utf-8", errors="replace")).hexdigest(),
        "errors": serialize_value(errors),
    }


def make_llms(config: dict[str, Any]) -> dict[str, Any]:
    model = config["model"]
    return {
        "default": GeneralLlm(
            model=model["reasoning"],
            temperature=model["temperature"],
            timeout=model["timeout_seconds"],
            allowed_tries=model["allowed_tries"],
        ),
        "summarizer": model["parser"],
        "researcher": "no_research",
        "parser": model["parser"],
    }


def make_bot(bot_class: type, config: dict[str, Any]):
    parity = config["parity"]
    return bot_class(
        research_reports_per_question=parity["research_reports_per_question"],
        predictions_per_research_report=parity["predictions_per_research_report"],
        use_research_summary_to_forecast=parity["use_research_summary_to_forecast"],
        enable_summarize_research=parity["enable_summarize_research"],
        publish_reports_to_metaculus=config["publish_during_dryrun"],
        folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=False,
        extra_metadata_in_explanation=False,
        llms=make_llms(config),
    )


def validate_dryrun_gate(config: dict[str, Any]) -> None:
    require(config.get("status") == "DESIGN_DRAFT", "Dry run expects DESIGN_DRAFT config")
    require(config.get("technical_dryrun_target") == "bot-testing-area",
            "Dry run target must be bot-testing-area")
    require(config.get("scored_target") is None, "Scored target must remain unset")
    require(config.get("publish_during_dryrun") is False,
            "Paired dry run must not publish forecasts")
    require(config.get("scored_run_enabled") is False,
            "Scored run must remain disabled")

    info = config.get("information_policy", {})
    require(info.get("external_research") == "DISABLED_CYCLE1",
            "Cycle 1 dry run must keep external research disabled")
    require(info.get("community_prediction") == "PROHIBITED",
            "Community Prediction must remain prohibited")
    require(info.get("leaderboard_signal") == "PROHIBITED",
            "Leaderboard signal must remain prohibited")
    require(info.get("cross_arm_forecast_visibility") == "PROHIBITED",
            "Cross-arm forecast visibility must remain prohibited")

    missing = [name for name in ("METACULUS_TOKEN", "OPENROUTER_API_KEY") if not os.environ.get(name)]
    require(not missing, f"Missing required secret(s): {', '.join(missing)}")


def deterministic_arm_order(snapshot_sha256: str, seed: int) -> list[str]:
    derived = int(snapshot_sha256[:16], 16) ^ seed
    rng = random.Random(derived)
    order = ["scope", "control"]
    rng.shuffle(order)
    return order


async def run() -> None:
    config = load_config()
    validate_dryrun_gate(config)

    client = MetaculusClient()
    questions = client.get_all_open_questions_from_tournament(config["technical_dryrun_target"])

    scope_bot = make_bot(ScopeStructuredBot2026, config)
    control_bot = make_bot(SummerTemplateBot2026, config)
    bots = {"scope": scope_bot, "control": control_bot}

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "run_kind": "paired_technical_dryrun",
        "started_at_utc": utc_now(),
        "config_sha256": sha256_data(config),
        "target": config["technical_dryrun_target"],
        "publish": False,
        "question_count_retrieved": len(questions),
        "paired_records": [],
        "exclusions": [],
    }

    previous_hash = "GENESIS"
    seed = config["randomization"]["arm_execution_order_seed"]

    for question in questions:
        snapshot = restricted_question_snapshot(question)
        snapshot_sha = sha256_data(snapshot)

        if not isinstance(question, SUPPORTED_TYPES):
            manifest["exclusions"].append(
                {
                    "question_url": snapshot.get("page_url"),
                    "question_type": snapshot.get("question_type"),
                    "reason_code": "UNSUPPORTED_FROZEN_FORMAT",
                    "snapshot_sha256": snapshot_sha,
                }
            )
            continue

        order = deterministic_arm_order(snapshot_sha, seed)
        arm_results: dict[str, Any] = {}

        for arm in order:
            started = utc_now()
            report = await bots[arm].forecast_question(copy.deepcopy(question), return_exceptions=True)
            finished = utc_now()
            arm_results[arm] = {
                "started_at_utc": started,
                "finished_at_utc": finished,
                "result": report_record(report),
            }

        record = {
            "question_url": snapshot.get("page_url"),
            "question_type": snapshot.get("question_type"),
            "question_snapshot_sha256": snapshot_sha,
            "execution_order": order,
            "scope": arm_results["scope"],
            "control": arm_results["control"],
            "previous_record_sha256": previous_hash,
        }
        record_hash = sha256_data(record)
        record["record_sha256"] = record_hash
        previous_hash = record_hash
        manifest["paired_records"].append(record)

    manifest["completed_at_utc"] = utc_now()
    manifest["paired_question_count"] = len(manifest["paired_records"])
    manifest["exclusion_count"] = len(manifest["exclusions"])
    manifest["ledger_tip_sha256"] = previous_hash

    scope_failures = sum(
        1 for record in manifest["paired_records"]
        if record["scope"]["result"]["kind"] == "exception"
    )
    control_failures = sum(
        1 for record in manifest["paired_records"]
        if record["control"]["result"]["kind"] == "exception"
    )
    manifest["scope_failure_count"] = scope_failures
    manifest["control_failure_count"] = control_failures

    output_path = OUTPUT_DIR / "paired_dryrun_manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Retrieved questions: {len(questions)}")
    print(f"Paired supported questions: {manifest['paired_question_count']}")
    print(f"Exclusions: {manifest['exclusion_count']}")
    print(f"SCOPE failures: {scope_failures}")
    print(f"Control failures: {control_failures}")
    print(f"Ledger tip: {previous_hash}")
    print(f"Manifest: {output_path}")

    if scope_failures or control_failures:
        raise RuntimeError("Paired dry run completed with arm failure(s)")


if __name__ == "__main__":
    asyncio.run(run())
