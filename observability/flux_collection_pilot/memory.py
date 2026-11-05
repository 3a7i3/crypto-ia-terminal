"""Verifiable memory ceiling.

Three layers, reported separately (see the report's enforcement table):
1. ``MemoryGuard.check`` - the runner compares the process resident size with the
   cap on every session open and every ``CHECK_EVERY`` messages; an unreadable
   value is a stop (``MEMORY_UNVERIFIABLE``), never "0".
2. ``apply_data_limit`` - ``RLIMIT_DATA`` for the live launcher (kernel enforced,
   readable back); verified in a subprocess by the tests, never applied to the
   test process itself.
3. A cgroup/systemd ``MemoryMax`` is an OPERATOR setting outside this package and
   is only RECORDED in the manifest.
"""


CHECK_EVERY = 256


def rss_bytes():
    """Resident set size from /proc, or None when it cannot be read."""
    try:
        with open("/proc/self/status", "rb") as f:
            for line in f:
                if line.startswith(b"VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class MemoryGuard:
    def __init__(self, limit_bytes, reader=rss_bytes):
        if type(limit_bytes) is not int or limit_bytes <= 0:
            raise ValueError("MEMORY_LIMIT_REQUIRED")
        self.limit, self.reader = limit_bytes, reader
        self.peak = None

    def check(self):
        """(ok, reason, value). Fails closed on an unreadable value."""
        v = self.reader()
        if type(v) is not int or v < 0:
            return False, "MEMORY_UNVERIFIABLE", None
        self.peak = v if self.peak is None else max(self.peak, v)
        if v >= self.limit:
            return False, "MEMORY_CAP", v
        return True, None, v


def apply_data_limit(limit_bytes):
    """Set RLIMIT_DATA (soft=hard) and read it back. Returns the observed (soft, hard)."""
    import resource

    resource.setrlimit(resource.RLIMIT_DATA, (limit_bytes, limit_bytes))
    return resource.getrlimit(resource.RLIMIT_DATA)


