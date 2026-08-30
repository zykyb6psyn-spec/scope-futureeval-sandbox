from __future__ import annotations

from scope_audit import canonical_sha256, load_json, sha256_file


CONFIG_PATH = "scope_sandbox_config.json"
PREREG_PATH = "scope_preregistration.json"


def main() -> None:
    config = load_json(CONFIG_PATH)
    prereg = load_json(PREREG_PATH)

    assert config.get("target") == "bot-testing-area", "Smoke-test target must be bot-testing-area"
    assert config.get("publish_reports_to_metaculus") is True, "Smoke test should exercise the full publish path"
    assert config.get("scored_submission", {}).get("enabled") is False, "Scored submission must be disabled"
    assert config.get("scored_submission", {}).get("allowed_targets") == [], "No scored targets may be allowed"
    assert config.get("models", {}).get("researcher") == "no_research", "External research must remain disabled for plumbing test"

    assert prereg.get("status") == "NOT_FROZEN", "Current scored preregistration must remain NOT_FROZEN"
    assert prereg.get("scored_run_enabled") is False, "Current scored run gate must remain disabled"
    assert prereg.get("target_tournament_or_minibench") is None, "No scored target may be pre-filled"

    print("SCOPE sandbox integrity check: PASS")
    print(f"config_sha256={canonical_sha256(config)}")
    print(f"preregistration_sha256={canonical_sha256(prereg)}")
    print(f"scope_smoke_test_sha256={sha256_file('scope_smoke_test.py')}")
    print(f"scope_audit_sha256={sha256_file('scope_audit.py')}")
    print(f"poetry_lock_sha256={sha256_file('poetry.lock')}")


if __name__ == "__main__":
    main()
