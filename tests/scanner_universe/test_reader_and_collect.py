"""Scanner V1: producer run/replay, GET-only reader and Operator API route."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from observability.scanner_universe import collect
from observability.scanner_universe.catalogues import ENDPOINTS
from observability.scanner_universe.universe import FRESHNESS_MAX_AGE_MS
from observability.operator_api.scanner_universe_reader import ScannerUniverseReader

from ._factory import T0, documents


def fake_fetcher(**overrides):
    docs = documents(**overrides)
    by_url = {url: docs[name] for name, url in ENDPOINTS.items()}

    def fetch(url):
        d = by_url[url]
        return {**d, "http_status": 200 if d["raw"] is not None else 503}
    return fetch


def clock(start=T0):
    state = {"t": start}

    def now():
        state["t"] += 1
        return state["t"]
    return now


class Producer(unittest.TestCase):
    def test_run_publishes_and_replay_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = collect.run(Path(tmp), fake_fetcher(), clock())
            self.assertEqual(pub["status"], "VERIFIED")
            run_dir = next((Path(tmp) / "runs").iterdir())
            self.assertEqual(collect.encode(collect.replay(run_dir)), (Path(tmp) / collect.PUBLICATION).read_bytes())
            manifest = json.loads((run_dir / "manifest.json").read_bytes())
            self.assertEqual(set(manifest["documents"]), set(ENDPOINTS))

    def test_failed_source_keeps_previous_list_as_dated_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = collect.run(Path(tmp), fake_fetcher(), clock())
            second = collect.run(Path(tmp), fake_fetcher(kf="HTTP_503"), clock(T0 + 5_000))
            self.assertEqual(second["status"], "UNVERIFIABLE")
            self.assertEqual(second["pairs"], [])
            self.assertEqual(second["reference"]["universe_sha256"], first["universe_sha256"])
            runs = sorted((Path(tmp) / "runs").iterdir())
            self.assertEqual(collect.encode(collect.replay(runs[-1])), (Path(tmp) / collect.PUBLICATION).read_bytes())

    def test_fetch_maps_transport_and_http_errors(self):
        def http_error(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 451, "x", {}, io.BytesIO(b""))

        def refused(request, timeout):
            raise urllib.error.URLError(ConnectionRefusedError())
        self.assertEqual(collect.fetch("https://x", http_error)["error"], "HTTP_451")
        self.assertEqual(collect.fetch("https://x", refused)["error"], "TRANSPORT_CONNECTIONREFUSEDERROR")


class Reader(unittest.TestCase):
    def publish(self, tmp, **kw):
        collect.run(Path(tmp), fake_fetcher(**kw), clock())
        return Path(tmp) / collect.PUBLICATION

    def test_states(self):
        self.assertEqual(ScannerUniverseReader("").read().error_code, "SCANNER_UNIVERSE_NOT_CONFIGURED")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ScannerUniverseReader(str(Path(tmp) / "absent.json")).read().error_code,
                             "SCANNER_UNIVERSE_MISSING")
            path = self.publish(tmp)
            fresh = ScannerUniverseReader(str(path), now_fn=lambda: T0 + 60_000).read()
            self.assertTrue(fresh.ok)
            self.assertEqual(fresh.snapshot["status"], "VERIFIED")
            stale = ScannerUniverseReader(str(path), now_fn=lambda: T0 + FRESHNESS_MAX_AGE_MS + 10).read()
            self.assertEqual((stale.snapshot["status"], stale.snapshot["pairs"]), ("UNVERIFIABLE", []))
            self.assertEqual(stale.snapshot["reference"]["keys"], ["BTC/USDT"])
            doc = json.loads(path.read_bytes())
            del doc["pairs"][0]["proofs"]["KRAKEN_SPOT"]
            path.write_text(json.dumps(doc))
            self.assertEqual(ScannerUniverseReader(str(path)).read().error_code, "SCANNER_UNIVERSE_INVALID_SCHEMA")
            path.write_text("{")
            self.assertEqual(ScannerUniverseReader(str(path)).read().error_code, "SCANNER_UNIVERSE_MALFORMED_JSON")

    def test_api_route(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover
            self.skipTest("fastapi not installed")
        from observability.operator_api import app as api
        self.addCleanup(api.configure_scanner_universe_reader, "")
        client = TestClient(api.app)
        api.configure_scanner_universe_reader("")
        response = client.get("/api/operator/v1/scanner-universe")
        self.assertEqual((response.status_code, response.json()), (503, {"error_code": "SCANNER_UNIVERSE_NOT_CONFIGURED"}))
        with tempfile.TemporaryDirectory() as tmp:
            api.configure_scanner_universe_reader(str(self.publish(tmp)), now_fn=lambda: T0 + 60_000)
            response = client.get("/api/operator/v1/scanner-universe")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json()["pairs"][0]["key"], "BTC/USDT")
        self.assertEqual(client.post("/api/operator/v1/scanner-universe").status_code, 405)


if __name__ == "__main__":
    unittest.main()
