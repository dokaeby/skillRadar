# Eval baseline — 2026-11-18

- 생성 시각: 2026-11-18T16:46:59+09:00
- 샘플 수: 10
- accuracy: 1.0

| repo | expected | predicted | confidence | ok | note |
|---|---|---|---|---|---|
| anthropics/skills | skills | skills | 1.00 | Y | Anthropic 공식 Agent Skills 모음 |
| modelcontextprotocol/servers | mcp | mcp | 1.00 | Y | MCP 레퍼런스 서버 모음 |
| microsoft/playwright-mcp | mcp | mcp | 1.00 | Y | Playwright MCP 서버 |
| browser-use/browser-use | agents | agents | 0.99 | Y | LLM 기반 브라우저 자동화 에이전트 |
| microsoft/autogen | agents | agents | 1.00 | Y | 다중 에이전트 대화 프레임워크 |
| microsoft/vscode | devtools | devtools | 0.95 | Y | 코드 에디터 — AI 도구 생태계의 기반 |
| obsidianmd/obsidian-sample-plugin | plugins | plugins | 0.95 | Y | Obsidian 플러그인 샘플 |
| puppeteer/puppeteer | automation | automation | 0.95 | Y | 헤드리스 브라우저 자동화 |
| huggingface/datasets | data | data | 0.99 | Y | 데이터셋 로딩/처리 라이브러리 |
| sindresorhus/awesome | other | other | 0.95 | Y | 큐레이션 목록 — AI 툴링 경계 사례 |

## metrics

```json
{
  "n": 10,
  "accuracy": 1.0,
  "per_label": {
    "agents": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 2
    },
    "automation": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 1
    },
    "data": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 1
    },
    "devtools": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 1
    },
    "mcp": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 2
    },
    "other": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 1
    },
    "plugins": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 1
    },
    "skills": {
      "precision": 1.0,
      "recall": 1.0,
      "support": 1
    }
  },
  "macro_avg": {
    "precision": 1.0,
    "recall": 1.0
  }
}
```
