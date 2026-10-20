"""Lab child launcher, executed by the supervisor inside its sandbox only.

It runs one worker module on one task read from stdin and writes one JSON
result to stdout. Everything it prints is an untrusted claim of the
individual; the supervisor decides what is recorded.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_PREFIXES = ("colony_lab.workers.", "tests.colony_lab.")
MAX_TASK_BYTES = 16_384
EXIT_USAGE, EXIT_TASK, EXIT_MEMORY = 64, 65, 70


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith(WORKER_PREFIXES):
        return EXIT_USAGE
    sys.path.insert(0, str(ROOT))
    raw = sys.stdin.buffer.read(MAX_TASK_BYTES + 1)
    if len(raw) > MAX_TASK_BYTES:
        return EXIT_TASK
    try:
        import importlib

        worker = importlib.import_module(sys.argv[1])
        task = json.loads(raw)
        output = worker.run(task["payload"])
        sys.stdout.write(json.dumps({"result_schema": "colony-lab.result/0", "task_id": task["task_id"],
                                     "output": output}, ensure_ascii=False, allow_nan=False, sort_keys=True))
    except MemoryError:
        return EXIT_MEMORY
    return 0


if __name__ == "__main__":
    sys.exit(main())
