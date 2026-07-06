# agent-bridge

Local stdio MCP bridge: lets a chat interface (Claude Desktop / claude.ai) delegate
planning and execution to a headless `claude` CLI subprocess, so plan → critique →
execute → diff-review doesn't require manual copy-paste between chat and terminal.

v0 scope: backend=`claude` only. Tools: `list_repos`, `plan`, `execute`, `get_diff`,
`status`, `usage_report`. See [SPEC.md](SPEC.md) for the full design and
[tools.schema.json](tools.schema.json) for the machine-readable tool contract.

## 運用注意

MCPサーバーはDesktop起動時に立ち上がる常駐プロセスであり、コード変更はホットリロード
されない。修正後は必ず Cmd+Q でDesktopを完全再起動すること。反映確認は `list_repos`
の `bridge_build`(実行中プロセスが起動したコミットの短縮SHA、取得失敗時は `"unknown"`)
と `started_at`(プロセス起動時刻)で行う — 期待するコミットと一致しなければ、
再起動がまだ反映されていないか、別プロセスが動いている。

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

## 既知の不具合と修正: `list_repos` 等の tools/call が Desktop 側で無応答(2026-07-07)

**症状**: Claude Desktop への MCP 登録・ハンドシェイク(`initialize`/`tools/list`)は成功するが、
`list_repos` を呼ぶと Desktop 側で約4分後に「No result received」のタイムアウトになる。

**切り分け**(いずれも正常と確認済み。詳細は git 履歴のコミットメッセージ参照):
- `~/Library/Logs/Claude/mcp-server-agent-bridge.log` では `tools/call` 受信から
  12ms で `result(1 blocks)` を返しており、agent-bridge プロセス自体は高速に応答していた。
- `list_repos.handle()` は fcntl ロックや I/O を一切持たず、直接呼び出しでも 0.5ms で返る。
- 上記から、agent-bridge の外(Desktop 側のレンダリング/上位ハンドリング層)で
  結果が失われている可能性が濃厚と判断した。

**根本原因**: `src/agent_bridge/server.py` の `_call_tool` が、成功時・エラー時ともに
結果を `list[types.TextContent]`(テキスト1本に JSON を詰めた形)としてのみ返しており、
MCP の `CallToolResult.structuredContent` を一度も設定していなかった。エラーも
`isError` をテキスト内の JSON に埋め込むだけで、プロトコルレベルの
`CallToolResult.isError` は常に `False`(未設定)のままだった。インストール済み
`mcp` SDK(1.28.1、`pyproject.toml` は `mcp>=1.2.0` としか固定していなかった)は
`structuredContent` を伴う応答を前提にした最近の MCP 仕様に沿っており、
Desktop 側がこれに依存してハングしていたと推測される。

**修正**: `_call_tool` が `types.CallToolResult` を直接返すように変更。
成功時は `content`(従来通りの JSON テキスト、後方互換)に加えて
`structuredContent=result`、`isError=False` を明示。エラー時(`BridgeError` /
未知ツール)は `isError=True` をプロトコルレベルで設定するよう変更した
(`errors.py` の `to_tool_result()` は不要になったため削除)。

**検証**: `server.py` の `_call_tool`(MCP ハンドラそのもの)には従来テストが
一切無かったため `tests/test_server.py` を新設し、成功時の `structuredContent`/
`isError=False`、未知ツール・`BridgeError` 双方での `isError=True` を回帰テスト化。
`uv run python -c` で `build_server(...)` 経由の実呼び出しを行い、
`structuredContent` が正しく載ること・エラー系で `isError=True` になることを
直接確認済み(pytest 49件全パス)。
