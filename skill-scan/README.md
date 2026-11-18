# skill-scan — 일일 스킬 디스커버리

GitHub에서 AI 에이전트(Claude/Codex/Devin)용 스킬·플러그인을 분야별로
검색해 `skills/`에 번들링하고 `reports/{날짜}/`에 한국어 다이제스트를 남긴다.

## 파일

- `prompts/ORCHESTRATOR.md` — 헤드 에이전트 프롬프트 (분야 팬아웃 → 검증 → 랭킹 → install manifest)
- `prompts/SUBAGENT.md` — 분야별 서브에이전트 프롬프트 템플릿
- `run_daily.sh` — `devin -p` 비대화형 실행 래퍼 (로그: `logs/scan-YYYY-MM-DD.log`)
- `install_schedule.sh` — macOS launchd에 매일 07:00(KST) 자동 실행 등록

## 수동 실행

```bash
./skill-scan/run_daily.sh
```

## 매일 자동 실행 등록 (macOS)

```bash
./skill-scan/install_schedule.sh          # 등록
./skill-scan/install_schedule.sh uninstall # 해제
```

비-macOS는 cron에 `0 22 * * * /path/to/repo/skill-scan/run_daily.sh` 추가
(22:00 UTC = 07:00 KST). `devin` CLI가 PATH에 있고 `devin auth login`이
되어 있어야 한다.

## 설치된 스킬 적용

생성된 `install.sh`는 실행하지 않는다. 확인 후:

```bash
./skill-scan/install.sh --dry-run   # 대상 확인
./skill-scan/install.sh all         # claude/codex/agents/devin-project 전체
./skill-scan/install.sh claude      # 특정 타겟만
```
