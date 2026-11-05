"""Sequence analysis per candidate counter domain. Never merges sessions.

The provider documentation is ambiguous: the AsyncAPI envelope says
``sequence_num`` is "per-connection", the general guide says "for each product".
Four candidate domains are therefore tracked side by side; a candidate is
REFUTED (never confirmed) by an observed gap, repeat or rewind in its own
counters. A tracker instance belongs to ONE session: a new connection starts
from nothing and no counter is carried over.

Policy (``protocol.SEQUENCE_POLICIES``) decides which domain's anomaly stops a
live collection or invalidates a book. The default PER_CHANNEL never lets a
counter of another channel explain an ``l2_data`` hole.
"""

from . import protocol

OK, BASELINE, GAP, REPEAT, REWIND = "OK", "BASELINE", "GAP", "REPEAT", "REWIND"
HYPOTHESES = ("PER_CONNECTION", "PER_CHANNEL", "PER_PRODUCT", "PER_CHANNEL_PRODUCT")


def _step(last, seq):
    if last is None:
        return BASELINE, None
    if seq == last + 1:
        return OK, None
    if seq == last:
        return REPEAT, last + 1
    if seq < last:
        return REWIND, last + 1
    return GAP, last + 1


class SequenceTracker:
    def __init__(self, policy=protocol.DEFAULT_SEQUENCE_POLICY):
        if policy not in protocol.SEQUENCE_POLICIES:
            raise ValueError("SEQUENCE_POLICY_UNKNOWN")
        self.policy = policy
        self._last = {h: {} for h in HYPOTHESES}
        self.refuted = {h: None for h in HYPOTHESES}  # first refuting (index, kind, key) or None
        self.anomalies = []  # every non-OK/BASELINE verdict of every domain
        self.count = 0

    def _keys(self, hyp, channel, products):
        if hyp == "PER_CONNECTION":
            return [("*",)]
        if hyp == "PER_CHANNEL":
            return [(channel,)]
        if hyp == "PER_PRODUCT":
            return [(p,) for p in products]  # no product -> that message has no such counter
        return [(channel, p) for p in products] or [(channel, "")]

    def observe(self, index, channel, seq, products=()):
        """Record one message; return the verdict of the POLICY domain.

        ``{"kind", "expected", "got", "domain", "key"}``; kind is OK/BASELINE/GAP/REPEAT/REWIND
        or OK when the policy domain does not apply to this channel.
        """
        self.count += 1
        verdict = {"kind": OK, "expected": None, "got": seq, "domain": self.policy, "key": None}
        for hyp in HYPOTHESES:
            for key in self._keys(hyp, channel, products):
                kind, expected = _step(self._last[hyp].get(key), seq)
                self._last[hyp][key] = max(seq, self._last[hyp].get(key, -1)) if kind in (REPEAT, REWIND) else seq
                if kind in (GAP, REPEAT, REWIND):
                    self.anomalies.append(
                        {"index": index, "domain": hyp, "key": list(key), "kind": kind,
                         "expected": expected, "got": seq}
                    )
                    if self.refuted[hyp] is None:
                        self.refuted[hyp] = {"index": index, "kind": kind, "key": list(key)}
                    if hyp == self.policy and self._applies(channel) and verdict["kind"] in (OK, BASELINE):
                        verdict.update(kind=kind, expected=expected, key=list(key))
                elif kind == BASELINE and hyp == self.policy and verdict["kind"] == OK:
                    verdict.update(kind=BASELINE, key=list(key))
        return verdict

    def _applies(self, channel):
        # PER_CHANNEL: only an l2_data counter can suspect the book; other
        # policies share counters across channels, any anomaly is suspect.
        return channel == protocol.L2_CHANNEL if self.policy == "PER_CHANNEL" else True

    def report(self):
        return {
            "messages": self.count,
            "policy": self.policy,
            "hypotheses": {h: {"consistent": self.refuted[h] is None, "first_refutation": self.refuted[h]}
                           for h in HYPOTHESES},
            "anomalies": self.anomalies[:100],
            "anomaly_count": len(self.anomalies),
        }
