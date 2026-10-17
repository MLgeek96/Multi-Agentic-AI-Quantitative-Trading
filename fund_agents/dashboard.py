"""Read-only, localhost dashboard for saved fund coordinator reports.

Run with ``python -m fund_agents.dashboard``. No trading engine is invoked.
"""

import argparse
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).with_name("web")


def reject_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        reject_constant(value)
    return number


def reports_in(directory):
    """Index only complete report envelopes, never quality audits or other JSON."""
    reports = []
    warnings = []
    for path in directory.rglob("*.json"):
        if path.name.endswith(".crypto_quality.json"):
            continue
        try:
            if not path.resolve().is_relative_to(directory.resolve()):
                continue
            report = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant, parse_float=finite_float)
            if not isinstance(report, dict) or report.get("schema_version") != "two-pm-fund-v1":
                continue
            for key in ("config", "fund_risk", "pm_proposals", "portfolio_before"):
                if not isinstance(report.get(key), dict):
                    raise ValueError("incomplete report: " + key)
            if not all(isinstance(report.get(k), str) and report[k]
                       for k in ("cycle_id", "as_of", "generated_at_utc", "mode", "status")):
                raise ValueError("missing report identity")
            reports.append((path.relative_to(directory).as_posix(), report))
        except (ValueError, OSError) as exc:
            warnings.append(f"Skipped {path.name}: {exc}")
    reports.sort(key=lambda item: (item[1]["generated_at_utc"], item[0]), reverse=True)
    return reports, warnings


class DashboardHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, report_directory, **kwargs):
        self.report_directory = report_directory
        super().__init__(*args, **kwargs)

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, status, data):
        self.respond(status, json.dumps(data, allow_nan=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ("/api/reports", "/api/report"):
            reports, warnings = reports_in(self.report_directory)
            if url.path == "/api/reports":
                keys = ("cycle_id", "as_of", "mode", "status", "generated_at_utc")
                self.json_response(200, {"reports": [dict(id=key, **{k: report[k] for k in keys})
                                                    for key, report in reports], "warnings": warnings})
            else:
                selected = parse_qs(url.query).get("id", [None])[0]
                report = next((r for key, r in reports if key == selected), None)
                self.json_response(200 if report else 404, report or {"error": "Report not found"})
            return
        assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                  "/styles.css": ("styles.css", "text/css")}
        if url.path not in assets:
            self.json_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        filename, mime = assets[url.path]
        self.respond(200, (STATIC / filename).read_bytes(), mime + "; charset=utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reports", type=Path, default=ROOT / "runs/fund_agents")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(DashboardHandler, report_directory=args.reports.resolve()))
    print(f"Fund dashboard: http://127.0.0.1:{server.server_port} (read-only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
