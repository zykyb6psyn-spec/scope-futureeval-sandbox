from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from forecasting_tools import BinaryQuestion, QuestionState

from main import SummerTemplateBot2026
from scope_input_sanitization import SANITIZED_FIELDS, assert_cycle1_sanitized, sanitize_question_for_cycle1
from scope_paired_dryrun import load_config, restricted_question_snapshot
from scope_structured_bot import ScopeStructuredBot2026


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "parity_validation_output"
OUT.mkdir(exist_ok=True)

LEAK_CANARY = "SCOPE_LEAK_CANARY_7f0d5b"
FORBIDDEN_SOURCE_REFERENCES = {
    "num_forecasters",
    "num_predictions",
    "previous_forecasts",
    "api_json",
    "custom_metadata",
    "cp_reveal_time",
    "includes_bots_in_aggregates",
    "resolution_string",
    "actual_resolution_time",
}

SUPPORTED_FORECAST_METHODS = [
    "_run_forecast_on_binary",
    "_run_forecast_on_multiple_choice",
    "_run_forecast_on_numeric",
    "_run_forecast_on_date",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_canary_question() -> BinaryQuestion:
    q = BinaryQuestion(
        question_text="Will the canary-free allowed event occur?",
        id_of_post=55,
        id_of_question=101,
        page_url="https://www.metaculus.com/questions/55",
        state=QuestionState.OPEN,
        background_info="Allowed public background.",
        resolution_criteria="Resolve Yes if the stated event occurs.",
        fine_print="Allowed public fine print.",
        api_json={"hidden": LEAK_CANARY},
        custom_metadata={"hidden": LEAK_CANARY},
    )
    # These assignments intentionally seed prohibited fields. Pydantic models do
    # not validate assignment by default; sanitization must remove every canary.
    q.num_forecasters = 987654
    q.num_predictions = 123456
    q.resolution_string = LEAK_CANARY
    q.tournament_slugs = [LEAK_CANARY]
    q.question_weight = 99.0
    q.previous_forecasts = None
    return q


def assert_no_forbidden_references(bot_class: type) -> list[str]:
    checked: list[str] = []
    for method_name in SUPPORTED_FORECAST_METHODS:
        method = getattr(bot_class, method_name)
        source = inspect.getsource(method)
        for forbidden in FORBIDDEN_SOURCE_REFERENCES:
            require(
                forbidden not in source,
                f"{bot_class.__name__}.{method_name} directly references prohibited field {forbidden}",
            )
        checked.append(f"{bot_class.__name__}.{method_name}")
    return checked


def main() -> None:
    tests: list[str] = []

    raw = make_canary_question()
    sanitized = sanitize_question_for_cycle1(raw)
    assert_cycle1_sanitized(sanitized)

    for field, expected in SANITIZED_FIELDS.items():
        if hasattr(sanitized, field):
            require(getattr(sanitized, field) == expected, f"field {field} not sanitized")
    tests.append("all known prohibited question-object fields are physically sanitized")

    require(sanitized.question_text == raw.question_text, "allowed question text changed")
    require(sanitized.background_info == raw.background_info, "allowed background changed")
    require(sanitized.resolution_criteria == raw.resolution_criteria, "allowed criteria changed")
    require(sanitized.fine_print == raw.fine_print, "allowed fine print changed")
    require(sanitized.id_of_question == raw.id_of_question, "immutable question ID changed")
    require(sanitized.id_of_post == raw.id_of_post, "post ID changed")
    tests.append("allowed evidence and immutable identity survive sanitization")

    dumped = json.dumps(sanitized.model_dump(mode="json"), sort_keys=True, default=str)
    require(LEAK_CANARY not in dumped, "canary survived sanitized question object")
    tests.append("hidden canary data is absent from sanitized question serialization")

    snapshot = restricted_question_snapshot(sanitized)
    snapshot_text = json.dumps(snapshot, sort_keys=True, default=str)
    require(LEAK_CANARY not in snapshot_text, "canary leaked into immutable forecast snapshot")
    require(snapshot["question_id"] == "101", "snapshot question ID missing")
    require(snapshot["cluster_id"] == "post:55", "snapshot cluster identity incorrect")
    tests.append("restricted snapshot contains no hidden canary and preserves scoring identity")

    allowed_snapshot_keys = {
        "question_id",
        "post_id",
        "cluster_id",
        "question_type",
        "page_url",
        "question_text",
        "background_info",
        "resolution_criteria",
        "fine_print",
        "open_time",
        "close_time",
        "group_question_option",
    }
    require(set(snapshot) == allowed_snapshot_keys, f"unexpected binary snapshot keys: {sorted(set(snapshot)-allowed_snapshot_keys)}")
    tests.append("binary snapshot schema is explicit and closed")

    checked_methods = []
    checked_methods.extend(assert_no_forbidden_references(SummerTemplateBot2026))
    checked_methods.extend(assert_no_forbidden_references(ScopeStructuredBot2026))
    tests.append("supported SCOPE and control forecast methods do not directly reference prohibited fields")

    config = load_config()
    require(config["information_policy"]["external_research"] == "DISABLED_CYCLE1", "external research gate opened")
    require(config["information_policy"]["community_prediction"] == "PROHIBITED", "Community Prediction gate opened")
    require(config["information_policy"]["leaderboard_signal"] == "PROHIBITED", "leaderboard gate opened")
    require(config["information_policy"]["cross_arm_forecast_visibility"] == "PROHIBITED", "cross-arm gate opened")
    require(config["publish_during_dryrun"] is False, "dry-run publishing enabled")
    require(config["scored_run_enabled"] is False, "scored execution enabled")
    tests.append("Cycle-1 information and scored-execution gates remain closed")

    parity = config["parity"]
    require(parity["same_reasoning_model"] is True, "reasoning model parity not required")
    require(parity["same_parser_model"] is True, "parser model parity not required")
    require(parity["same_temperature"] is True, "temperature parity not required")
    require(parity["same_question_snapshot"] is True, "question snapshot parity not required")
    require(parity["same_research_input"] is True, "research-input parity not required")
    require(parity["enable_summarize_research"] is False, "research summarization re-enabled")
    require(parity["use_research_summary_to_forecast"] is False, "research summary entered forecast path")
    tests.append("matched-arm model, input and research parity constraints are explicit")

    record = {
        "schema_version": "1.0",
        "status": "PASS",
        "test_count": len(tests),
        "tests": tests,
        "source_methods_checked": checked_methods,
        "sanitized_fields": sorted(SANITIZED_FIELDS),
        "implementation_hashes": {
            "scope_input_sanitization.py": sha256_file(ROOT / "scope_input_sanitization.py"),
            "scope_paired_dryrun.py": sha256_file(ROOT / "scope_paired_dryrun.py"),
            "scope_structured_bot.py": sha256_file(ROOT / "scope_structured_bot.py"),
            "scope_cycle1_config_draft.json": sha256_file(ROOT / "scope_cycle1_config_draft.json"),
            "scope_parity_validation.py": sha256_file(ROOT / "scope_parity_validation.py"),
            "main.py": sha256_file(ROOT.parent / "main.py"),
        },
        "interpretation": (
            "Cycle-1 forecast objects are sanitized before either arm receives them; known aggregate, "
            "prior-forecast, hidden API and resolution fields are removed, the immutable scoring identity "
            "is retained, and supported forecast methods have no direct references to prohibited fields."
        ),
    }
    (OUT / "parity_validation_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
