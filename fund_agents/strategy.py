"""Pinned upstream provenance and the locally enforced strategy policy."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path


def strategy_evidence(config):
    directory = Path(__file__).parent / "vendor/pairs_trading"
    source = json.loads((directory / "SOURCE.json").read_text(encoding="utf-8"))
    for filename, details in source["files"].items():
        actual = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        if actual != details["local_sha256"]:
            raise ValueError("Pairs engine differs from its recorded source: " + filename)
    fields = ("entry_z", "exit_z", "stop_z", "kalman_q", "kalman_r", "formation_end",
              "formation_adf_pvalue", "formation_min_correlation", "formation_min_half_life",
              "formation_max_half_life", "holding_half_life_multiplier", "max_holding_sessions",
              "require_formation_qualification", "pairs_gross_fraction")
    return {"repository": source["repository"], "commit": source["commit"],
            "verified_on": source.get("verified_on"), "engine_files_verified": True,
            "policy": {name: getattr(config, name) for name in fields},
            "mandate": [asdict(pair) for pair in config.pairs],
            "adaptations": ["Frozen formation qualification; no unqualified fallback pair",
                            "Residual forecast Z-score uses the spread once",
                            "Signed linked legs with common independent risk scaling",
                            "Holding limit: min(hard session cap, ceil(configured multiplier × entry OU half-life)); frozen at entry session",
                            "Record-only intentions; upstream backtest returns are not fund returns"]}
