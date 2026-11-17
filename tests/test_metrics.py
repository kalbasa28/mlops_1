import pytest

from metrics import compute_metrics


def test_perfect_predictions_score_one():
    assert compute_metrics([0, 1, 0, 1], [0, 1, 0, 1]) == {"accuracy": 1.0, "precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_metrics_are_for_the_failure_class():
    metrics = compute_metrics(y_true=[0, 0, 1, 1], y_pred=[0, 1, 1, 0])
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)


def test_missing_every_failure_gives_zero_recall_despite_high_accuracy():
    metrics = compute_metrics(y_true=[0] * 9 + [1], y_pred=[0] * 10)
    assert metrics["accuracy"] == pytest.approx(0.9)
    assert metrics["recall"] == 0.0
