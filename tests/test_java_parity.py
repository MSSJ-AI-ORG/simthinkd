"""Java runtime parity: java/src/main/java/simthinkd must choose exactly what the Python decider chooses.

    python -X utf8 tests/test_java_parity.py <decider folder> <requests.jsonl> [--synthetic N]
Compiles the Java runtime (javac --release 8), exports the weights (tools/export_java_weights.py), feeds every request to
both, and compares the operation choice and, when offered, the target choice. Adds synthetic requests (Korean, emoji,
punctuation, long texts, recent actions) built from the same decider. Exit 0 only if 100% of choices agree; reports the
largest probability difference.
"""
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from simthinkd import Decider  # noqa: E402

WORDS = ["적", "해병", "zealot", "dist", "12", "hp", "40", "near", "멀리", "😀", "—", "a.b", "x_y", "Ⅻ", "ﬁ", "Ünïcode", "\t", "  "]


def synthetic(base, rng, n):
    out = []
    for _ in range(n):
        b = json.loads(json.dumps(base))
        crit = b["questions"].get("attack_target", {}).get("criteria", {})
        for k in list(crit):
            crit[k]["description"] = " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 25)))
        b["state"]["page"]["text"] = " ".join(rng.choice(WORDS) for _ in range(rng.randint(0, 40)))
        if rng.random() < 0.5:
            b["state"]["recent_actions"] = [{"action": rng.choice(["ATTACK", "e0", "e1", "WAIT"]), "page_changed": rng.random() < 0.5}
                                            for _ in range(rng.randint(1, 6))]
        out.append(b)
    return out


def main():
    model, reqs = Path(sys.argv[1]), Path(sys.argv[2])
    n_syn = int(sys.argv[sys.argv.index("--synthetic") + 1]) if "--synthetic" in sys.argv else 500
    bodies = [json.loads(l) for l in reqs.read_text(encoding="utf-8").splitlines() if l.strip()]
    bodies += synthetic(bodies[0], random.Random(5), n_syn)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        smtd = t / "w.smtd"
        subprocess.run([sys.executable, str(ROOT / "tools" / "export_java_weights.py"), str(model), str(smtd)], check=True, capture_output=True)
        src = sorted(str(p) for p in (ROOT / "java" / "src" / "main" / "java" / "simthinkd").glob("*.java"))
        subprocess.run(["javac", "--release", "8", "-encoding", "UTF-8", "-d", str(t / "cls"), *src], check=True)
        inp = "\n".join(json.dumps(b, ensure_ascii=False) for b in bodies) + "\n"
        r = subprocess.run(["java", "-cp", str(t / "cls"), "simthinkd.SimThinkD", str(smtd)], input=inp.encode("utf-8"), capture_output=True, check=True)
        jans = [json.loads(l) for l in r.stdout.decode("utf-8").splitlines() if l.strip()]
    d = Decider(str(model))
    assert len(jans) == len(bodies), (len(jans), len(bodies))
    agree_op = agree_t = n_t = 0
    max_diff = 0.0
    bad = []
    for i, (b, ja) in enumerate(zip(bodies, jans)):
        pa = d.predict(b)
        agree_op += pa["operation"]["choice"] == ja["operation"]["choice"]
        for k, v in pa["operation"]["probabilities"].items():
            max_diff = max(max_diff, abs(v - ja["operation"]["probabilities"][k]))
        heads = [h for h in pa if h.endswith("_target")]
        for h in heads:
            n_t += 1
            ok = h in ja and pa[h]["choice"] == ja[h]["choice"]
            agree_t += ok
            if h in ja:
                for k, v in pa[h]["probabilities"].items():
                    max_diff = max(max_diff, abs(v - ja[h]["probabilities"].get(k, -1)))
            if not ok and len(bad) < 5:
                bad.append({"i": i, "py": pa[h]["choice"], "java": ja.get(h, {}).get("choice"),
                            "py_p": sorted(pa[h]["probabilities"].values())[-2:]})
    ms = sorted(j["_ms"] for j in jans)
    rep = {"requests": len(bodies), "operation_agree": agree_op, "target_questions": n_t, "target_agree": agree_t,
           "max_prob_diff": max_diff, "java_ms_p50": ms[len(ms) // 2], "java_ms_p95": ms[int(len(ms) * 0.95)], "mismatches": bad}
    print(json.dumps(rep, ensure_ascii=False))
    sys.exit(0 if agree_op == len(bodies) and agree_t == n_t else 1)


if __name__ == "__main__":
    main()
