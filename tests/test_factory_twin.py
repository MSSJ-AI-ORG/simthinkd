"""Factory twin end-to-end test: train a decider, serve it, run the twin against it, check the results.

    python -X utf8 tests/test_factory_twin.py        (needs simthinkd[train])

Exit 0 = all pass. This runs the same three commands as examples/factory_twin/README.md.
"""
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

TWIN = Path(__file__).resolve().parents[1] / "examples" / "factory_twin"
PY = sys.executable


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    results = []
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        r = subprocess.run([PY, "-X", "utf8", str(TWIN / "train_inspection_decider.py"), "--out", str(t / "decider")],
                           capture_output=True, text=True, cwd=TWIN)
        results.append(("train", r.returncode == 0 and (t / "decider" / "weights.npz").exists(), r.stderr[-300:]))
        port = free_port()
        server = subprocess.Popen([PY, "-m", "simthinkd.cli", "serve", str(t / "decider"), "--port", str(port)],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            health = None
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as h:
                        health = json.loads(h.read())
                        break
                except OSError:
                    time.sleep(0.5)
            results.append(("serve", bool(health and health.get("weights_sha256")), str(health)))
            out = t / "result.json"
            r = subprocess.run([PY, "-X", "utf8", str(TWIN / "run.py"), "--arm", "D", "--parts", "50", "--timing", "live",
                                "--url", f"http://127.0.0.1:{port}", "--out", str(out)], capture_output=True, text=True, cwd=TWIN)
            ok = r.returncode == 0 and out.exists()
            results.append(("run arm D", ok, (r.stdout + r.stderr)[-400:]))
            if ok:
                m = json.loads(out.read_text(encoding="utf-8"))["metrics"]
                results.append(("50 parts done", m["parts"] == 50, m))
                results.append(("decisions on time (late < 10%)", m["late_rate"] < 0.10, m["late_rate"]))
                results.append(("decider mostly right (>= 70%)", m["correct_rate"] >= 0.70, m["correct_rate"]))
        finally:
            server.terminate()
            server.wait(timeout=10)
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" | {info}"))
    return 0 if results and all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
