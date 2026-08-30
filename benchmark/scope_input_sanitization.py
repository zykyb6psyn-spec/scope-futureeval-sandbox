from __future__ import annotations

from typing import Any


# Fields that may contain aggregate, prior-forecast, hidden platform, resolved,
# targeting or otherwise non-Cycle-1 information. They are deliberately removed
# from the object passed into either reasoning arm.
SANITIZED_FIELDS: dict[str, Any] = {
    "num_forecasters": None,
    "num_predictions": None,
    "actual_resolution_time": None,
    "published_time": None,
    "scheduled_resolution_time": None,
    "already_forecasted": None,
    "tournament_slugs": [],
    "default_project_id": None,
    "includes_bots_in_aggregates": None,
    "cp_reveal_time": None,
    "question_weight": None,
    "resolution_string": None,
    "previous_forecasts": None,
    "api_json": {},
    "custom_metadata": {},
    "categories": [],
}

# Explicit model-visible question materials for Cycle 1. Identity/routing fields
# are allowed to remain on the object for provenance/submission but are not
# forecast evidence.
MODEL_VISIBLE_FIELDS = {
    "question_text",
    "background_info",
    "resolution_criteria",
    "fine_print",
    "open_time",
    "close_time",
    "group_question_option",
    "options",
    "unit_of_measure",
    "lower_bound",
    "upper_bound",
    "open_lower_bound",
    "open_upper_bound",
    "zero_point",
}

IDENTITY_ROUTING_FIELDS = {
    "id_of_question",
    "id_of_post",
    "page_url",
    "state",
    "date_accessed",
    "question_ids_of_group",
    "conditional_type",
}


def sanitize_question_for_cycle1(question: Any) -> Any:
    """Return a deep copied question with non-Cycle-1 information removed.

    Pydantic v2's model_copy is preferred because all forecasting-tools question
    models are BaseModel subclasses. A defensive fallback supports test doubles.
    """
    if hasattr(question, "model_copy"):
        sanitized = question.model_copy(deep=True)
    else:
        import copy

        sanitized = copy.deepcopy(question)

    for field, replacement in SANITIZED_FIELDS.items():
        if hasattr(sanitized, field):
            value = list(replacement) if isinstance(replacement, list) else dict(replacement) if isinstance(replacement, dict) else replacement
            setattr(sanitized, field, value)

    return sanitized


def assert_cycle1_sanitized(question: Any) -> None:
    """Fail closed when any known prohibited field still carries information."""
    for field, expected in SANITIZED_FIELDS.items():
        if not hasattr(question, field):
            continue
        actual = getattr(question, field)
        if actual != expected:
            raise RuntimeError(
                f"Cycle-1 leakage gate failed: field {field!r} was not sanitized"
            )
