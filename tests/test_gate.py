from gate import gate_failures

GATE = {"min_recall": 0.70, "min_precision": 0.30}


def test_good_model_passes():
    assert gate_failures({"recall": 0.85, "precision": 0.41}, GATE) == []


def test_threshold_itself_passes():
    assert gate_failures({"recall": 0.70, "precision": 0.30}, GATE) == []


def test_low_recall_fails():
    assert gate_failures({"recall": 0.21, "precision": 0.93}, GATE) == ["recall = 0.21 (minimum 0.7)"]


def test_low_precision_fails():
    assert gate_failures({"recall": 0.72, "precision": 0.17}, GATE) == ["precision = 0.17 (minimum 0.3)"]


def test_missing_metric_fails():
    assert len(gate_failures({"recall": 0.85}, GATE)) == 1
