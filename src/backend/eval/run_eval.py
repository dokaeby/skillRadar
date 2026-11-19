"""골든 데이터셋 분류 평가 CLI + CI 회귀 게이트.

사용법:
  python -m backend.eval.run_eval                  평가 실행 + 리포트 기록
  python -m backend.eval.run_eval --check          baseline 대비 회귀 검사 (CI 게이트)
  python -m backend.eval.run_eval --update-baseline baseline.json 갱신
- dataset.json의 각 repo에 대해 GitHub README를 가져와 classify_repo로 분류하고
  expected_label과 비교해 정확도/precision/recall을 출력한다.
- 결과는 docs/experiments/{오늘}-eval-baseline.md에 기록한다.
- --check는 docs/experiments/baseline.json의 accuracy보다 낮으면 exit 1.
- LLM_API_KEY가 없으면 메시지를 출력하고 0으로 종료한다.
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from backend.config import Settings
from backend.eval.metrics import classification_metrics
from backend.github_client import GitHubClient, today_kst
from backend.llm_tasks import classify_repo

logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"
REPORT_DIR = Path(__file__).resolve().parents[3] / "docs" / "experiments"
BASELINE_PATH = REPORT_DIR / "baseline.json"
REPO_URL = "https://api.github.com/repos/{full_name}"


async def _fetch_repo_meta(
    client: httpx.AsyncClient, full_name: str, token: str
) -> tuple[str | None, list[str]]:
    """저장소 메타데이터(description, topics)를 가져온다. 실패 시 (None, []).

    입력:
      - client: httpx.AsyncClient
      - full_name: str
      - token: str
    출력: tuple[str | None, list[str]]
    결과: 없음 (GitHub API 읽기)
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = await client.get(REPO_URL.format(full_name=full_name), headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - 평가 항목별 예외 격리
        logger.warning("repo 메타데이터 조회 실패 %s: %s", full_name, exc)
        return None, []
    return data.get("description"), list(data.get("topics") or [])


async def run(settings: Settings) -> tuple[dict[str, str], list[dict], dict]:
    """데이터셋 전체를 평가하고 (predicted, rows, metrics)를 반환한다.

    입력:
      - settings: Settings
    출력: tuple[dict[str, str], list[dict], dict]
    결과: 데이터셋 전체 분류 평가. LLM/GitHub API 호출 발생
    """
    token = settings.github_token.get_secret_value()
    api_key = settings.llm_api_key.get_secret_value()
    entries = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    gh = GitHubClient(token=token)
    predicted: dict[str, str] = {}
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as meta_client:
            for entry in entries:
                full_name = entry["repo"]
                description, topics = await _fetch_repo_meta(
                    meta_client, full_name, token
                )
                readme = await gh.fetch_readme(full_name)
                result = await classify_repo(
                    description=description,
                    readme=readme,
                    name=full_name,
                    topics=topics,
                    api_key=api_key,
                    base_url=settings.llm_base_url,
                    model=settings.judge_model,
                )
                predicted[full_name] = result.label
                rows.append(
                    {
                        "repo": full_name,
                        "expected": entry["expected_label"],
                        "predicted": result.label,
                        "confidence": result.confidence,
                        "ok": result.label == entry["expected_label"],
                        "note": entry.get("note", ""),
                    }
                )
                logger.info(
                    "%s: expected=%s predicted=%s", full_name, entry["expected_label"], result.label
                )
    finally:
        await gh.aclose()

    expected = {e["repo"]: e["expected_label"] for e in entries}
    return predicted, rows, classification_metrics(predicted, expected)


def write_report(rows: list[dict], metrics: dict) -> Path:
    """평가 결과를 docs/experiments/{date}-eval-baseline.md에 기록한다.

    입력:
      - rows: list[dict]
      - metrics: dict
    출력: Path
    결과: 평가 리포트 md 파일을 docs/experiments/에 생성
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    path = REPORT_DIR / f"{today_kst()}-eval-baseline.md"
    lines = [
        f"# Eval baseline — {today_kst()}",
        "",
        f"- 생성 시각: {stamp}",
        f"- 샘플 수: {metrics.get('n', 0)}",
        f"- accuracy: {metrics.get('accuracy', 0.0)}",
        "",
        "| repo | expected | predicted | confidence | ok | note |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['repo']} | {row['expected']} | {row['predicted']} "
            f"| {row['confidence']:.2f} | {'Y' if row['ok'] else 'N'} | {row['note']} |"
        )
    lines += [
        "",
        "## metrics",
        "",
        "```json",
        json.dumps(metrics, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def check_baseline(metrics: dict, tolerance: float = 0.0) -> int:
    """측정 지표가 baseline.json 대비 회귀했는지 검사한다.

    입력:
      - metrics: dict — classification_metrics 결과
      - tolerance: float — 허용 하락폭 (기본 0.0 = 회귀 불허)
    출력: int — 통과 0, 실패 1, baseline 없음 0(스킵)
    결과: baseline.json 없으면 경고 후 스킵. accuracy 비교만 수행
    """
    if not BASELINE_PATH.exists():
        print(f"baseline 없음 ({BASELINE_PATH}) — 게이트 스킵")
        return 0
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    base_acc = float(baseline.get("accuracy", 0.0))
    acc = float(metrics.get("accuracy", 0.0))
    threshold = base_acc - tolerance
    print(f"accuracy: {acc:.4f} (baseline {base_acc:.4f}, threshold {threshold:.4f})")
    if acc < threshold:
        print(f"회귀 감지: {acc:.4f} < {threshold:.4f} — 평가 기준 미달")
        return 1
    print("게이트 통과")
    return 0


def update_baseline(metrics: dict, rows: list[dict]) -> Path:
    """현재 측정값을 baseline.json으로 저장한다.

    입력:
      - metrics: dict — classification_metrics 결과
      - rows: list[dict] — repo별 예측 상세
    출력: Path — 작성된 baseline.json 경로
    결과: baseline.json 생성/덮어쓰기
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "accuracy": metrics.get("accuracy", 0.0),
        "n": metrics.get("n", 0),
        "macro_avg": metrics.get("macro_avg", {}),
        "measured_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "rows": [
            {"repo": r["repo"], "expected": r["expected"], "predicted": r["predicted"]}
            for r in rows
        ],
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return BASELINE_PATH


async def main() -> int:
    """

    입력:
      - 없음
    출력: int
    결과: 평가 실행 + 리포트 출력. 종료 코드 반환
    """
    parser = argparse.ArgumentParser(description="골든 데이터셋 분류 평가")
    parser.add_argument("--check", action="store_true", help="baseline 대비 회귀 검사")
    parser.add_argument("--update-baseline", action="store_true", help="baseline.json 갱신")
    parser.add_argument("--tolerance", type=float, default=0.0, help="허용 accuracy 하락폭")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings()
    if not settings.llm_enabled:
        print("LLM_API_KEY가 설정되지 않아 평가를 건너뜁니다.")
        return 0
    _, rows, metrics = await run(settings)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    path = write_report(rows, metrics)
    print(f"리포트 작성: {path}")
    if args.update_baseline:
        bp = update_baseline(metrics, rows)
        print(f"baseline 갱신: {bp}")
        return 0
    if args.check:
        return check_baseline(metrics, tolerance=args.tolerance)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
