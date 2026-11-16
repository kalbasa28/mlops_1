from contextlib import asynccontextmanager
from typing import Literal

import mlflow.sklearn
import pandas as pd
from fastapi import FastAPI
from mlflow import MlflowClient
from pydantic import BaseModel, Field

from features import FEATURE_COLUMNS, TYPE_CODES

REGISTERED_MODEL_NAME = "predictive-maintenance"
ALIAS = "champion"


class MachineReading(BaseModel):
    type: Literal["L", "M", "H"]
    air_temperature_k: float = Field(gt=0)
    process_temperature_k: float = Field(gt=0)
    rotational_speed_rpm: float = Field(ge=0)
    torque_nm: float = Field(ge=0)
    tool_wear_min: float = Field(ge=0)

    def to_model_row(self) -> list:
        return [
            TYPE_CODES[self.type],
            self.air_temperature_k,
            self.process_temperature_k,
            self.rotational_speed_rpm,
            self.torque_nm,
            self.tool_wear_min,
        ]


class Prediction(BaseModel):
    failure: bool
    failure_probability: float
    model_version: str


serving = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    champion = MlflowClient().get_model_version_by_alias(REGISTERED_MODEL_NAME, ALIAS)
    serving["model"] = mlflow.sklearn.load_model(f"models:/{REGISTERED_MODEL_NAME}/{champion.version}")
    serving["version"] = champion.version
    print(f"Loaded {REGISTERED_MODEL_NAME}@{ALIAS} = version {champion.version} (run {champion.run_id})")
    yield
    serving.clear()


app = FastAPI(title="Predictive maintenance API", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": serving["version"]}


@app.post("/predict")
def predict(reading: MachineReading) -> Prediction:
    row = pd.DataFrame([reading.to_model_row()], columns=FEATURE_COLUMNS)
    probability = float(serving["model"].predict_proba(row)[0, 1])
    return Prediction(
        failure=probability > 0.5,
        failure_probability=probability,
        model_version=serving["version"],
    )
