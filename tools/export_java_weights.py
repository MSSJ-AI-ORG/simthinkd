#!/usr/bin/env python3
"""Export a decider's weights (.npz or a folder with decider.json) for the Java runtime (java/src/main/java/simthinkd).

    python tools/export_java_weights.py <decider folder or weights.npz> <out.smtd>
File: one header line 'SMTD1 {json}' (source_sha256 of the npz, temperature, array names and shapes), then the arrays as
little-endian float32 in header order.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

NAMES = ["local.weight", "local.bias", "context.weight", "context.bias", "score.weight", "score.bias"]


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if src.is_dir():
        card = json.loads((src / "decider.json").read_text(encoding="utf8"))
        src = src / card["weights"]
    with np.load(src, allow_pickle=False) as w:
        arrays = {k: np.ascontiguousarray(w[k], dtype="<f4") for k in NAMES}
        temperature = float(w["temperature"]) if "temperature" in w.files else 1.0
    header = {"source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "temperature": temperature,
              "arrays": [{"name": k, "shape": list(arrays[k].shape)} for k in NAMES]}
    with open(out, "wb") as f:
        f.write(("SMTD1 " + json.dumps(header) + "\n").encode())
        for k in NAMES:
            f.write(arrays[k].tobytes())
    print(json.dumps({"out": str(out), **header}))


if __name__ == "__main__":
    main()
