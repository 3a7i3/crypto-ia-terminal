"""Pilote : lance 'final_block.sh activate' (script = parent, helper = enfant), attend un marqueur, applique UNE action.
Actions : kill_parent | kill_group | term_helper | hup_group | pty_loss (fermeture du maitre d'un vrai pty)."""
import fcntl, os, pty, signal, subprocess, sys, termios, time
script, log, marker, action = sys.argv[1:5]
env = dict(os.environ, PATH=os.environ["SBX"] + "/bin:" + os.environ["PATH"])
def helper_pids():
    return [int(x) for x in subprocess.run(["pgrep", "-f", "activate_workboard_frontend.py --archive"], capture_output=True, text=True).stdout.split()]
def wait_marker():
    for _ in range(80):
        time.sleep(0.25)
        if marker in open(log, errors="replace").read(): return True
    return False
if action == "pty_loss":
    master, slave = pty.openpty()
    def child():
        os.setsid(); fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        for fd in (0, 1, 2): os.dup2(slave, fd)
        if slave > 2: os.close(slave)
        os.close(master)
    p = subprocess.Popen(["bash", script, "activate"], env=env, preexec_fn=child, close_fds=True)
    os.close(slave); os.write(master, b"ACTIVER\n"); seen = b""; ok = False
    with open(log, "wb") as out:
        end = time.time() + 20
        while time.time() < end:
            try: d = os.read(master, 4096)
            except OSError: break
            out.write(d); out.flush(); seen += d
            if marker.encode() in seen: ok = True; break
    if not ok: os.killpg(p.pid, signal.SIGKILL); print("MARQUEUR ABSENT"); sys.exit(3)
    os.close(master); print("rc script =", p.wait(timeout=150)); sys.exit(0)
with open(log, "w") as out:
    p = subprocess.Popen(["bash", script, "activate"], stdin=subprocess.PIPE, stdout=out, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    p.stdin.write(b"ACTIVER\n"); p.stdin.close()
    if not wait_marker(): os.killpg(p.pid, signal.SIGKILL); print("MARQUEUR ABSENT"); sys.exit(3)
    hp = helper_pids(); print("pid script parent =", p.pid, "; pid helper(s) =", hp)
    if action == "kill_parent": os.kill(p.pid, signal.SIGKILL)
    elif action == "kill_group": os.killpg(p.pid, signal.SIGKILL)
    elif action == "term_helper":
        for x in hp: os.kill(x, signal.SIGTERM)
    elif action == "hup_group": os.killpg(p.pid, signal.SIGHUP)
    else: sys.exit(4)
    print("action =", action)
    try: print("rc script =", p.wait(timeout=150))
    except subprocess.TimeoutExpired: print("rc script = TIMEOUT"); os.killpg(p.pid, signal.SIGKILL)
    time.sleep(1); print("helper vivant apres l'action =", "OUI" if helper_pids() else "NON")
