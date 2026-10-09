"""Read-only local Spot adapter; audit the exact bytes before building snapshots."""

import hashlib
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_quant.data_quality import audit_ohlcv, utc, write_audit

from .models import Bar, Dataset, MarketSnapshot, fingerprint


def load_local_snapshot(directory: Path, symbols: tuple[str, ...], as_of: str, *, minimum_rows=520):
    decision = utc(as_of).normalize()
    datasets, reports = [], []
    for symbol in symbols:
        path = directory / f"{symbol}_1d.csv"
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        full = pd.read_csv(BytesIO(raw))
        # Historical replay explicitly ignores later bars, never earlier bad bars.
        # Keep NaT rows in scope so malformed timestamps cannot escape the audit.
        if "open_time" in full:
            dates = pd.to_datetime(full["open_time"], utc=True, errors="coerce", format="mixed")
            selected = full.loc[dates.isna() | dates.le(decision)].copy()
        else:
            selected = full
        report = audit_ohlcv(selected, symbol=symbol, closed_at=decision + pd.Timedelta(days=1),
                             expected_last=decision, minimum_rows=minimum_rows)
        report.update(file=path.name, file_sha256=digest, rows_excluded_after_as_of=len(full) - len(selected))
        reports.append(report)
        failed = tuple(c["name"] for c in report["checks"] if not c["passed"] and c["severity"] == "ERROR")
        bars = ()
        if report["status"] == "PASS":
            bars = tuple(Bar(utc(row.open_time).date().isoformat(), float(row.close), float(row.quote_volume))
                         for row in selected.itertuples())
        datasets.append(Dataset(symbol, bars, report["status"], failed, digest))
    audit = {"schema_version": "agent-bundle-v1", "as_of": decision.date().isoformat(),
             "status": "PASS" if all(d.quality_status == "PASS" for d in datasets) else "FAIL",
             "basis": "LOCAL_SPOT_RESEARCH", "source": str(directory.resolve()), "datasets": reports,
             "limitations": ["Local schema/continuity audit does not establish exchange authenticity or listing eligibility",
                             "Daily files are not an independent raw-archive checksum chain"]}
    snapshot = MarketSnapshot(decision.date().isoformat(), tuple(datasets), "LOCAL_SPOT_RESEARCH", str(directory.resolve()), fingerprint(audit))
    return snapshot, audit


def demo_snapshot(symbols: tuple[str, ...], *, scenario="normal"):
    dates = pd.date_range("2023-01-01", periods=800, freq="1D", tz="UTC")
    datasets = []
    for i, symbol in enumerate(symbols):
        values = (100.0 + i * 50) * np.exp(np.arange(len(dates)) * 0.0007 + np.sin(np.arange(len(dates)) / 7) * .015)
        bars = tuple(Bar(day.date().isoformat(), float(value), 50_000_000.0) for day, value in zip(dates, values))
        datasets.append(Dataset(symbol, bars, "FAIL" if scenario == "flagged" else "PASS",
                                ("demo_quality_failure",) if scenario == "flagged" else (), fingerprint((symbol, bars))))
    audit = {"basis": "SYNTHETIC_DEMO", "scenario": scenario, "status": "FAIL" if scenario == "flagged" else "PASS"}
    return MarketSnapshot(dates[-1].date().isoformat(), tuple(datasets), "SYNTHETIC_DEMO", "invented deterministic fixture", fingerprint(audit)), audit


def save_audit(audit, destination):
    write_audit(audit, destination)
