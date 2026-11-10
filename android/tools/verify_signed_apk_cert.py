"""Fail-closed offline certificate preflight for a manually signed APK.

The expected SHA-256 digest comes from a trusted operator's stored value.
The observed digest comes from Android SDK apksigner --print-certs output.
This script never reads keystore bytes, passwords, API keys, or user data.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

_PATTERN = re.compile(
    r"^Signer #(\d+) certificate SHA-256 digest: ([0-9A-Fa-f]{64})$",
    re.MULTILINE,
)


class SigningIdentityDenied(ValueError):
    pass


def normalize_fingerprint(value: str) -> str:
    if not isinstance(value, str):
        raise SigningIdentityDenied("Expected signing certificate is missing")
    canonical = value.strip().replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", canonical):
        raise SigningIdentityDenied("Expected signing certificate is invalid")
    return canonical


def check_apk_identity(output: str, expected: str) -> bool:
    if not isinstance(output, str):
        raise SigningIdentityDenied("Android signer verification unavailable")
    matches = _PATTERN.findall(output)
    if len(matches) != 1 or matches[0][0] != "1":
        raise SigningIdentityDenied("Exactly one verified APK signer is required")
    if normalize_fingerprint(matches[0][1]) != normalize_fingerprint(expected):
        raise SigningIdentityDenied("APK signer does not match the trusted certificate")
    if "Verifies" not in output:
        raise SigningIdentityDenied("SDK APK verification status is absent")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: verify_signed_apk_cert.py <apksigner-output-file>", file=sys.stderr)
        return 2
    try:
        expected = os.environ.get("EDGE_ANDROID_EXPECTED_CERT_SHA256", "")
        result = check_apk_identity(
            Path(sys.argv[1]).read_text(encoding="utf-8"), expected
        )
    except (OSError, SigningIdentityDenied) as error:
        print("Android signing preflight denied: " + str(error), file=sys.stderr)
        return 1
    if result:
        print("Android signing preflight passed: one trusted SHA-256 signer")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
