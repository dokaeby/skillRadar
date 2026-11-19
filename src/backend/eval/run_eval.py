"""골든 데이터셋 분류 평가 CLI.

사용법: python -m backend.eval.run_eval
- dataset.json의 각 repo에 대해 GitHub README를 가져와 classify_repo로 분류하고
  expected_label과 비교해 정확도/precision/recall을 출력한다.
- 결과는 docs/experiments/{오늘}-eval-baseline.md에 기록한다.
- LLM_API_KEY가 없으면 메시지를 출력하고 0으로 종료한다.
"""

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


async def main() -> int:
    """

    입력:
      - 없음
    출력: int
    결과: 평가 실행 + 리포트 출력. 종료 코드 반환
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings()
    if not settings.llm_enabled:
        print("LLM_API_KEY가 설정되지 않아 평가를 건너뜁니다.")
        return 0
    _, rows, metrics = await run(settings)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    path = write_report(rows, metrics)
    print(f"리포트 작성: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
