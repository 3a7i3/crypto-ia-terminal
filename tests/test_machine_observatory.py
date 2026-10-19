"""Security boundary and failure semantics of the standalone collector."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "machine_observatory", Path(__file__).parents[1] / "scripts/machine_observatory.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.epoch = "TEST-EPOCH-01"
        self.path = self.root / "databases/ppl_authority/epochs" / (
            hashlib.sha256(self.epoch.encode()).hexdigest() + ".jsonl")
        self.path.parent.mkdir(parents=True)

    def write_events(self):
        rows = [{"sequence": 1, "event_type": "EPOCH_CREATED",
                 "payload": {"sensitive": "NEVER_EXPORT_THIS"}},
                {"sequence": 2, "event_type": "POSITION_OPENED"},
                {"sequence": 3, "event_type": "POSITION_CLOSED"}]
        self.path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def test_capture_counts_but_never_exports_payloads_or_secret_content(self):
        self.write_events()
        (self.root / ".env.secrets").write_text("TOKEN=SUPER_SECRET_VALUE")
        with patch.object(collector.os, "open", wraps=os.open) as opened:
            report = collector.capture(source_root=self.root, epoch=self.epoch)
        self.assertFalse(any(call.args[0] in collector.SECRET_FILES for call in opened.call_args_list))
        text = json.dumps(report)
        self.assertNotIn("SUPER_SECRET_VALUE", text)
        self.assertNotIn("NEVER_EXPORT_THIS", text)
        self.assertEqual(report["ppl_boundary"]["event_counts"]["POSITION_CLOSED"], 1)
        self.assertTrue(report["ppl_boundary"]["contiguous_from_one"])
        self.assertEqual(report["secrets"][".env.secrets"]["status"], "PRESENT")
        self.assertFalse(report["secrets"][".env.secrets"]["content_read"])

    def test_default_performs_no_network_or_process_execution(self):
        with patch.object(collector.urllib.request, "build_opener") as network, \
                patch.object(collector.subprocess, "Popen") as process:
            collector.capture(source_root=self.root, epoch=self.epoch)
        network.assert_not_called()
        process.assert_not_called()

    def test_missing_is_not_empty(self):
        self.assertEqual(collector.read_epoch(self.path)["status"], "MISSING")
        self.path.touch()
        self.assertEqual(collector.read_epoch(self.path)["status"], "EMPTY_OR_INCOMPLETE")

    def test_denied_is_not_missing(self):
        with patch.object(collector.os, "open", side_effect=PermissionError()):
            self.assertEqual(collector.read_epoch(self.path)["status"], "DENIED")
            self.assertEqual(collector.file_metadata(self.path)["status"], "DENIED")

    def test_final_symlink_and_parent_symlink_are_refused(self):
        outside = self.root / "outside"
        outside.write_text("secret")
        self.path.symlink_to(outside)
        self.assertEqual(collector.read_epoch(self.path)["status"], "INVALID_PATH")
        self.assertEqual(collector.file_metadata(self.path)["status"], "INVALID_PATH")
        link = self.root / "link"
        link.symlink_to(self.path.parent, target_is_directory=True)
        self.assertEqual(collector.read_epoch(link / self.path.name)["status"], "INVALID_PATH")

    def test_fifo_does_not_block(self):
        os.mkfifo(self.path)
        self.assertEqual(collector.read_epoch(self.path)["status"], "INVALID_PATH")

    def test_oversize_and_partial_records_refused(self):
        self.path.write_bytes(b"x" * 33)
        with patch.object(collector, "MAX_BYTES", 32):
            self.assertEqual(collector.read_epoch(self.path)["status"], "LIMIT_EXCEEDED")
        self.path.write_text('{"sequence":1,"event_type":"EPOCH_CREATED"}')
        self.assertEqual(collector.read_epoch(self.path)["status"], "EMPTY_OR_INCOMPLETE")

    def test_changed_file_is_not_a_stable_capture(self):
        self.write_events()
        original = collector.os.read
        changed = False

        def mutate(fd, limit):
            nonlocal changed
            data = original(fd, limit)
            if not changed:
                changed = True
                with self.path.open("a") as stream:
                    stream.write('{"sequence":4,"event_type":"POSITION_OPENED"}\n')
            return data

        with patch.object(collector.os, "read", side_effect=mutate):
            self.assertEqual(collector.read_epoch(self.path)["status"], "SOURCE_CHANGED")

    def test_duplicate_keys_nan_and_boolean_sequence_refused(self):
        for raw in [b'{"sequence":1,"sequence":2}\n', b'{"value":NaN}\n',
                    b'{"sequence":true,"event_type":"EPOCH_CREATED"}\n']:
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                self.assertNotEqual(collector.read_epoch(self.path)["status"], "CAPTURED")

    def test_gap_preserved_and_unknown_type_not_echoed(self):
        result = collector.event_summary([{"sequence":2,"event_type":"POSITION_OPENED"}])
        self.assertFalse(result["contiguous_from_one"])
        self.path.write_text('{"sequence":1,"event_type":"TOKEN_SECRET"}\n')
        result = collector.read_epoch(self.path)
        self.assertEqual(result["status"], "UNKNOWN_EVENT_TYPE")
        self.assertNotIn("TOKEN_SECRET", json.dumps(result))

    def test_invalid_root_and_epoch_cannot_escape_allowlist(self):
        for root, epoch in [("relative", self.epoch), (self.root, "../secret"),
                            (str(self.root) + "/../other", self.epoch)]:
            with self.subTest(root=root, epoch=epoch), self.assertRaises(collector.CaptureError):
                collector.capture(source_root=root, epoch=epoch)

    def test_api_raw_text_errors_and_unknown_fields_not_exported(self):
        class Opener:
            def open(self, url, timeout):
                self.url, self.timeout = url, timeout
                return io.BytesIO(b'{"token":"NEVER_ECHO","snapshot_age_s":12,"freshness_classification":"STALE"}')
        opener = Opener()
        result = collector.api_probe("snapshot", opener=opener)
        self.assertEqual(result["snapshot_age_s"], 12)
        self.assertNotIn("NEVER_ECHO", json.dumps(result))
        self.assertEqual(opener.url, "http://127.0.0.1:8090/api/operator/v1/snapshot")
        with self.assertRaises(collector.CaptureError):
            collector.api_probe("../../secret", opener=opener)

    def test_api_no_proxy_or_redirect(self):
        with patch.object(collector.urllib.request, "build_opener", side_effect=OSError()) as build:
            self.assertEqual(collector.api_probe("snapshot")["status"], "UNAVAILABLE")
        args = build.call_args.args
        self.assertEqual(args[0].proxies, {})
        self.assertIsInstance(args[1], collector.NoRedirect)
        self.assertIsNone(args[1].redirect_request(None, None, 302, "", {}, "http://external"))

    def test_import_does_not_collect_and_cli_errors_are_closed(self):
        with patch.object(collector.subprocess, "Popen") as process, \
                patch.object(collector.urllib.request, "build_opener") as network:
            SPEC.loader.exec_module(collector)
        process.assert_not_called()
        network.assert_not_called()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = collector.main(["--source-root", "relative", "--epoch", self.epoch])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["error_code"], "INVALID_ROOT")

    def test_service_probe_fixed_command_and_untrusted_fields_filtered(self):
        text = "\n\n".join(
            "Id=" + unit + "\nLoadState=loaded\nActiveState=active\nSubState=SECRET_VALUE\n"
            for unit in collector.UNITS)
        real_popen = subprocess.Popen

        def child(command, **kwargs):
            self.assertEqual(command, collector.COMMAND)
            self.assertEqual(kwargs["env"], {"LC_ALL": "C"})
            self.assertFalse(kwargs["shell"])
            return real_popen([sys.executable, "-c", "print(" + repr(text) + ")"], **kwargs)

        with patch.object(collector.subprocess, "Popen", side_effect=child):
            report = collector.service_probe()
        self.assertEqual(report["status"], "CAPTURED")
        self.assertEqual(len(report["services"]), len(collector.UNITS))
        self.assertNotIn("SECRET_VALUE", json.dumps(report))

    def test_service_probe_refuses_excess_output(self):
        real_popen = subprocess.Popen
        with patch.object(collector.subprocess, "Popen", side_effect=lambda _cmd, **kw:
                          real_popen([sys.executable, "-c", "print('x'*40000)"], **kw)):
            self.assertEqual(collector.service_probe()["status"], "LIMIT_EXCEEDED")

    def test_http_error_body_not_read_and_large_response_refused(self):
        error = urllib.error.HTTPError("http://localhost", 503, "SECRET", {}, io.BytesIO(b"SECRET"))
        class Opener:
            def open(self, *_args, **_kwargs):
                raise error
        result = collector.api_probe("events", opener=Opener())
        self.assertEqual(result, {"status": "HTTP_ERROR", "http_status": 503})
        self.assertTrue(error.fp.closed)
        class Large:
            def open(self, *_args, **_kwargs):
                return io.BytesIO(b"x" * 33)
        with patch.object(collector, "MAX_BYTES", 32):
            self.assertEqual(collector.api_probe("events", opener=Large())["status"], "LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
