"""Pure wire codecs for the BBO pilot (stdlib only, no network, Python >= 3.10).

1. A minimal RFC 6455 client codec: opening handshake request and validation,
   masked client frames, server frame parser (fragmentation, control frames,
   size caps). No extension is negotiated, so RSV bits must be zero.
2. A minimal protobuf decoder for the MEXC Spot push wrapper and its aggregated
   depth body. Field numbers come from the official .proto files copied in
   ``mexc_proto/`` (revision recorded in ``mexc_proto/PROVENANCE.md``).
3. Synthetic encoders for both, used by tests and the dry-run only.

Nothing here opens a socket; the caller owns the transport.
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct

# ---------------------------------------------------------------- RFC 6455

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
DATA_OPCODES = (OP_TEXT, OP_BINARY)
CONTROL_OPCODES = (OP_CLOSE, OP_PING, OP_PONG)
MAX_MESSAGE_BYTES = 512 * 1024


class WireError(ValueError):
    """Protocol violation; the reason is a stable upper-case code."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code


def new_key(rand=os.urandom):
    return base64.b64encode(rand(16)).decode("ascii")


def accept_for(key):
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")


def handshake_request(host, path, key, *, user_agent="cat-public-pilot/1"):
    lines = [
        f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket",
        "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13",
        f"User-Agent: {user_agent}",
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def parse_handshake_response(raw, key):
    """Validate a 101 response; returns (headers, leftover bytes after the head)."""
    head, sep, rest = raw.partition(b"\r\n\r\n")
    if not sep:
        raise WireError("HANDSHAKE_INCOMPLETE")
    try:
        text = head.decode("iso-8859-1")
    except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 decodes all bytes
        raise WireError("HANDSHAKE_ENCODING") from exc
    status_line, *header_lines = text.split("\r\n")
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or parts[0] != "HTTP/1.1" or parts[1] != "101":
        raise WireError("HANDSHAKE_STATUS", status_line[:80])
    headers = {}
    for line in header_lines:
        name, colon, value = line.partition(":")
        if not colon:
            raise WireError("HANDSHAKE_HEADER")
        headers.setdefault(name.strip().lower(), value.strip())
    if headers.get("upgrade", "").lower() != "websocket":
        raise WireError("HANDSHAKE_UPGRADE")
    if "upgrade" not in [t.strip().lower() for t in headers.get("connection", "").split(",")]:
        raise WireError("HANDSHAKE_CONNECTION")
    if headers.get("sec-websocket-accept") != accept_for(key):
        raise WireError("HANDSHAKE_ACCEPT")
    if headers.get("sec-websocket-extensions"):
        raise WireError("HANDSHAKE_UNREQUESTED_EXTENSION")
    return headers, rest


def _mask(payload, key):
    return bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def encode_client_frame(opcode, payload=b"", *, fin=True, mask_key=None, rand=os.urandom):
    """Client to server frames are always masked (RFC 6455 §5.3)."""
    if opcode in CONTROL_OPCODES and (len(payload) > 125 or not fin):
        raise WireError("CONTROL_FRAME_INVALID")
    key = mask_key if mask_key is not None else rand(4)
    if len(key) != 4:
        raise WireError("MASK_KEY_LENGTH")
    return _header(opcode, len(payload), fin, True) + key + _mask(payload, key)


def encode_server_frame(opcode, payload=b"", *, fin=True, rsv=0, masked=False):
    """Synthetic server frame (tests and dry-run). ``masked`` builds an invalid one."""
    head = bytearray(_header(opcode, len(payload), fin, masked))
    head[0] |= (rsv & 0x7) << 4
    if masked:
        key = b"\x01\x02\x03\x04"
        return bytes(head) + key + _mask(payload, key)
    return bytes(head) + payload


def _header(opcode, length, fin, masked):
    b0 = (0x80 if fin else 0) | opcode
    m = 0x80 if masked else 0
    if length < 126:
        return bytes([b0, m | length])
    if length < 65536:
        return bytes([b0, m | 126]) + struct.pack("!H", length)
    return bytes([b0, m | 127]) + struct.pack("!Q", length)


def close_payload(code=1000, reason=""):
    return struct.pack("!H", code) + reason.encode("utf-8")[:120]


class FrameParser:
    """Incremental parser of server frames into complete messages.

    ``feed`` returns a list of ``(opcode, payload)``: data messages are
    reassembled; control frames (which may interleave a fragmented message)
    are returned as they arrive.
    """

    def __init__(self, max_message_bytes=MAX_MESSAGE_BYTES):
        self.buf = bytearray()
        self.max = max_message_bytes
        self.frag_opcode = None
        self.frag = bytearray()
        self.closed = False

    def feed(self, data):
        if self.closed and data:
            raise WireError("DATA_AFTER_CLOSE")
        self.buf += data
        out = []
        while True:
            frame = self._next_frame()
            if frame is None:
                return out
            fin, opcode, payload = frame
            if opcode in CONTROL_OPCODES:
                if opcode == OP_CLOSE:
                    if len(payload) == 1:
                        raise WireError("CLOSE_PAYLOAD")
                    self.closed = True
                out.append((opcode, payload))
                if self.closed:
                    if self.buf:
                        raise WireError("DATA_AFTER_CLOSE")
                    return out
                continue
            if opcode == OP_CONT:
                if self.frag_opcode is None:
                    raise WireError("UNEXPECTED_CONTINUATION")
            elif self.frag_opcode is not None:
                raise WireError("INTERLEAVED_DATA_FRAME")
            else:
                self.frag_opcode = opcode
            self.frag += payload
            if len(self.frag) > self.max:
                raise WireError("MESSAGE_TOO_LARGE", str(len(self.frag)))
            if fin:
                message, op = bytes(self.frag), self.frag_opcode
                self.frag, self.frag_opcode = bytearray(), None
                if op == OP_TEXT:
                    try:
                        message.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise WireError("TEXT_NOT_UTF8") from exc
                out.append((op, message))

    def _next_frame(self):
        b = self.buf
        if len(b) < 2:
            return None
        fin, rsv, opcode = bool(b[0] & 0x80), (b[0] >> 4) & 0x7, b[0] & 0x0F
        masked, length = bool(b[1] & 0x80), b[1] & 0x7F
        if rsv:
            raise WireError("RSV_BITS_SET")
        if opcode not in DATA_OPCODES + CONTROL_OPCODES + (OP_CONT,):
            raise WireError("UNKNOWN_OPCODE", str(opcode))
        if masked:
            raise WireError("MASKED_SERVER_FRAME")
        if opcode in CONTROL_OPCODES and (not fin or length > 125):
            raise WireError("CONTROL_FRAME_INVALID")
        pos = 2
        if length == 126:
            if len(b) < 4:
                return None
            length = struct.unpack_from("!H", b, 2)[0]
            if length < 126:
                raise WireError("NON_MINIMAL_LENGTH")
            pos = 4
        elif length == 127:
            if len(b) < 10:
                return None
            length = struct.unpack_from("!Q", b, 2)[0]
            if length >> 63 or length < 65536:
                raise WireError("NON_MINIMAL_LENGTH")
            pos = 10
        if length > self.max:
            raise WireError("FRAME_TOO_LARGE", str(length))
        if len(b) < pos + length:
            return None
        payload = bytes(b[pos:pos + length])
        del b[:pos + length]
        return fin, opcode, payload


# ---------------------------------------------------------------- protobuf

# Field numbers verified against mexc_proto/*.proto by tests/radar_composite/test_bbo_wire.py
WRAPPER_FIELDS = {"channel": 1, "symbol": 3, "symbolId": 4, "createTime": 5, "sendTime": 6,
                  "publicAggreDepths": 313}
DEPTHS_FIELDS = {"asks": 1, "bids": 2, "eventType": 3, "fromVersion": 4, "toVersion": 5,
                 "lastOrderCreateTime": 6}
ITEM_FIELDS = {"price": 1, "quantity": 2}
VARINT, I64, LEN, I32 = 0, 1, 2, 5


def read_varint(buf, pos):
    result = shift = 0
    while True:
        if pos >= len(buf):
            raise WireError("PB_TRUNCATED_VARINT")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if result >> 64:
                raise WireError("PB_VARINT_OVERFLOW")
            return result, pos
        shift += 7
        if shift >= 70:
            raise WireError("PB_VARINT_TOO_LONG")


def iter_fields(buf):
    """Yield (field_number, wire_type, value); LEN values are bytes."""
    pos, end = 0, len(buf)
    while pos < end:
        key, pos = read_varint(buf, pos)
        number, wtype = key >> 3, key & 7
        if number == 0:
            raise WireError("PB_FIELD_ZERO")
        if wtype == VARINT:
            value, pos = read_varint(buf, pos)
        elif wtype == I64:
            if pos + 8 > end:
                raise WireError("PB_TRUNCATED_I64")
            value, pos = bytes(buf[pos:pos + 8]), pos + 8
        elif wtype == LEN:
            size, pos = read_varint(buf, pos)
            if pos + size > end:
                raise WireError("PB_TRUNCATED_LEN")
            value, pos = bytes(buf[pos:pos + size]), pos + size
        elif wtype == I32:
            if pos + 4 > end:
                raise WireError("PB_TRUNCATED_I32")
            value, pos = bytes(buf[pos:pos + 4]), pos + 4
        else:
            raise WireError("PB_UNSUPPORTED_WIRE_TYPE", str(wtype))
        yield number, wtype, value


def _int64(v):
    return v - (1 << 64) if v >> 63 else v


def _expect(number, wtype, want, seen, repeated=False):
    if wtype != want:
        raise WireError("PB_WIRE_TYPE_MISMATCH", str(number))
    if not repeated:
        if number in seen:
            raise WireError("PB_DUPLICATE_FIELD", str(number))
        seen.add(number)


def _str(value, number):
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WireError("PB_STRING_NOT_UTF8", str(number)) from exc


def decode_depth_item(buf):
    out, seen = {"price": "", "quantity": ""}, set()
    for number, wtype, value in iter_fields(buf):
        if number in (1, 2):
            _expect(number, wtype, LEN, seen)
            out["price" if number == 1 else "quantity"] = _str(value, number)
    return out["price"], out["quantity"]


def decode_aggre_depths(buf):
    out = {"asks": [], "bids": [], "eventType": "", "fromVersion": "", "toVersion": "",
           "lastOrderCreateTime": 0}
    seen = set()
    for number, wtype, value in iter_fields(buf):
        if number in (1, 2):
            _expect(number, wtype, LEN, seen, repeated=True)
            out["asks" if number == 1 else "bids"].append(decode_depth_item(value))
        elif number in (3, 4, 5):
            _expect(number, wtype, LEN, seen)
            out[{3: "eventType", 4: "fromVersion", 5: "toVersion"}[number]] = _str(value, number)
        elif number == 6:
            _expect(number, wtype, VARINT, seen)
            out["lastOrderCreateTime"] = _int64(value)
    return out


def decode_mexc_push(buf):
    """Decode a PushDataV3ApiWrapper. Unknown fields are skipped and counted.

    ``body`` is the aggregated depth when field 313 is present, else None with
    ``body_field`` naming the oneof member that was present (if any).
    """
    out = {"channel": None, "symbol": None, "symbolId": None, "createTime": None,
           "sendTime": None, "body_field": None, "body": None, "unknown_fields": []}
    seen = set()
    for number, wtype, value in iter_fields(buf):
        if number in (1, 3, 4):
            _expect(number, wtype, LEN, seen)
            out[{1: "channel", 3: "symbol", 4: "symbolId"}[number]] = _str(value, number)
        elif number in (5, 6):
            _expect(number, wtype, VARINT, seen)
            out["createTime" if number == 5 else "sendTime"] = _int64(value)
        elif number == 313:
            _expect(number, wtype, LEN, seen)
            if out["body_field"] is not None:
                raise WireError("PB_ONEOF_TWICE")
            out["body_field"], out["body"] = 313, decode_aggre_depths(value)
        elif 300 <= number <= 399 and wtype == LEN:
            if out["body_field"] is not None:
                raise WireError("PB_ONEOF_TWICE")
            out["body_field"] = number
        else:
            out["unknown_fields"].append(number)
    if out["channel"] is None:
        raise WireError("PB_MISSING_CHANNEL")
    return out


# ---------------------------------------------------------------- protobuf encoder (synthetic)

def _varint(v):
    if v < 0:
        v += 1 << 64
    out = bytearray()
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(number, wtype):
    return _varint((number << 3) | wtype)


def _len_field(number, data):
    return _key(number, LEN) + _varint(len(data)) + data


def encode_aggre_depths(asks, bids, from_version, to_version, *, event_type="",
                        last_order_create_time=None):
    out = bytearray()
    for number, side in ((1, asks), (2, bids)):
        for price, qty in side:
            out += _len_field(number, _len_field(1, price.encode()) + _len_field(2, qty.encode()))
    if event_type:
        out += _len_field(3, event_type.encode())
    out += _len_field(4, str(from_version).encode()) + _len_field(5, str(to_version).encode())
    if last_order_create_time is not None:
        out += _key(6, VARINT) + _varint(last_order_create_time)
    return bytes(out)


def encode_mexc_push(channel, symbol, body, *, send_time=None, create_time=None, body_field=313):
    out = bytearray(_len_field(1, channel.encode()))
    out += _len_field(body_field, body)
    if symbol is not None:
        out += _len_field(3, symbol.encode())
    if create_time is not None:
        out += _key(5, VARINT) + _varint(create_time)
    if send_time is not None:
        out += _key(6, VARINT) + _varint(send_time)
    return bytes(out)
