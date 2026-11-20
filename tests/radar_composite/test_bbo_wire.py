"""Offline tests of the BBO wire codecs: RFC 6455 client codec and MEXC protobuf."""
import hashlib
import re
import socket
import unittest
from pathlib import Path
from unittest import mock

from observability.radar_composite import bbo_wire as wire

PROTO_DIR = Path(wire.__file__).resolve().parent / "mexc_proto"
PROTO_SHA256 = {
    "PushDataV3ApiWrapper.proto": "1869bbb700319ea4a0844ec11860dade0868c6a3a444dd3db6455db3c578c4fd",
    "PublicAggreDepthsV3Api.proto": "77e5d4a690dab83901691c906abf910e904ebbbbcb3d3e345333785992f66994",
    "PublicAggreBookTickerV3Api.proto": "2fb244c34e3fd9d4760795166bd1e43f0c9939bb3982f96d71c66da5388d0108",
    "LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
}
PROTO_REVISION = "0c9c4f35dd0fadc3a46a350e909a93379d81e811"


class NoNetwork(unittest.TestCase):
    """Any socket creation during a test is a failure."""

    def setUp(self):
        def forbidden(*a, **k):
            raise AssertionError("network access attempted in an offline test")
        for target in ("socket.socket", "socket.create_connection"):
            p = mock.patch(target, side_effect=forbidden)
            p.start()
            self.addCleanup(p.stop)


def proto_fields(name, message):
    text = (PROTO_DIR / name).read_text()
    body = re.search(r"message\s+" + message + r"\s*\{(.*?)\n\}", text, re.DOTALL).group(1)
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"(\w+)\s*=\s*(\d+)\s*;", body)}


class Provenance(NoNetwork):
    def test_proto_files_match_recorded_hashes(self):
        for name, digest in PROTO_SHA256.items():
            self.assertEqual(hashlib.sha256((PROTO_DIR / name).read_bytes()).hexdigest(), digest, name)
        self.assertIn(PROTO_REVISION, (PROTO_DIR / "PROVENANCE.md").read_text())

    def test_decoder_field_numbers_come_from_the_official_proto(self):
        wrapper = proto_fields("PushDataV3ApiWrapper.proto", "PushDataV3ApiWrapper")
        for name, number in wire.WRAPPER_FIELDS.items():
            self.assertEqual(wrapper[name], number, name)
        depths = proto_fields("PublicAggreDepthsV3Api.proto", "PublicAggreDepthsV3Api")
        self.assertEqual(depths, wire.DEPTHS_FIELDS)
        item = proto_fields("PublicAggreDepthsV3Api.proto", "PublicAggreDepthV3ApiItem")
        self.assertEqual(item, wire.ITEM_FIELDS)
        text = (PROTO_DIR / "PushDataV3ApiWrapper.proto").read_text()
        self.assertRegex(text, r"optional int64 createTime = 5;")
        self.assertRegex(text, r"optional int64 sendTime = 6;")
        self.assertRegex((PROTO_DIR / "PublicAggreDepthsV3Api.proto").read_text(),
                         r"string fromVersion = 4;\s*string toVersion = 5;")


