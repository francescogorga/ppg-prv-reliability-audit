"""Loader for the PhysioNet Pulse Transit Time PPG Dataset v1.1.0 (WFDB format).

Channels used (from the dataset description):
  pleth_1 = IR, sensor 1 (MAX30101)   <- main input, same chip/channel as the glasses
  pleth_4 = IR, sensor 2 (MAX30101)   <- robustness check
  ecg     = 3-lead ECG (AD8232); R peaks from .atr (automatic + manually verified)
  a_x/a_y/a_z = accelerometer (MPU-9250), g
All channels at 500 Hz.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import wfdb
from scipy import signal

DATA = Path(__file__).resolve().parent / "data" / "ptt_ppg"

# MAX30101 with ADC range 16384 nA and 18-bit samples: 16384 / 2**18 = 0.0625 nA per count.
# Only the SQI presence check (DC < 10 nA) depends on absolute units; every other
# quantity in the pipeline is a ratio or a timing, so this factor does not affect them.
COUNTS_TO_NA = 16384 / 2**18


@dataclass
class Record:
    name: str
    subject: int
    activity: str
    fs: float
    ir1: np.ndarray        # nA
    ir2: np.ndarray        # nA
    acc_mag: np.ndarray    # g
    r_peaks_s: np.ndarray  # seconds
    n_nan: int


def records() -> list[str]:
    return (DATA / "RECORDS").read_text().split()


def load(name: str) -> Record:
    rec = wfdb.rdrecord(str(DATA / name))
    ann = wfdb.rdann(str(DATA / name), "atr")
    idx = {n: i for i, n in enumerate(rec.sig_name)}
    x = rec.p_signal
    n_nan = int(np.isnan(x[:, [idx["pleth_1"], idx["pleth_4"]]]).sum())

    def clean(v):
        v = v.astype(float)
        if np.isnan(v).any():  # linear interpolation over isolated invalid samples
            good = ~np.isnan(v)
            v[~good] = np.interp(np.flatnonzero(~good), np.flatnonzero(good), v[good])
        return v

    acc = np.sqrt(sum(clean(x[:, idx[k]]) ** 2 for k in ("a_x", "a_y", "a_z")))
    subj, act = name.split("_")
    beats = ann.sample[np.isin(ann.symbol, ["N"])] / rec.fs
    return Record(name=name, subject=int(subj[1:]), activity=act, fs=float(rec.fs),
                  ir1=clean(x[:, idx["pleth_1"]]) * COUNTS_TO_NA,
                  ir2=clean(x[:, idx["pleth_4"]]) * COUNTS_TO_NA,
                  acc_mag=acc, r_peaks_s=beats, n_nan=n_nan)


def resample(x: np.ndarray, fs_in: float, fs_out: float) -> np.ndarray:
    """Anti-aliased integer decimation (500 -> 100 Hz), zero-phase FIR; DC preserved."""
    q = int(round(fs_in / fs_out))
    assert abs(fs_in / q - fs_out) < 1e-9, "only integer factors supported"
    return signal.decimate(x, q, ftype="fir", zero_phase=True)
