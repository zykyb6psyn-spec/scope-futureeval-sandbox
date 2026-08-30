from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_sha256(data: Any) -> str:
    return sha256_bytes(canonical_json(data).encode("utf-8"))


def binding_payload(binding: dict[str, Any]) -> dict[str, Any]:
    """Return the self-hashable target-binding payload.

    `binding_record_sha256` cannot be part of its own digest. All other fields,
    including target identity, freeze provenance and timestamps, are covered.
    """
    return {key: value for key, value in binding.items() if key != "binding_record_sha256"}


def binding_sha256(binding: dict[str, Any]) -> str:
    return canonical_sha256(binding_payload(binding))
