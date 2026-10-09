#!/usr/bin/env python3
"""Inspect staged Git blobs before publication; never print secret values.

This small preflight detects common secret patterns, credential JSON fields,
generated directories and oversized files. It is not a complete secret scanner.
"""

import json
from io import BytesIO
import re
import subprocess


FORBIDDEN = (".venv/", ".freqtrade-venv/", "datasets/", "processed/", "runtime/", "runs/", "outputs/",
             ".codex_work/", ".codex_build/", "binance-public-data/", "live/market_data/", "local_llm/",
             "local_portfolios/", "freqtrade/user_data/data/", "freqtrade/user_data/models/",
             "freqtrade/user_data/backtest_results/", "freqtrade/validation_runs/")
PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
)
SECRET_KEYS = {"api_key", "api_secret", "access_token", "client_secret", "private_key", "jwt_secret_key", "password", "token", "secret"}


def credential_fields(value, parents=()):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            sensitive = key.lower() in SECRET_KEYS or (key.lower() == "key" and "exchange" in parents)
            if sensitive and isinstance(child, str) and child.strip() and not child.startswith(("${", "ENV:", "your-")):
                found.append(".".join((*parents, key)))
            found.extend(credential_fields(child, (*parents, key)))
    elif isinstance(value, list):
        for child in value:
            found.extend(credential_fields(child, parents))
    return found


def main():
    listing = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
    issues, count, total = [], 0, 0
    candidates = []
    for item in listing.split(b"\0"):
        if not item:
            continue
        header, raw_path = item.split(b"\t", 1)
        mode, object_id, stage = header.decode().split()
        path = raw_path.decode("utf-8")
        count += 1
        if mode == "160000" or stage != "0":
            issues.append((path, "embedded Git checkout or unresolved conflict"))
            continue
        if path.startswith(FORBIDDEN) or path.split("/")[-1].startswith(".env"):
            issues.append((path, "private/generated input must not be staged"))
        candidates.append((path, object_id))
    requests = ("\n".join(object_id for _, object_id in candidates) + "\n").encode()
    sizes = subprocess.run(["git", "cat-file", "--batch-check"], input=requests, capture_output=True, check=True).stdout.splitlines()
    selected = []
    for (path, object_id), size_line in zip(candidates, sizes):
        size = int(size_line.split()[-1])
        total += size
        if size > 50 * 1024 * 1024:
            issues.append((path, "file exceeds 50 MiB publication limit"))
            continue
        selected.append((path, object_id))
    requests = ("\n".join(object_id for _, object_id in selected) + "\n").encode()
    stream = BytesIO(subprocess.run(["git", "cat-file", "--batch"], input=requests, capture_output=True, check=True).stdout)
    for path, object_id in selected:
        header = stream.readline().split()
        size = int(header[-1])
        blob = stream.read(size)
        stream.read(1)
        if any(pattern.search(blob) for pattern in PATTERNS):
            issues.append((path, "potential credential pattern; inspect locally"))
        if path.endswith(".json"):
            try:
                for field in credential_fields(json.loads(blob)):
                    issues.append((path, f"nonempty credential field: {field}"))
            except (ValueError, UnicodeDecodeError):
                issues.append((path, "invalid JSON"))
    for path, reason in issues:
        print(f"BLOCKED: {path}: {reason}")
    print(f"Publication preflight {'FAIL' if issues else 'PASS'}: {count} staged files, {total / 1024 / 1024:.2f} MiB")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
