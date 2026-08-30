import asyncio
import logging

from forecasting_tools import GeneralLlm
from main import SummerTemplateBot2026


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def run() -> None:
    bot = SummerTemplateBot2026(
        research_reports_per_question=1,
        predictions_per_research_report=1,
        use_research_summary_to_forecast=False,
        publish_reports_to_metaculus=True,
        folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=False,
        extra_metadata_in_explanation=True,
        llms={
            "default": GeneralLlm(
                model="openrouter/openai/gpt-4o",
                temperature=0.3,
                timeout=40,
                allowed_tries=2,
            ),
            "summarizer": "openrouter/openai/gpt-4o-mini",
            "researcher": "no_research",
            "parser": "openrouter/openai/gpt-4o-mini",
        },
    )

    reports = await bot.forecast_on_tournament(
        "bot-testing-area",
        return_exceptions=True,
    )
    bot.log_report_summary(reports)

    errors = [report for report in reports if isinstance(report, Exception)]
    if errors:
        raise RuntimeError(f"Smoke test completed with {len(errors)} forecast error(s)")


if __name__ == "__main__":
    asyncio.run(run())
