from __future__ import annotations

from pathlib import Path

from scope_audit import canonical_sha256, load_json, sha256_file


CONFIG_PATH = "scope_sandbox_config.json"
PREREG_PATH = "scope_preregistration.json"
SMOKE_WORKFLOW_PATH = ".github/workflows/scope_smoke_test.yaml"
INTEGRITY_WORKFLOW_PATH = ".github/workflows/scope_integrity_check.yaml"


def main() -> None:
    config = load_json(CONFIG_PATH)
    prereg = load_json(PREREG_PATH)

    assert config.get("target") == "bot-testing-area", "Smoke-test target must be bot-testing-area"
    assert config.get("publish_reports_to_metaculus") is True, "Smoke test should exercise the full publish path"
    assert config.get("scored_submission", {}).get("enabled") is False, "Scored submission must be disabled"
    assert config.get("scored_submission", {}).get("allowed_targets") == [], "No scored targets may be allowed"
    assert config.get("models", {}).get("researcher") == "no_research", "External research must remain disabled for plumbing test"

    runtime = config.get("runtime", {})
    assert runtime.get("runner") == "ubuntu-24.04", "Runner version must remain pinned"
    assert runtime.get("python") == "3.11.16", "Python patch version must remain pinned"
    assert runtime.get("poetry") == "2.4.2", "Poetry version must remain pinned"

    assert prereg.get("status") == "NOT_FROZEN", "Current scored preregistration must remain NOT_FROZEN"
    assert prereg.get("scored_run_enabled") is False, "Current scored run gate must remain disabled"
    assert prereg.get("target_tournament_or_minibench") is None, "No scored target may be pre-filled"

    smoke_workflow = Path(SMOKE_WORKFLOW_PATH).read_text(encoding="utf-8")
    integrity_workflow = Path(INTEGRITY_WORKFLOW_PATH).read_text(encoding="utf-8")

    required_smoke_fragments = [
        "runs-on: ubuntu-24.04",
        'python-version: "3.11.16"',
        'version: "2.4.2"',
        "persist-credentials: false",
        "poetry sync --no-interaction --no-root",
        "if-no-files-found: error",
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "snok/install-poetry@a783c322200f0519c7926aa6faa857c4e23e9263",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    ]
    for fragment in required_smoke_fragments:
        assert fragment in smoke_workflow, f"Smoke workflow drift: missing {fragment}"

    required_integrity_fragments = [
        "runs-on: ubuntu-24.04",
        'python-version: "3.11.16"',
        "persist-credentials: false",
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    ]
    for fragment in required_integrity_fragments:
        assert fragment in integrity_workflow, f"Integrity workflow drift: missing {fragment}"

    print("SCOPE sandbox integrity check: PASS")
    print(f"config_sha256={canonical_sha256(config)}")
    print(f"preregistration_sha256={canonical_sha256(prereg)}")
    print(f"scope_smoke_test_sha256={sha256_file('scope_smoke_test.py')}")
    print(f"scope_audit_sha256={sha256_file('scope_audit.py')}")
    print(f"poetry_lock_sha256={sha256_file('poetry.lock')}")
    print(f"smoke_workflow_sha256={sha256_file(SMOKE_WORKFLOW_PATH)}")
    print(f"integrity_workflow_sha256={sha256_file(INTEGRITY_WORKFLOW_PATH)}")


if __name__ == "__main__":
    main()
