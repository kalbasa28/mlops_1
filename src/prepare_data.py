import os

import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

RAW = "data/raw/ai4i2020.csv"
PARAMS_FILE = "params.yaml"
OUT_DIR = "data/processed"
TARGET = "Machine failure"
ID_COLUMNS = ["UDI", "Product ID"]
TARGET_LEAKING_FAILURE_MODES = ["TWF", "HDF", "PWF", "OSF", "RNF"]
TYPE_CODES = {"L": 0, "M": 1, "H": 2}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=ID_COLUMNS + TARGET_LEAKING_FAILURE_MODES)
    return df.assign(Type=df["Type"].map(TYPE_CODES))


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
