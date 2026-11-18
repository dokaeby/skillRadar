"""eval.metrics 분류 지표 테스트."""

from backend.eval.metrics import classification_metrics


def test_perfect_predictions() -> None:
    expected = {"a/x": "agents", "b/y": "mcp"}
    predicted = {"a/x": "agents", "b/y": "mcp"}
    m = classification_metrics(predicted, expected)
    assert m["n"] == 2
    assert m["accuracy"] == 1.0
    assert m["macro_avg"]["precision"] == 1.0
    assert m["macro_avg"]["recall"] == 1.0
    assert m["per_label"]["agents"]["support"] == 1


def test_partial_predictions_precision_recall() -> None:
    expected = {"a": "agents", "b": "agents", "c": "mcp", "d": "skills"}
    predicted = {"a": "agents", "b": "mcp", "c": "mcp", "d": "other"}
    m = classification_metrics(predicted, expected)
    assert m["accuracy"] == 0.5  # a, c 정답

    agents = m["per_label"]["agents"]
    # tp=1 (a), fp=0, fn=1 (b를 mcp로 예측) → precision 1.0, recall 0.5
    assert agents["precision"] == 1.0
    assert agents["recall"] == 0.5
    assert agents["support"] == 2

    mcp = m["per_label"]["mcp"]
    # tp=1 (c), fp=1 (b), fn=0 → precision 0.5, recall 1.0
    assert mcp["precision"] == 0.5
    assert mcp["recall"] == 1.0

    skills = m["per_label"]["skills"]
    # 정답 1개를 other로 예측 → tp=0, fn=1 → recall 0.0
    assert skills["recall"] == 0.0
    assert skills["support"] == 1

    # macro avg: precision (1.0 + 0.5 + 0.0 + 1.0(other? pred 'other'만 존재)) 계산 확인
    # 라벨 집합: agents, mcp, skills, other
    # other: tp=0, fp=1(d), fn=0 → precision 0.0, recall 0.0 (support 0)
    precisions = [v["precision"] for v in m["per_label"].values()]
    recalls = [v["recall"] for v in m["per_label"].values()]
    assert m["macro_avg"]["precision"] == round(sum(precisions) / len(precisions), 4)
    assert m["macro_avg"]["recall"] == round(sum(recalls) / len(recalls), 4)


def test_missing_prediction_treated_as_wrong() -> None:
    expected = {"a": "agents", "b": "mcp"}
    predicted = {"a": "agents"}  # b 누락
    m = classification_metrics(predicted, expected)
    assert m["accuracy"] == 0.5
    assert m["per_label"]["mcp"]["recall"] == 0.0


def test_empty_expected() -> None:
    m = classification_metrics({}, {})
    assert m["n"] == 0
    assert m["accuracy"] == 0.0
