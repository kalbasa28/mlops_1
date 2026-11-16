import os

import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

from features import FEATURE_COLUMNS, TYPE_CODES

RAW = "data/raw/ai4i2020.csv"
PARAMS_FILE = os.environ.get("PARAMS_FILE", "params.yaml")
OUT_DIR = "data/processed"
TARGET = "Machine failure"
ID_COLUMNS = ["UDI", "Product ID"]
TARGET_LEAKING_FAILURE_MODES = ["TWF", "HDF", "PWF", "OSF", "RNF"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=ID_COLUMNS + TARGET_LEAKING_FAILURE_MODES)
    df = df.assign(Type=df["Type"].map(TYPE_CODES))
    return df[FEATURE_COLUMNS + [TARGET]]


def main() -> None:
    with open(PARAMS_FILE) as f:
        params = yaml.safe_load(f)["prepare"]

    df = clean(pd.read_csv(RAW))
    train, test = train_test_split(
        df,
        test_size=params["test_size"],
        random_state=params["random_seed"],
        stratify=df[TARGET],
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    train.to_csv(f"{OUT_DIR}/train.csv", index=False)
    test.to_csv(f"{OUT_DIR}/test.csv", index=False)
    print(f"Train: {len(train)} rows ({train[TARGET].sum()} failures)")
    print(f"Test:  {len(test)} rows ({test[TARGET].sum()} failures)")


if __name__ == "__main__":
    main()
