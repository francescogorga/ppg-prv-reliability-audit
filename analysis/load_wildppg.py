"""WildPPG (Meier, Demirel, Holz, NeurIPS 2024 D&B; data CC BY-NC-SA 4.0).

Raw participant files (.mat, MATLAB 5) contain, per body location, channels with
fields v (values) and fs. Used here, all at 128 Hz:
  head/ppg_ir  reflective PPG 950 nm (MAX86141), value = fraction of ADC full scale (has DC)
  head/ppg_g   reflective PPG 530 nm (robustness check)
  head/acc_*   accelerometer, g
  sternum/ecg  Lead-I ECG (int), reference for beat timing

usage: python load_wildppg.py extract <raw.mat> <out.npz>
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.io

DATA = Path(__file__).resolve().parent / "data" / "wildppg"

# The app's SQI has one absolute threshold (DC >= 10 nA, "sensor on skin"). WildPPG
# stores PPG as a fraction of the ADC full scale and the MAX86141 range setting is not
# stated, so values are scaled by 4096 (the glasses' MAX30101 range, nA). With this
# factor the presence check triggers below 0.24% of full scale. Every other SQI term
# and all timing are scale-free.
FRACTION_TO_NA = 4096.0


def _channels(mat, loc):
    s = mat[loc][0]
    out = {}
    for name, sd in zip(s.dtype.names, s[0]):
        f = sd[0][0]
        fields = dict(zip(f.dtype.names, f))
        out[name] = (np.asarray(fields["v"]).squeeze(), float(np.asarray(fields["fs"]).squeeze()))
    return out


def extract(raw: Path, out: Path):
    mat = scipy.io.loadmat(raw)
    head, stern = _channels(mat, "head"), _channels(mat, "sternum")
    fs = {head[k][1] for k in ("ppg_ir", "ppg_g", "acc_x")} | {stern["ecg"][1]}
    assert fs == {128.0}, fs
    n = len(stern["ecg"][0])
    assert all(len(head[k][0]) == n for k in ("ppg_ir", "ppg_g", "acc_x", "acc_y", "acc_z"))
    np.savez_compressed(
        out, id=str(mat["id"][0]), notes=str(mat["notes"][0]) if len(mat["notes"]) else "",
        fs=128.0,
        ppg_ir=head["ppg_ir"][0].astype(np.float64), ppg_g=head["ppg_g"][0].astype(np.float64),
        acc=np.stack([head[k][0] for k in ("acc_x", "acc_y", "acc_z")]).astype(np.float32),
        ecg=stern["ecg"][0].astype(np.int32),
    )


@dataclass
class Participant:
    pid: str
    fs: float
    ir: np.ndarray      # nA-equivalent (see FRACTION_TO_NA)
    green: np.ndarray
    acc_mag: np.ndarray
    ecg: np.ndarray
    n_nan_ppg: int


def participants() -> list[str]:
    ids = sorted(p.stem for p in DATA.glob("*.npz"))
    if not ids:
        raise FileNotFoundError(f"No extracted WildPPG data in {DATA}; run download_wildppg.sh all")
    return ids


def load(pid: str) -> Participant:
    z = np.load(DATA / f"{pid}.npz")

    def fill(v):
        v = v.astype(float)
        bad = ~np.isfinite(v)
        if bad.any():
            v[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), v[~bad])
        return v

    n_nan = int((~np.isfinite(z["ppg_ir"])).sum())
    acc = z["acc"].astype(float)
    return Participant(pid=str(z["id"]), fs=float(z["fs"]),
                       ir=fill(z["ppg_ir"]) * FRACTION_TO_NA, green=fill(z["ppg_g"]) * FRACTION_TO_NA,
                       acc_mag=np.sqrt((acc ** 2).sum(axis=0)), ecg=z["ecg"].astype(float), n_nan_ppg=n_nan)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "extract":
        extract(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(__doc__)
