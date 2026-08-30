import asyncio
import logging
import os

from forecasting_tools import GeneralLlm
from main import SummerTemplateBot2026
from scope_audit import build_pre_run_manifest, finalize_manifest, load_json


CONFIG_PATH = "scope_sandbox_config.json"
PREREG_PATH = "scope_preregistration.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def validate_isolation(config: dict, prereg: dict) -> None:
    """Fail closed if a technical smoke test could touch a scored/live target."""
    if config.get("target") != "bot-testing-area":
        raise RuntimeError("Isolation gate: smoke test target must be bot-testing-area")

    scored_cfg = config.get("scored_submission", {})
    if scored_cfg.get("enabled") is not False:
        raise RuntimeError("Isolation gate: scored submission must remain disabled")

    if prereg.get("scored_run_enabled") is not False:
        raise RuntimeError("Isolation gate: preregistration must keep scored_run_enabled=false")

    if prereg.get("status") != "NOT_FROZEN":
        raise RuntimeError("Isolation gate: this technical smoke test expects an unfrozen scored preregistration")

    if config.get("models", {}).get("researcher") != "no_research":
        raise RuntimeError("Isolation gate: technical smoke test must keep external research disabled")

    missing = [name for name in ("METACULUS_TOKEN", "OPENROUTER_API_KEY") if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required GitHub secret(s): {', '.join(missing)}")


async def run() -> None:
    config = load_json(CONFIG_PATH)
    prereg = load_json(PREREG_PATH)
    validate_isolation(config, prereg)
    pre_manifest = build_pre_run_manifest(config, prereg)

    default_cfg = config["models"]["default"]
    reports: list = []

    try:
        bot = SummerTemplateBot2026(
            research_reports_per_question=config["research_reports_per_question"],
            predictions_per_research_report=config["predictions_per_research_report"],
            use_research_summary_to_forecast=config["use_research_summary_to_forecast"],
            publish_reports_to_metaculus=config["publish_reports_to_metaculus"],
            folder_to_save_reports_to=None,
            skip_previously_forecasted_questions=config["skip_previously_forecasted_questions"],
            extra_metadata_in_explanation=config["extra_metadata_in_explanation"],
            llms={
                "default": GeneralLlm(
                    model=default_cfg["model"],
                    temperature=default_cfg["temperature"],
                    timeout=default_cfg["timeout_seconds"],
                    allowed_tries=default_cfg["allowed_tries"],
                ),
                "summarizer": config["models"]["summarizer"],
                "researcher": config["models"]["researcher"],
                "parser": config["models"]["parser"],
            },
        )

        reports = await bot.forecast_on_tournament(
            config["target"],
            return_exceptions=True,
        )
        bot.log_report_summary(reports)

        errors = [report for report in reports if isinstance(report, Exception)]
        if errors:
            finalize_manifest(
                pre_manifest,
                reports,
                status="completed_with_forecast_errors",
                error_summary=f"{len(errors)} forecast exception(s)",
            )
            raise RuntimeError(f"Smoke test completed with {len(errors)} forecast error(s)")

        finalize_manifest(pre_manifest, reports, status="success")
        logger.info("SCOPE FutureEval sandbox smoke test completed successfully")

    except Exception as exc:
        # Preserve an audit artifact even when failure occurs before forecast reports exist.
        post_path_exists = os.path.exists("scope_audit_output/post_run_manifest.json")
        if not post_path_exists:
            finalize_manifest(
                pre_manifest,
                reports,
                status="failed",
                error_summary=f"{type(exc).__name__}: {exc}",
            )
        raise


if __name__ == "__main__":
    asyncio.run(run())
