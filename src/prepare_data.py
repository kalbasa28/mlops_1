"""Clean the raw AI4I data and split it into train/test sets.

Run: python src/prepare_data.py
Reads data/raw/ai4i2020.csv and params.yaml (section `prepare`),
writes data/processed/train.csv and data/processed/test.csv.
"""
import os

import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

RAW = "data/raw/ai4i2020.csv"
PARAMS_FILE = "params.yaml"
OUT_DIR = "data/processed"
TARGET = "Machine failure"
DROP = ["UDI", "Product ID", "TWF", "HDF", "PWF", "OSF", "RNF"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with only model-ready columns: numeric features + TARGET."""
    df_dropped = df.drop(columns=DROP)
    df_clean = df_dropped.assign(Type=df_dropped["Type"]
                                 .map({"L": 0, "M": 1, "H": 2}))
    return df_clean



def main() -> None:
    with open(PARAMS_FILE) as f:
        params = yaml.safe_load(f)["prepare"]

    df = clean(pd.read_csv(RAW))

    # Stratify on the target: with only ~3.4% failures, a plain random split
    # could put noticeably more or fewer failures into the test set.
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
