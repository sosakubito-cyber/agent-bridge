# agent-bridge

Local stdio MCP bridge: lets a chat interface (Claude Desktop / claude.ai) delegate
planning and execution to a headless `claude` CLI subprocess, so plan → critique →
execute → diff-review doesn't require manual copy-paste between chat and terminal.

v0 scope: backend=`claude` only. Tools: `list_repos`, `plan`, `execute`, `get_diff`,
`status`, `usage_report`. See [SPEC.md](SPEC.md) for the full design and
[tools.schema.json](tools.schema.json) for the machine-readable tool contract.

## 実測記録

環境: `claude --version` → `2.1.201 (Claude Code)`(2026-07-07 時点)

`claude -p "say ok" --output-format json` の実測結果(整形・一部省略):

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "ok",
  "stop_reason": "end_turn",
  "session_id": "a3b58be9-3070-4f7d-8ee5-73fdd9a8794a",
  "total_cost_usd": 0.0874962,
  "usage": {
    "input_tokens": 4,
    "cache_creation_input_tokens": 10672,
    "cache_read_input_tokens": 56824,
    "output_tokens": 427
  },
  "modelUsage": { "claude-sonnet-5": { "costUSD": 0.0874962, "contextWindow": 1000000, "maxOutputTokens": 64000 } },
  "permission_denials": [
    { "tool_name": "Bash", "tool_input": { "command": "git pull", "description": "..." } }
  ],
  "terminal_reason": "completed"
}
```

**フィールド名 → `adapter.py` 対応表**(`src/agent_bridge/adapter.py` のプレースホルダ実装がそのまま実測と一致。コード変更は不要だった):

| bridge 側の意味 | 実測フィールド名 | 備考 |
|---|---|---|
| `result_text` | `result` | プレースホルダの `obj.get("result")` が的中 |
| `cost_usd` | `total_cost_usd`(`cost_usd` トップレベルは存在しない) | フォールバックチェーンが的中 |
| `backend_session_id` | `session_id` | 的中 |
| `usage` | `usage`(input/output/cache_creation/cache_read の4種) | そのまま採録可能 |

**運用上の注意(新規判明)**: `permission_denials` フィールドがトップレベルに存在し、
今回の実測ではユーザーの `~/.claude/CLAUDE.md`(全プロジェクト共通指示、
「セッション開始時にまず git pull」)に従ってサブプロセス側の `claude` が
`git pull` を自発的に試み、ヘッドレス実行(対話承認不可)のため拒否されていた。
**含意**: agent-bridge 経由の `plan`/`execute` 呼び出しでは、対象リポジトリ側の
グローバル/プロジェクト CLAUDE.md が指示する行動(git pull 等)が許可モード次第で
毎回 `permission_denials` に記録される可能性がある。v1 でこのフィールドを
`warnings[]` に転記するか検討(v0 では未反映、既存の `usage`/`session_id` 欠測時
warning ロジックのみ実装済み)。

コスト面: 単純な "say ok" でも $0.087(cache creation 10,672 tokens 込み)。
サブプロセスは対象リポジトリの CLAUDE.md 等をコンテキストに読み込むため、
トリビアルなタスクでも無視できないコストが発生する点に注意。
