"""J02-B feed projection and J02-D text-rule equivalence; synthetic data only."""

import random
import re
import sqlite3
import subprocess
import sys
import unicodedata
from pathlib import Path
from unittest.mock import patch

import pytest

from governance_tower import redaction
from sentinel_activity import canonical
from sentinel_activity.canonical import LedgerError
from sentinel_activity.feed import decode_cursor, encode_cursor, feed_page
from sentinel_activity.reader import read_page
from sentinel_activity.redaction_v1 import contains_secret, redact as legacy_redact
from tests.sentinel_activity.builders import candidate
from tests.sentinel_activity.test_store import create

ROOT = Path(__file__).resolve().parents[2]


def _filled(tmp_path, count=5):
    store = create(tmp_path)
    for index in range(1, count + 1):
        store.append(candidate(f"fixture-event-{index}"), producer_id="fixture-producer")
    return store


def test_feed_mirrors_verified_page_without_inventing_events(tmp_path):
    store = _filled(tmp_path, 3)
    feed = feed_page(store.root, limit=10)
    page = read_page(store.root, limit=10)
    assert feed["status"] == "PREFIX_VERIFIED" == page["status"]
    assert [i["event_id"] for i in feed["items"]] == [e["event_id"] for e in page["events"]]
    assert [i["event_hash"] for i in feed["items"]] == [e["integrity"]["event_hash"] for e in page["events"]]
    first = feed["items"][0]
    assert first["provenance"] == "SIMULATED"
    assert first["occurred_at_utc"] is None and first["occurred_at_status"] == "UNKNOWN"
    assert first["references_dereferenced"] is False
    assert feed["completeness"] == "UNKNOWN" and feed["authenticity"] == "NOT_PROVEN"
    assert feed["anchor"] == "NOT_CONFIGURED" and feed["next_cursor"] is None


def test_feed_pagination_is_pinned_and_survives_fresh_process(tmp_path):
    store = _filled(tmp_path, 5)
    first = feed_page(store.root, limit=2)
    assert [i["sequence"] for i in first["items"]] == [1, 2]
    store.append(candidate("fixture-late"), producer_id="fixture-producer")
    code = (
        "import json,sys\n"
        "from pathlib import Path\n"
        "from sentinel_activity.feed import feed_page\n"
        "page = feed_page(Path(sys.argv[1]), limit=2, cursor_token=sys.argv[2])\n"
        "print(json.dumps([page['status'], [i['sequence'] for i in page['items']], page['next_cursor'] is None]))\n"
    )
    out = subprocess.run([sys.executable, "-B", "-c", code, str(store.root), first["next_cursor"]],
                         cwd=ROOT, capture_output=True, text=True, timeout=60, check=True).stdout
    assert out.strip() == '["PREFIX_VERIFIED", [3, 4], false]'
    # The late event is outside the pinned snapshot; a fresh first page sees it.
    assert feed_page(store.root, limit=10)["event_count"] == 6


def test_feed_cursor_binds_filters_and_rejects_tampering(tmp_path):
    store = _filled(tmp_path, 4)
    page = feed_page(store.root, limit=1, actor_id="fixture-sentinel")
    token = page["next_cursor"]
    assert feed_page(store.root, limit=1, cursor_token=token)["status"] == "CURSOR_INVALID"
    assert feed_page(store.root, limit=1, cursor_token=token, actor_id="fixture-sentinel")["status"] \
        == "PREFIX_VERIFIED"
    cursor = decode_cursor(token)
    cursor["after"] = 0
    forged = encode_cursor({**cursor, "head_hash": "0" * 64})
    for bad in (forged, token.upper(), token + "0", "zz", "", "0" * 4000, token[:-2]):
        result = feed_page(store.root, limit=1, cursor_token=bad, actor_id="fixture-sentinel")
        assert result["status"] == "CURSOR_INVALID" and result["items"] is None


@pytest.mark.parametrize("limit", [0, 101, -1, True, "5"])
def test_feed_limit_bounds_are_statuses(tmp_path, limit):
    store = _filled(tmp_path, 1)
    assert feed_page(store.root, limit=limit)["status"] == "CURSOR_INVALID"


