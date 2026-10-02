#!/usr/bin/env python3
"""Export trained weights to JSON format for browser use.

Usage:
    python tools/export_web_weights.py
"""
import base64
import hashlib
import json
from pathlib import Path

import numpy as np

from simthinkd.core import PRESETS

REPO_ROOT = Path(__file__).parent.parent
WEIGHTS_DIR = REPO_ROOT / "src" / "simthinkd" / "weights"
WEB_WEIGHTS_DIR = REPO_ROOT / "web" / "weights"


def export_weights(preset_name: str, output_dir: Path) -> dict:
    """Export a single preset's weights to JSON.

    Returns metadata dict (sha256, temperature, actions, goal, etc).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    preset = PRESETS[preset_name]
    weights_file = WEIGHTS_DIR / preset["weights"]

    # Load and verify
    sha256 = hashlib.sha256(weights_file.read_bytes()).hexdigest()
    assert sha256 == preset["sha256"], f"SHA mismatch for {preset_name}"

    # Load arrays
    with np.load(weights_file, allow_pickle=False) as f:
        temperature = float(f["temperature"])
        arrays = {key: f[key].astype("<f4") for key in f.files if key != "temperature"}

    # Little-endian float32 bytes, base64 (about 4x smaller than JSON number lists)
    weights_json = {"temperature": temperature}
    for key, arr in arrays.items():
        weights_json[key] = {"shape": list(arr.shape), "b64": base64.b64encode(arr.tobytes()).decode("ascii")}

    # Write to JSON
    output_file = output_dir / f"{preset_name}.json"
    meta = {
        "preset": preset_name,
        "sha256": sha256,
        "temperature": weights_json.pop("temperature"),
        "goal": preset.get("goal", ""),
        "url": preset.get("url", ""),
        "title": preset.get("title", ""),
        "model": preset.get("model", ""),
        "about": preset.get("about", ""),
        "example": preset.get("example", ""),
        "actions": preset.get("actions", {}),
        "weights": weights_json,
    }

    output_file.write_text(json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
    print(f"Exported {preset_name}: {output_file}")
    return meta


if __name__ == "__main__":
    for preset_name in ["doom-defend", "doom-corridor"]:
        export_weights(preset_name, WEB_WEIGHTS_DIR)
    print(f"\nAll weights exported to {WEB_WEIGHTS_DIR}")
