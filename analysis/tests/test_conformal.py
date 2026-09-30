"""Finite-sample calibration must include the augmented infinite score."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conformal import conformal_q


def test_small_calibration_cannot_give_finite_90pct_bound():
    assert np.isinf(conformal_q(np.arange(8.0)))
    assert conformal_q(np.arange(9.0)) == 8.0
    assert conformal_q(np.arange(19.0)) == 17.0


def test_empty_calibration_fails_explicitly():
    with pytest.raises(ValueError, match="at least one"):
        conformal_q([])
