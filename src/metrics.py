"""Metrics shared by train.py and evaluate.py, so both always compute them the same way."""
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def compute_metrics(y_true, y_pred) -> dict[str, float]:
    """Return accuracy, precision, recall and f1 for the positive class (Machine failure = 1)."""
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred)
    recall = recall_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)

    metrics = {"accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1}
    return metrics