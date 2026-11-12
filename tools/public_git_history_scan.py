#!/usr/bin/env python3
"""Non-disclosing, offline preflight of all reachable Git history blobs.

Findings report only categories, paths, and blob prefixes; never secret values.
This heuristic is not a substitute for GitHub's own secret scanning.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

MAX_BYTES = 2_000_000
BATCH_SIZE = 150
SIGNATURES = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github-token": re.compile(rb"(?:github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9_]{25,})"),
    "openai-key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b"),
    "google-api-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "aws-key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "slack-token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "database-url": re.compile(rb"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:/@]{1,80}:[^\s/@]{6,}@[^\s/]+", re.I),
}
ASSIGNMENT = re.compile(
    rb"(?im)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY|PASS_PHRASE|PASSPHRASE)[A-Z0-9_]*)\s*[:=]\s*([\"'])([^\r\n\"']{16,})\2"
)
PLACEHOLDERS = (b"REPLACE", b"YOUR", b"EXAMPLE", b"SAMPLE", b"DUMMY", b"FAKE", b"TEST", b"PLACEHOLDER", b"GENERATE", b"CHANGEME", b"CHANGE_ME", b"SYNTHETIC", b"CORRECT HORSE BATTERY STAPLE", b"REPLACEMENT PASSPHRASE 12345")
SENSITIVE_EXTENSIONS = {".pem", ".p12", ".pfx", ".jks", ".keystore", ".key", ".sqlite", ".sqlite3", ".db", ".gpg", ".asc"}

def git(args, input_bytes=None):
    return subprocess.run(["git", *args], input=input_bytes, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout

def scan():
    try:
        lines = git(["rev-list", "--objects", "--all"]).splitlines()
        path_by_sha = {}
        for line in lines:
            sha, _, path = line.partition(b" ")
            path_by_sha.setdefault(sha, path.decode("utf-8", "replace"))
        metadata = git(["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                       b"\n".join(path_by_sha) + b"\n")
    except (OSError, subprocess.CalledProcessError):
        print("ERROR: Unable to enumerate the complete fetched Git object history")
        return 2

    blobs = []
    oversized = []
    for line in metadata.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[1] != b"blob":
            continue
        if int(parts[2]) > MAX_BYTES:
            oversized.append(path_by_sha.get(parts[0], "(unnamed blob)"))
        else:
            blobs.append(parts[0])

    findings = set()
    for start in range(0, len(blobs), BATCH_SIZE):
        batch = blobs[start:start+BATCH_SIZE]
        try:
            content = git(["cat-file", "--batch"], b"\n".join(batch) + b"\n")
        except subprocess.CalledProcessError:
            print("ERROR: Unable to read Git blob content")
            return 2
        offset = 0
        for expected in batch:
            newline = content.find(b"\n", offset)
            if newline < 0:
                print("ERROR: Truncated Git batch response")
                return 2
            sha, typ, size_raw = content[offset:newline].split()
            size = int(size_raw)
            begin = newline + 1
            data = content[begin:begin+size]
            offset = begin + size + 1
            if sha != expected or typ != b"blob" or len(data) != size:
                print("ERROR: Git batch response mismatch")
                return 2
            path = path_by_sha.get(sha, "(unnamed blob)")
            filename = pathlib.PurePosixPath(path).name
            suffix = pathlib.PurePosixPath(path).suffix.lower()
            if filename in {"id_rsa", "id_ed25519", ".env"} or (
                suffix in SENSITIVE_EXTENSIONS
            ) or (filename.startswith(".env.") and filename != ".env.example"):
                findings.add(("sensitive-filename", path, sha[:12].decode()))
            if b"\0" in data[:1024]:
                continue
            for kind, pattern in SIGNATURES.items():
                for occurrence in pattern.finditer(data):
                    # Synthetic keys in fixtures are expected and never real credentials.
                    context = data[max(0, occurrence.start()-120):occurrence.start()].lower()
                    if kind == "openai-key" and (
                        "/tests/" in path or pathlib.PurePosixPath(path).name.startswith("test_")
                    ) and b"synthetic_key" in context:
                        continue
                    findings.add((kind, path, sha[:12].decode()))
            for match in ASSIGNMENT.finditer(data):
                value = match.group(3).upper().strip(b"\"';,)")
                if any(marker in value for marker in PLACEHOLDERS):
                    continue
                if value.startswith((b"$", b"<", b"{")):
                    continue
                findings.add(("credential-like-assignment", path, sha[:12].decode()))

    print(f"Scanned {len(blobs)} unique reachable Git history blobs")
    print(f"Oversized blobs requiring manual review: {len(oversized)}")
    for path in oversized[:10]:
        print(f"OVERSIZED: {path}")
    if findings:
        print(f"Potential exposures needing review: {len(findings)} (values never printed)")
        for category in sorted({kind for kind, _, _ in findings}):
            print(f"CATEGORY {category}: {sum(1 for kind, _, _ in findings if kind == category)}")
        for kind, path, prefix in sorted(findings)[:100]:
            print(f"{kind}: {path} (blob {prefix})")
        if len(findings) > 100:
            print(f"Other findings omitted: {len(findings) - 100}")
    if findings or oversized:
        return 1
    print("PASS: No recognized secrets or sensitive filenames detected in fetched history")
    print("This heuristic does not guarantee that all possible secrets are absent")
    return 0

if __name__ == "__main__":
    sys.exit(scan())
