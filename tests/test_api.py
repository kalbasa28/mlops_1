import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import app, serving
from features import FEATURE_COLUMNS

VALID_READING = {
    "type": "M",
    "air_temperature_k": 298.1,
    "process_temperature_k": 308.6,
    "rotational_speed_rpm": 1551,
    "torque_nm": 42.8,
    "tool_wear_min": 0,
}


class AlwaysSeventyPercentModel:
    def predict_proba(self, rows):
        assert list(rows.columns) == FEATURE_COLUMNS
        return np.array([[0.3, 0.7]])


@pytest.fixture
def client():
    serving.update(model=AlwaysSeventyPercentModel(), version="42")
    yield TestClient(app)
    serving.clear()


def test_health_reports_served_version(client):
    assert client.get("/health").json() == {"status": "ok", "model_version": "42"}


def test_predict_returns_failure_probability_and_version(client):
    response = client.post("/predict", json=VALID_READING)
    assert response.status_code == 200
    assert response.json() == {"failure": True, "failure_probability": 0.7, "model_version": "42"}


@pytest.mark.parametrize(
    "bad_field",
    [{"type": "X"}, {"torque_nm": -1}, {"air_temperature_k": 0}, {"tool_wear_min": "a lot"}],
)
def test_predict_rejects_invalid_input(client, bad_field):
    assert client.post("/predict", json=VALID_READING | bad_field).status_code == 422


def test_predict_rejects_missing_field(client):
    reading = {k: v for k, v in VALID_READING.items() if k != "torque_nm"}
    assert client.post("/predict", json=reading).status_code == 422
