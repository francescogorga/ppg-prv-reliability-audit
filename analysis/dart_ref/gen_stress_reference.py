"""Writes the synthetic 1 Hz stress inputs and runs the app's original StressDetector on them."""
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tests"))
from test_stress import cases  # noqa: E402

out = HERE / "out"
out.mkdir(exist_ok=True)
for name, (hr, hrv, gate) in cases().items():
    inp = out / f"stress_{name}_in.csv"
    inp.write_text("\n".join(f"{'' if np.isnan(h) else repr(float(h))},{repr(float(v))},{int(g)}" for h, v, g in zip(hr, hrv, gate)) + "\n")
    subprocess.run(["dart", "run", str(HERE / "stress_ref.dart"), str(inp), str(out / f"stress_{name}_out.csv")], check=True, cwd=HERE)
    print("ok", name)
