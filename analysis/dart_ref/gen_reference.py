"""Writes synthetic inputs and runs the ORIGINAL Dart classes on them (dart_ref/ref.dart).

Outputs go to dart_ref/out/. Run from analysis/:  .venv/bin/python dart_ref/gen_reference.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from synthetic import make_cases  # noqa: E402

GATES = ["0.4", "none"]


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    for name, (fs, raw, _bt, _rr) in make_cases().items():
        inp = out / f"{name}_input.csv"
        inp.write_text("\n".join(repr(float(v)) for v in raw) + "\n")
        for g in GATES:
            prefix = out / f"{name}_gate{g}"
            subprocess.run(["dart", "run", str(HERE / "ref.dart"), str(inp), str(prefix), str(fs), g],
                           check=True, cwd=HERE)
            print("ok", prefix.name)


if __name__ == "__main__":
    main()
