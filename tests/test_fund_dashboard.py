"""Exercise the read-only report boundary without invoking a trading engine."""

from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fund_agents.dashboard import DashboardHandler, reports_in


def envelope(cycle="test", generated="2026-10-14T10:00:00+00:00"):
    return {"schema_version": "two-pm-fund-v1", "cycle_id": cycle,
            "as_of": "2026-08-28", "generated_at_utc": generated,
            "mode": "research", "status": "INPUT_HOLD", "config": {},
            "fund_risk": {"status": "INPUT_HOLD", "metrics": {}, "approved_groups": []},
            "pm_proposals": {}, "portfolio_before": {}}


class QuietHandler(DashboardHandler):
    def log_message(self, *args):
        pass


class FundDashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def write(self, filename, value):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_index_excludes_audits_and_preserves_held_metrics(self):
        self.write("research/held.json", envelope())
        self.write("held.crypto_quality.json", envelope("not-a-cycle"))
        self.write("unrelated.json", {"private": "not a report"})
        reports, warnings = reports_in(self.root)
        self.assertEqual([r[0] for r in reports], ["research/held.json"])
        self.assertEqual(reports[0][1]["fund_risk"]["metrics"], {})
        self.assertEqual(warnings, [])

    def test_newest_saved_cycle_first_and_invalid_reports_are_skipped(self):
        self.write("older.json", envelope("older"))
        self.write("newer.json", envelope("newer", "2026-10-15T10:00:00+00:00"))
        self.write("incomplete.json", {"schema_version": "two-pm-fund-v1"})
        (self.root / "partial.json").write_text('{"schema_version":', encoding="utf-8")
        self.write("nonfinite.json", dict(envelope(), config={"limit": float("nan")}))
        (self.root / "overflow.json").write_text(json.dumps(envelope()).replace('"config": {}', '"config": {"limit": 1e999}'), encoding="utf-8")
        self.write("invalid-date-type.json", envelope(generated=100))
        reports, warnings = reports_in(self.root)
        self.assertEqual([r[1]["cycle_id"] for r in reports], ["newer", "older"])
        self.assertEqual(len(warnings), 5)

    def test_empty_or_absent_directory(self):
        self.assertEqual(reports_in(self.root / "missing"), ([], []))

    def test_http_serves_only_indexed_reports_and_known_assets(self):
        expected = envelope()
        self.write("research/test.json", expected)
        before = (self.root / "research/test.json").read_bytes()
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, report_directory=self.root))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/reports") as response:
                self.assertEqual(json.load(response)["reports"][0]["id"], "research/test.json")
            with urlopen(base + "/api/report?id=research%2Ftest.json") as response:
                self.assertEqual(json.load(response), expected)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            for path in ("/", "/app.js", "/styles.css"):
                with urlopen(base + path) as response:
                    self.assertEqual(response.status, 200)
            for path in ("/api/report?id=..%2Fsecret.json", "/api/report", "/../README.md", "/runtime/fund.sqlite"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/report", data=b"{}", method="POST"))
            self.assertEqual(error.exception.code, 501)
            self.assertEqual((self.root / "research/test.json").read_bytes(), before)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
