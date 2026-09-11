from decimal import Decimal
import json

import numpy as np
import pytest

from q1.export import rounded,rounded_array,verified_source


def test_half_up_is_shared_and_not_binary_bankers_rounding():
    assert rounded(1.23445) == Decimal("1.2345")
    assert rounded(-1.23445) == Decimal("-1.2345")
    assert np.array_equal(rounded_array([[1.23445,2.55555]]),[[1.2345,2.5556]])


def test_unverified_results_cannot_be_exported(tmp_path):
    (tmp_path/"verification.json").write_text(json.dumps({"numerical_passed":False}))
    with pytest.raises(ValueError,match="validation"):
        verified_source(tmp_path)
