import pandas as pd

from features import FEATURE_COLUMNS
from prepare_data import TARGET, TARGET_LEAKING_FAILURE_MODES, clean


def raw_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "UDI": [1, 2, 3],
            "Product ID": ["L1", "M2", "H3"],
            "Type": ["L", "M", "H"],
            "Air temperature [K]": [298.1, 298.2, 298.3],
            "Process temperature [K]": [308.6, 308.7, 308.8],
            "Rotational speed [rpm]": [1551, 1408, 1498],
            "Torque [Nm]": [42.8, 46.3, 49.4],
            "Tool wear [min]": [0, 3, 5],
            "Machine failure": [0, 1, 0],
            "TWF": [0, 1, 0],
            "HDF": [0, 0, 0],
            "PWF": [0, 0, 0],
            "OSF": [0, 0, 0],
            "RNF": [0, 0, 0],
        }
    )


def test_clean_keeps_only_features_and_target_in_order():
    assert list(clean(raw_rows()).columns) == FEATURE_COLUMNS + [TARGET]


def test_clean_drops_columns_that_leak_the_target():
    cleaned = clean(raw_rows())
    assert not set(TARGET_LEAKING_FAILURE_MODES) & set(cleaned.columns)


def test_clean_encodes_type_as_integers():
    assert clean(raw_rows())["Type"].tolist() == [0, 1, 2]


def test_clean_keeps_every_row():
    assert len(clean(raw_rows())) == 3
