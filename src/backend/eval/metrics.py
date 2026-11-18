"""분류 평가 지표. 순수 Python — 외부 의존성 없음."""

from typing import Any


def classification_metrics(
    predicted: dict[str, str], expected: dict[str, str]
) -> dict[str, Any]:
    """예측/정답 {repo: label} 딕셔너리를 비교해 지표를 반환한다.

    반환: accuracy, 레이블별 precision/recall/support, macro 평균, 샘플 수.
    """
    n = len(expected)
    if n == 0:
        return {"n": 0, "accuracy": 0.0, "per_label": {}, "macro_avg": {}}

    labels = sorted(set(predicted.values()) | set(expected.values()))
    correct = 0
    # label -> [tp, fp, fn]
    counts: dict[str, list[int]] = {label: [0, 0, 0] for label in labels}

    for repo, exp in expected.items():
        pred = predicted.get(repo)
        if pred == exp:
            correct += 1
        for label in labels:
            tp = int(pred == label and exp == label)
            fp = int(pred == label and exp != label)
            fn = int(pred != label and exp == label)
            counts[label][0] += tp
            counts[label][1] += fp
            counts[label][2] += fn

    per_label: dict[str, dict[str, float]] = {}
    for label, (tp, fp, fn) in counts.items():
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "support": int(tp + fn),
        }

    macro_precision = (
        sum(v["precision"] for v in per_label.values()) / len(per_label)
        if per_label
        else 0.0
    )
    macro_recall = (
        sum(v["recall"] for v in per_label.values()) / len(per_label)
        if per_label
        else 0.0
    )

    return {
        "n": n,
        "accuracy": round(correct / n, 4),
        "per_label": per_label,
        "macro_avg": {
            "precision": round(macro_precision, 4),
            "recall": round(macro_recall, 4),
        },
    }
