from __future__ import annotations

from datetime import datetime

from forecasting_tools import (
    BinaryQuestion,
    MultipleChoiceQuestion,
    NumericQuestion,
    clean_indents,
)

from main import SummerTemplateBot2026


class ScopeStructuredBot2026(SummerTemplateBot2026):
    """Cycle-1 SCOPE reasoning treatment arm.

    This subclass deliberately changes only the forecasting reasoning prompts.
    Retrieval, parsing, question models, output schemas and aggregation stay on
    the same upstream template path as the matched control.
    """

    @staticmethod
    def _evidence_text(research: str) -> str:
        if research.strip():
            return research
        return "[No external research in Cycle 1. Use only the supplied question materials.]"

    async def _run_forecast_on_binary(self, question: BinaryQuestion, research: str):
        prompt = clean_indents(
            f"""
            You are the SCOPE structured forecasting arm in a blinded benchmark.
            Your task is to give your sincere probability, not to sound confident.
            Do not invent current facts that are not contained in the materials below.

            QUESTION
            {question.question_text}

            BACKGROUND
            {question.background_info}

            RESOLUTION CRITERIA
            {question.resolution_criteria}

            FINE PRINT
            {question.fine_print}

            SHARED EVIDENCE PACKET
            {self._evidence_text(research)}

            Today is {datetime.now().strftime("%Y-%m-%d")}.

            Apply SCOPE in this fixed order:

            1. EVIDENCE
               List the few observations that actually bear on the outcome.
               For each, distinguish fact/claim/inference and direct/indirect evidence.
               Treat missing public evidence as absence-of-evidence, not evidence-of-absence,
               unless the resolution context makes non-observation genuinely informative.

            2. DEPENDENCY
               Identify which observations may share the same underlying cause.
               Do not double-count correlated signals.

            3. BASE RATE
               State a defensible reference class and starting probability if one exists.
               If no useful reference class exists, say so rather than fabricating one.

            4. SCENARIOS
               Describe the status-quo path, the strongest No path and the strongest Yes path.
               Note the time remaining and any key dependency that must change for the less
               likely path to occur.

            5. PROBABILITY SYNTHESIS
               Update from the base-rate anchor using only the evidence above.
               Avoid unsupported precision and avoid extreme probabilities unless evidence
               is both strong and substantially independent.

            6. CALIBRATION GUARD
               Before finalizing, ask:
               - If the strongest single signal vanished, would the forecast change too much?
               - Is confidence consistent with time remaining and evidence independence?
               - Am I reacting to vividness rather than diagnostic value?
               You may revise once after this check.

            {self._get_conditional_disclaimer_if_necessary(question)}

            End with exactly one final line in this form:
            Probability: ZZ%
            """
        )
        return await self._binary_prompt_to_forecast(question, prompt)

    async def _run_forecast_on_multiple_choice(
        self, question: MultipleChoiceQuestion, research: str
    ):
        prompt = clean_indents(
            f"""
            You are the SCOPE structured forecasting arm in a blinded benchmark.
            Do not invent current facts that are not contained in the supplied materials.

            QUESTION
            {question.question_text}

            OPTIONS
            {question.options}

            BACKGROUND
            {question.background_info}

            RESOLUTION CRITERIA
            {question.resolution_criteria}

            FINE PRINT
            {question.fine_print}

            SHARED EVIDENCE PACKET
            {self._evidence_text(research)}

            Today is {datetime.now().strftime("%Y-%m-%d")}.

            Apply SCOPE in this fixed order:

            1. EVIDENCE
               Identify only observations that discriminate among the options.
               Mark fact/claim/inference and direct/indirect evidence.

            2. DEPENDENCY
               Identify correlated observations and avoid counting one causal signal twice.

            3. BASE RATE
               State the most useful reference-class distribution across options if defensible.
               Otherwise explicitly say that no stable base-rate distribution is available.

            4. SCENARIOS
               Identify the status-quo option/path and the strongest plausible path to each
               materially competitive alternative. Keep tail options non-zero when genuine
               uncertainty remains.

            5. PROBABILITY SYNTHESIS
               Allocate probabilities across all options using the same evidence set.
               Probabilities must sum to 100%.

            6. CALIBRATION GUARD
               Check for overconfidence, duplicated evidence and a neglected plausible option.
               You may revise once after this check.

            {self._get_conditional_disclaimer_if_necessary(question)}

            End with the final probabilities in this exact option order:
            {question.options}

            Use one line per option:
            Option name: probability%
            """
        )
        return await self._multiple_choice_prompt_to_forecast(question, prompt)

    async def _run_forecast_on_numeric(self, question: NumericQuestion, research: str):
        upper_bound_message, lower_bound_message = (
            self._create_upper_and_lower_bound_messages(question)
        )
        prompt = clean_indents(
            f"""
            You are the SCOPE structured forecasting arm in a blinded benchmark.
            Do not invent current facts that are not contained in the supplied materials.

            QUESTION
            {question.question_text}

            BACKGROUND
            {question.background_info}

            RESOLUTION CRITERIA
            {question.resolution_criteria}

            FINE PRINT
            {question.fine_print}

            UNITS
            {question.unit_of_measure if question.unit_of_measure else "Not stated; infer cautiously from the question."}

            SHARED EVIDENCE PACKET
            {self._evidence_text(research)}

            Today is {datetime.now().strftime("%Y-%m-%d")}.

            {lower_bound_message}
            {upper_bound_message}

            Apply SCOPE in this fixed order:

            1. EVIDENCE
               Identify observations that constrain the likely numeric range.
               Mark fact/claim/inference and direct/indirect evidence.

            2. DEPENDENCY
               Identify correlated signals and avoid narrowing the distribution twice for
               evidence that reflects the same underlying driver.

            3. BASE RATE
               Give a defensible reference-class center/range if one exists. If it does not,
               state that explicitly.

            4. SCENARIOS
               Describe the status-quo/central path, a plausible low scenario and a plausible
               high scenario. State the time remaining.

            5. DISTRIBUTION SYNTHESIS
               Produce a distribution that reflects both ordinary variation and meaningful
               tail risk. Do not use false precision.

            6. CALIBRATION GUARD
               Check whether the 10th-90th interval is wide enough for unknown unknowns and
               whether a single correlated evidence cluster has made it too narrow.
               You may revise once after this check.

            Formatting rules:
            - use the requested units;
            - never use scientific notation;
            - percentile values must be monotonically increasing;
            - Percentile 10 must be the lowest and Percentile 90 the highest.

            {self._get_conditional_disclaimer_if_necessary(question)}

            End exactly with:
            Percentile 10: XX
            Percentile 20: XX
            Percentile 40: XX
            Percentile 60: XX
            Percentile 80: XX
            Percentile 90: XX
            """
        )
        return await self._numeric_prompt_to_forecast(question, prompt)
