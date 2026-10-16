"""Fabrique, a partir du helper reel, des variantes avec UNE faute ou une pause injectee. Bac a sable seulement.
usage : patch_helpers.py <helper.py> <dossier de sortie>"""

import pathlib
import sys

src = pathlib.Path(sys.argv[1]).read_text()
# Test-only registration; no global process-name search or production helper edit.
src = src.replace(
    'if __name__ == "__main__":\n',
    'if __name__ == "__main__":\n'
    '    if os.environ.get("SBX"):\n'
    '        with open(os.path.join(os.environ["SBX"], "helper-pids"), "a") as pids:\n'
    '            pids.write(str(os.getpid()) + "\\n")\n',
    1,
)
out = pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def patch(old, new):
    assert src.count(old) == 1, old
    return src.replace(old, new, 1)


V = {"orig": src}
V["h_stall_tmp"] = patch(
    "            os.fsync(stream.fileno())\n        os.link(tmp, DROPIN)",
    "            os.fsync(stream.fileno())\n"
    '        print("MARK_TMP_WRITTEN", flush=True)\n'
    "        time.sleep(60)\n"
    "        os.link(tmp, DROPIN)",
)
V["h_stall_linked"] = patch(
    "        created = True\n",
    '        created = True\n        print("MARK_DROPIN_CREATED", flush=True)\n        time.sleep(60)\n',
)
V["h_stall_restart"] = patch(
    '        command("systemctl", "restart", WEB)\n        last_error = None',
    '        command("systemctl", "restart", WEB)\n'
    '        print("MARK_AFTER_RESTART", flush=True)\n'
    "        time.sleep(60)\n"
    "        last_error = None",
)
V["h_noverify"] = patch(
    "                verify_served(files)\n                last_error = None",
    "                last_error = None",
)
for name, text in V.items():
    (out / f"{name}.py").write_text(text)
