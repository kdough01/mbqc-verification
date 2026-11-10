"""
heldout.py — held-out expected values: sealed in the repository, readable only where the key is.

A held-out value is a number a check compares against that the proposer must not see, so it cannot tune a
proposal to it. It is sealed (Fernet: AES-128-CBC + HMAC-SHA256) with a key that lives only in the
repository secret HELDOUT_KEY, which the `verify` workflow passes to `dagtool run` on pushes. The proposals gate,
`dagtool feedback` and any local run do not have it, so there the check is a skip ("evaluated in CI only").
Evidence never records a held-out value or how far a result is from it: only whether it matched.

    dagtool heldout keygen                         a new key, to store as the HELDOUT_KEY secret (once)
    HELDOUT_KEY=... dagtool heldout seal ID VALUE  seal a value as dag/heldout/<ID>.json
    dagtool heldout list                           the sealed ids (never their values)

In a check: expect: {heldout: ID} (reproduction and tool checks).
Limits: whoever holds the key can read the values; sealing protects them from proposers, not from the owner.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

KEY_ENV = "HELDOUT_KEY"
ID_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,80}")


class HeldOutUnavailable(RuntimeError):
    """No key here: the value can only be read in CI."""


def store(root: Path) -> Path:
    return root / "dag" / "heldout"


def keygen() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def _fernet(key: str | None = None):
    from cryptography.fernet import Fernet
    key = key or os.environ.get(KEY_ENV)
    if not key:
        raise HeldOutUnavailable(f"held-out value: evaluated in CI only ({KEY_ENV} is not set here)")
    return Fernet(key.encode())


def seal(root: Path, hid: str, value: float, note: str = "", key: str | None = None) -> Path:
    if not ID_RE.fullmatch(hid):
        raise ValueError("held-out ids are lowercase letters, digits, '.', '_' and '-'")
    token = _fernet(key).encrypt(json.dumps({"id": hid, "value": float(value)}).encode()).decode()
    path = store(root) / f"{hid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": hid, "sealed": token, "note": note,
                                "sealed_at": time.strftime("%Y-%m-%d", time.gmtime())}, indent=1) + "\n",
                    encoding="utf-8")
    return path


def value(root: Path, hid: str, key: str | None = None) -> float:
    path = store(root) / f"{hid}.json"
    if not ID_RE.fullmatch(hid) or not path.exists():
        raise KeyError(f"no held-out value {hid!r} under dag/heldout/")
    f = _fernet(key)          # raises HeldOutUnavailable first, so a missing key never looks like a bad file
    from cryptography.fernet import InvalidToken
    try:
        data = json.loads(f.decrypt(json.loads(path.read_text(encoding="utf-8"))["sealed"].encode()))
    except InvalidToken as e:
        raise ValueError(f"held-out value {hid!r} does not open with this key") from e
    if data.get("id") != hid:
        raise ValueError(f"held-out file {hid!r} holds a value sealed for {data.get('id')!r}")
    return float(data["value"])


def ids(root: Path) -> list[str]:
    return sorted(p.stem for p in store(root).glob("*.json"))
