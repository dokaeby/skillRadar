#!/usr/bin/env bash
# SkillRadar skill-scan daily runner.
# Devin CLI 비대화형 모드로 오케스트레이터 프롬프트를 실행한다.
# 사용법: ./skill-scan/run_daily.sh   (launchd/cron에서 호출)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# .env에서 GITHUB_TOKEN 등을 로드 (있으면)
if [ -f .env ]; then
  set -a; source .env; set +a
fi

export TODAY="$(TZ=Asia/Seoul date +%F)"
mkdir -p "skill-scan/logs"
LOG="skill-scan/logs/scan-${TODAY}.log"

echo "[skill-scan] start ${TODAY} $(date -Is)" | tee -a "$LOG"

# 오케스트레이터 프롬프트를 실행일로 치환해 임시 파일로 만든 뒤 devin -p 실행
PROMPT_FILE="$(mktemp -t skillscan-prompt.XXXXXX.md)"
trap 'rm -f "$PROMPT_FILE"' EXIT
sed "s/{TODAY}/${TODAY}/g" skill-scan/prompts/ORCHESTRATOR.md > "$PROMPT_FILE"

if command -v devin >/dev/null 2>&1; then
  devin -p --respect-workspace-trust false --prompt-file "$PROMPT_FILE" 2>&1 | tee -a "$LOG"
else
  echo "[skill-scan] devin CLI not found — 프롬프트만 생성됨: $PROMPT_FILE" | tee -a "$LOG"
  exit 127
fi

echo "[skill-scan] done ${TODAY} $(date -Is)" | tee -a "$LOG"