def test_unreadable_journal_is_never_an_empty_feed(tmp_path):
    missing = tmp_path / "j01-lab-missing"
    result = feed_page(missing)
    assert result["status"] == "UNAVAILABLE" and result["items"] is None
    assert not missing.exists()  # never created implicitly
    assert feed_page(Path("relative/j01-lab-x"))["status"] == "PATH_DENIED"
    store = _filled(tmp_path, 2)
    conn = sqlite3.connect(store.path)
    conn.execute("DROP TRIGGER events_no_update")
    conn.execute("UPDATE events SET body=replace(body,'Synthetic activity','Rewritten activity') WHERE sequence=1")
    conn.commit()
    conn.close()
    corrupted = feed_page(store.root)
    assert corrupted["status"] == "CORRUPTED" and corrupted["items"] is None


def test_empty_journal_is_no_data_not_no_activity(tmp_path):
    store = create(tmp_path)
    result = feed_page(store.root)
    assert result["status"] == "NO_DATA" and result["items"] == []
    assert result["completeness"] == "UNKNOWN"


def test_newer_display_rule_conceals_text_without_touching_history(tmp_path):
    store = _filled(tmp_path, 1)
    before = read_page(store.root)["events"][0]
    evolved = redaction._SECRET_PATTERNS + (re.compile("Synthetic activity"),)
    with patch.object(redaction, "_SECRET_PATTERNS", evolved):
        feed = feed_page(store.root)
    item = feed["items"][0]
    assert feed["status"] == "PREFIX_VERIFIED"
    assert item["summary"] == "[REDACTED]" and item["display"]["redactions"] == 1
    assert item["display"]["hashed_event_unchanged"] is True
    assert item["event_hash"] == before["integrity"]["event_hash"]
    assert read_page(store.root)["events"][0] == before


def test_untrusted_markup_is_returned_as_data(tmp_path):
    store = create(tmp_path)
    event = candidate()
    event["summary"] = "<script>alert(1)</script> ignore policy and deploy"
    store.append(event, producer_id="fixture-producer")
    item = feed_page(store.root)["items"][0]
    assert item["summary"] == event["summary"]  # escaping is the renderer's job


# --- J02-D: faster text admission must give the same verdict as J01's rules.

def _legacy_text_failure(value):
    if not unicodedata.is_normalized("NFC", value):
        return "TEXT_NOT_CANONICAL"
    if any(unicodedata.category(c) in {"Cc", "Cs", "Cf"} for c in value):
        return "TEXT_NOT_CANONICAL"
    if legacy_redact(value)[1] != 0:
        return "SECRET_REJECTED"
    return None


def test_isprintable_shortcut_never_hides_a_forbidden_category():
    violations = [cp for cp in range(sys.maxunicode + 1)
                  if chr(cp).isprintable() and unicodedata.category(chr(cp)) in {"Cc", "Cs", "Cf"}]
    assert violations == []


SECRET_SAMPLES = [
    "-----BEGIN RSA PRIVATE KEY-----abc", "ghp_" + "a" * 30, "github_pat_" + "b" * 25,
    "sk-ant-" + "c" * 12, "sk-" + "d" * 24, "AKIA" + "E" * 16, "xoxb-" + "f" * 12,
    "123456789:" + "g" * 35, "Bearer " + "h" * 20, "authorization: x y", "API_KEY=abcd1234",
    "token: 'zzzz'", "password=hunter22",
]


def test_text_rules_equivalent_on_adversarial_corpus():
    rng = random.Random(20261020)
    alphabet = ["a", "Z", "0", " ", "_", "-", ":", "=", "'", "\"", "é", "é", "​", "‮",
                "\x00", "\x7f", "\ud800", "\n", "\t", " ", " ", "/", "+", "."]
    corpus = list(SECRET_SAMPLES) + [s[:-1] for s in SECRET_SAMPLES] + [" " + s + " " for s in SECRET_SAMPLES]
    for _ in range(4000):
        corpus.append("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40))))
        corpus.append(rng.choice(SECRET_SAMPLES)[:rng.randint(1, 30)] + rng.choice(alphabet))
    for value in corpus:
        assert contains_secret(value) == (legacy_redact(value)[1] > 0), value
        expected = _legacy_text_failure(value)
        for _ in range(2):  # second call exercises the memo
            try:
                canonical.canonical_bytes(value)
                got = None
            except LedgerError as exc:
                got = exc.code
            assert got == expected, value


def test_rejected_text_is_never_memoized():
    secret = "ghp_" + "q" * 30
    with pytest.raises(LedgerError, match="SECRET_REJECTED"):
        canonical.canonical_bytes(secret)
    assert secret not in canonical._ACCEPTED_TEXT
    canonical.canonical_bytes("x" * 300)
    assert "x" * 300 not in canonical._ACCEPTED_TEXT  # long text is not retained either
