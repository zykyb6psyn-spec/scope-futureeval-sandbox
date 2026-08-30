from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


AUDIT_DIR = Path("scope_audit_output")
AUDIT_DIR.mkdir(exist_ok=True)

TRACKED_FILES = [
    "scope_smoke_test.py",
    "scope_audit.py",
    "scope_sandbox_config.json",
    "scope_preregistration.json",
    "main.py",
    "pyproject.toml",
    "poetry.lock",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(data: Any) -> str:
    return sha256_bytes(canonical_json(data).encode("utf-8"))


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def file_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in TRACKED_FILES:
        p = Path(path)
        if p.exists():
            hashes[path] = sha256_file(p)
    return hashes


def github_context() -> dict[str, Any]:
    keys = [
        "GITHUB_ACTION",
        "GITHUB_ACTOR",
        "GITHUB_JOB",
        "GITHUB_REF",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_NUMBER",
        "GITHUB_SHA",
        "GITHUB_WORKFLOW",
        "RUNNER_NAME",
        "RUNNER_OS",
        "RUNNER_ARCH",
    ]
    return {key: os.environ.get(key) for key in keys}


def build_pre_run_manifest(config: dict[str, Any], prereg: dict[str, Any]) -> dict[str, Any]:
    hashes = file_hashes()
    manifest = {
        "manifest_schema": "1.0",
        "phase": "pre_run",
        "created_at_utc": utc_now(),
        "run_kind": os.environ.get("SCOPE_RUN_KIND", "unknown"),
        "github": github_context(),
        "config": config,
        "config_sha256": canonical_sha256(config),
        "preregistration": prereg,
        "preregistration_sha256": canonical_sha256(prereg),
        "tracked_file_sha256": hashes,
        "integrity_note": "This manifest records configuration and code provenance before forecast execution.",
    }
    write_json(AUDIT_DIR / "pre_run_manifest.json", manifest)
    _write_sha256s(hashes | {
        "scope_sandbox_config.json::canonical": manifest["config_sha256"],
        "scope_preregistration.json::canonical": manifest["preregistration_sha256"],
    })
    return manifest


def _safe_question_url(report: Any) -> str | None:
    for attr in ("question", "question_obj"):
        obj = getattr(report, attr, None)
        url = getattr(obj, "page_url", None) if obj is not None else None
        if url:
            return str(url)
    for attr in ("question_url", "page_url"):
        url = getattr(report, attr, None)
        if url:
            return str(url)
    return None


def build_hash_chained_ledger(reports: Iterable[Any]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    previous_hash = "GENESIS"
    for index, report in enumerate(reports):
        is_error = isinstance(report, Exception)
        stable_repr_hash = sha256_bytes(repr(report).encode("utf-8", errors="replace"))
        record = {
            "index": index,
            "recorded_at_utc": utc_now(),
            "kind": "exception" if is_error else "forecast_report",
            "report_type": type(report).__name__,
            "question_url": None if is_error else _safe_question_url(report),
            "exception_type": type(report).__name__ if is_error else None,
            "exception_message": str(report) if is_error else None,
            "object_repr_sha256": stable_repr_hash,
            "previous_record_sha256": previous_hash,
        }
        record_hash = canonical_sha256(record)
        record["record_sha256"] = record_hash
        ledger.append(record)
        previous_hash = record_hash

    ledger_path = AUDIT_DIR / "forecast_ledger.jsonl"
    with ledger_path.open("w", encoding="utf-8") as f:
        for record in ledger:
            f.write(canonical_json(record) + "\n")
    return ledger


def finalize_manifest(
    pre_manifest: dict[str, Any],
    reports: list[Any],
    status: str,
    error_summary: str | None = None,
) -> dict[str, Any]:
    ledger = build_hash_chained_ledger(reports)
    errors = [r for r in reports if isinstance(r, Exception)]
    manifest = {
        "manifest_schema": "1.0",
        "phase": "post_run",
        "created_at_utc": utc_now(),
        "status": status,
        "error_summary": error_summary,
        "github": github_context(),
        "pre_run_manifest_sha256": canonical_sha256(pre_manifest),
        "report_count": len(reports),
        "exception_count": len(errors),
        "ledger_record_count": len(ledger),
        "ledger_tip_sha256": ledger[-1]["record_sha256"] if ledger else "GENESIS",
        "tracked_file_sha256": file_hashes(),
        "interpretation": "Technical sandbox evidence only; not evidence of predictive skill or benchmark superiority.",
    }
    write_json(AUDIT_DIR / "post_run_manifest.json", manifest)
    _write_sha256s({
        "pre_run_manifest.json": sha256_file(AUDIT_DIR / "pre_run_manifest.json"),
        "post_run_manifest.json": sha256_file(AUDIT_DIR / "post_run_manifest.json"),
        "forecast_ledger.jsonl": sha256_file(AUDIT_DIR / "forecast_ledger.jsonl"),
    }, append=True)
    return manifest


def _write_sha256s(hashes: dict[str, str], append: bool = False) -> None:
    path = AUDIT_DIR / "SHA256SUMS.txt"
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as f:
        for name, digest in sorted(hashes.items()):
            f.write(f"{digest}  {name}\n")