class Handshake(NoNetwork):
    def test_rfc6455_sample_accept(self):
        # RFC 6455 §1.3 sample nonce
        self.assertEqual(wire.accept_for("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def _resp(self, key, extra=""):
        return ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {wire.accept_for(key)}\r\n{extra}\r\n").encode()

    def test_request_and_valid_response(self):
        key = wire.new_key(rand=lambda n: b"\x00" * n)
        req = wire.handshake_request("ws.kraken.com", "/v2", key).decode()
        self.assertTrue(req.startswith("GET /v2 HTTP/1.1\r\n"))
        self.assertIn("Sec-WebSocket-Version: 13", req)
        headers, rest = wire.parse_handshake_response(self._resp(key) + b"\x81\x00", key)
        self.assertEqual(rest, b"\x81\x00")
        self.assertEqual(headers["upgrade"], "websocket")

    def test_invalid_responses(self):
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        cases = {
            b"HTTP/1.1 403 Forbidden\r\n\r\n": "HANDSHAKE_STATUS",
            self._resp("AAAAAAAAAAAAAAAAAAAAAA=="): "HANDSHAKE_ACCEPT",
            self._resp(key, "Sec-WebSocket-Extensions: permessage-deflate\r\n"): "HANDSHAKE_UNREQUESTED_EXTENSION",
            self._resp(key)[:-2]: "HANDSHAKE_INCOMPLETE",
        }
        for raw, code in cases.items():
            with self.assertRaises(wire.WireError) as ctx:
                wire.parse_handshake_response(raw, key)
            self.assertEqual(ctx.exception.code, code)


class Frames(NoNetwork):
    def test_client_frames_are_masked(self):
        frame = wire.encode_client_frame(wire.OP_TEXT, b"Hello", mask_key=b"\x37\xfa\x21\x3d")
        # RFC 6455 §5.7 masked "Hello" example
        self.assertEqual(frame, bytes.fromhex("818537fa213d7f9f4d5158"))
        with self.assertRaises(wire.WireError):
            wire.encode_client_frame(wire.OP_PING, b"x" * 126)

    def test_fragmented_message_with_interleaved_ping(self):
        p = wire.FrameParser()
        data = (wire.encode_server_frame(wire.OP_TEXT, b"Hel", fin=False)
                + wire.encode_server_frame(wire.OP_PING, b"p")
                + wire.encode_server_frame(wire.OP_CONT, b"lo"))
        out = []
        for i in range(len(data)):  # byte by byte: incremental parsing
            out += p.feed(data[i:i + 1])
        self.assertEqual(out, [(wire.OP_PING, b"p"), (wire.OP_TEXT, b"Hello")])

    def test_extended_lengths(self):
        p = wire.FrameParser()
        for size in (125, 126, 65535, 65536):
            payload = bytes(size)
            self.assertEqual(p.feed(wire.encode_server_frame(wire.OP_BINARY, payload)),
                             [(wire.OP_BINARY, payload)])

    def test_protocol_violations(self):
        cases = {
            wire.encode_server_frame(wire.OP_TEXT, b"x", masked=True): "MASKED_SERVER_FRAME",
            wire.encode_server_frame(wire.OP_TEXT, b"x", rsv=1): "RSV_BITS_SET",
            wire.encode_server_frame(wire.OP_CONT, b"x"): "UNEXPECTED_CONTINUATION",
            wire.encode_server_frame(wire.OP_TEXT, b"\xff\xfe"): "TEXT_NOT_UTF8",
            bytes([0x83, 0x00]): "UNKNOWN_OPCODE",
            bytes([0x09, 0x00]): "CONTROL_FRAME_INVALID",
            bytes([0x82, 126, 0x00, 0x05]) + b"abcde": "NON_MINIMAL_LENGTH",
            (wire.encode_server_frame(wire.OP_TEXT, b"a", fin=False)
             + wire.encode_server_frame(wire.OP_TEXT, b"b")): "INTERLEAVED_DATA_FRAME",
        }
        for raw, code in cases.items():
            with self.assertRaises(wire.WireError) as ctx:
                wire.FrameParser().feed(raw)
            self.assertEqual(ctx.exception.code, code, raw[:4])

    def test_size_caps(self):
        p = wire.FrameParser(max_message_bytes=10)
        with self.assertRaises(wire.WireError) as ctx:
            p.feed(wire.encode_server_frame(wire.OP_BINARY, bytes(11)))
        self.assertEqual(ctx.exception.code, "FRAME_TOO_LARGE")
        p = wire.FrameParser(max_message_bytes=10)
        p.feed(wire.encode_server_frame(wire.OP_BINARY, bytes(6), fin=False))
        with self.assertRaises(wire.WireError) as ctx:
            p.feed(wire.encode_server_frame(wire.OP_CONT, bytes(6)))
        self.assertEqual(ctx.exception.code, "MESSAGE_TOO_LARGE")

    def test_close_then_nothing(self):
        p = wire.FrameParser()
        out = p.feed(wire.encode_server_frame(wire.OP_CLOSE, wire.close_payload(1000, "bye")))
        self.assertEqual(out, [(wire.OP_CLOSE, b"\x03\xe8bye")])
        with self.assertRaises(wire.WireError):
            p.feed(b"\x81\x00")


class Protobuf(NoNetwork):
    def test_roundtrip_depth_push(self):
        body = wire.encode_aggre_depths([("62000.01", "0.5")], [("61999.99", "0"), ("61999.98", "1.25")],
                                        1001, 1003, event_type="spot@public.aggre.depth.v3.api.pb",
                                        last_order_create_time=1_795_128_000_123)
        push = wire.encode_mexc_push("spot@public.aggre.depth.v3.api.pb@100ms@BTCUSDT", "BTCUSDT", body,
                                     send_time=1_795_128_000_200, create_time=-5)
        got = wire.decode_mexc_push(push)
        self.assertEqual(got["channel"], "spot@public.aggre.depth.v3.api.pb@100ms@BTCUSDT")
        self.assertEqual((got["symbol"], got["sendTime"], got["createTime"]), ("BTCUSDT", 1_795_128_000_200, -5))
        d = got["body"]
        self.assertEqual(d["asks"], [("62000.01", "0.5")])
        self.assertEqual(d["bids"], [("61999.99", "0"), ("61999.98", "1.25")])
        self.assertEqual((d["fromVersion"], d["toVersion"]), ("1001", "1003"))
        self.assertEqual(d["lastOrderCreateTime"], 1_795_128_000_123)

    def test_other_oneof_member_and_unknown_fields(self):
        push = wire.encode_mexc_push("spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT", None,
                                     b"", body_field=315) + wire._key(99, wire.VARINT) + wire._varint(1)
        got = wire.decode_mexc_push(push)
        self.assertEqual((got["body_field"], got["body"], got["unknown_fields"]), (315, None, [99]))

    def test_malformed(self):
        good = wire.encode_mexc_push("c", "S", wire.encode_aggre_depths([], [], 1, 1))
        cases = {
            good[:-1]: "PB_TRUNCATED_LEN",
            wire._len_field(1, b"c") + wire._len_field(1, b"d"): "PB_DUPLICATE_FIELD",
            wire._key(1, wire.VARINT) + wire._varint(5): "PB_WIRE_TYPE_MISMATCH",
            wire._len_field(1, b"\xff"): "PB_STRING_NOT_UTF8",
            wire._len_field(3, b"S"): "PB_MISSING_CHANNEL",
            bytes([0x0B]): "PB_UNSUPPORTED_WIRE_TYPE",
            bytes([0x08]) + b"\xff" * 11: "PB_VARINT_TOO_LONG",
            wire._len_field(1, b"c") + wire._len_field(313, b"") + wire._len_field(315, b""): "PB_ONEOF_TWICE",
        }
        for raw, code in cases.items():
            with self.assertRaises(wire.WireError) as ctx:
                wire.decode_mexc_push(raw)
            self.assertEqual(ctx.exception.code, code)

    def test_socket_is_really_forbidden(self):
        with self.assertRaises(AssertionError):
            socket.create_connection(("example.invalid", 443))


if __name__ == "__main__":
    unittest.main()


class BoundedSend(NoNetwork):
    class Sock:
        def __init__(self, chunk, clock, step=0.0, raise_timeout=False):
            self.chunk, self.clock, self.step = chunk, clock, step
            self.raise_timeout = raise_timeout
            self.got = b""
            self.timeouts = []

        def settimeout(self, t):
            self.timeouts.append(t)

        def setblocking(self, flag):
            pass

        def send(self, data):
            self.clock[0] += self.step
            if self.raise_timeout:
                raise TimeoutError
            n = min(self.chunk, len(data))
            self.got += bytes(data[:n])
            return n

    def test_success_and_deadline_shrinks(self):
        clock = [0.0]
        sock = self.Sock(4, clock, step=0.1)
        self.assertEqual(wire.send_all_bounded(sock, b"0123456789", 1.0, monotonic=lambda: clock[0]), 10)
        self.assertEqual(sock.got, b"0123456789")
        self.assertEqual(sock.timeouts, sorted(sock.timeouts, reverse=True))  # remaining time only

    def test_slow_peer_hits_the_whole_message_deadline(self):
        clock = [0.0]
        sock = self.Sock(1, clock, step=0.3)
        with self.assertRaises(wire.WireError) as ctx:
            wire.send_all_bounded(sock, b"0123456789", 1.0, monotonic=lambda: clock[0])
        self.assertEqual(ctx.exception.code, "SEND_TIMEOUT")
        self.assertLess(len(sock.got), 10)

    def test_socket_timeout_and_closed_peer(self):
        clock = [0.0]
        with self.assertRaises(wire.WireError) as ctx:
            wire.send_all_bounded(self.Sock(4, clock, raise_timeout=True), b"x", 1.0, monotonic=lambda: clock[0])
        self.assertEqual(ctx.exception.code, "SEND_TIMEOUT")
        with self.assertRaises(wire.WireError) as ctx:
            wire.send_all_bounded(self.Sock(0, clock), b"x", 1.0, monotonic=lambda: clock[0])
        self.assertEqual(ctx.exception.code, "SEND_CONNECTION_CLOSED")
        with self.assertRaises(wire.WireError) as ctx:
            wire.send_all_bounded(self.Sock(4, clock), b"x", 0, monotonic=lambda: clock[0])
        self.assertEqual(ctx.exception.code, "SEND_TIMEOUT")
