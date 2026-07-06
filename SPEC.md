# agent-bridge SPEC v0.4(v0.3 + 2026-07-06 追補 A0–A5 統合)

チャット(Claude Desktop / claude.ai)を司令塔に、ローカルのヘッドレスエージェント
(**Claude Code** / **Cursor CLI**)へ計画立案・実行を委譲するための
**ローカル stdio MCP サーバー**の仕様書。

- 配置先: **独立プライベートリポジトリ** `agent-bridge`(Mac: `~/Projects/Shibehasu/agent-bridge`)。
  GitHub: `sosakubito-cyber/agent-bridge`(private)。配置場所の決定理由は §11 A0 参照。
- 本書の位置づけ: 実装の正典(SPEC駆動)。実装は Claude Code に委譲する(§9)。
- 対応ワークフロー: 案B(チャット⇔ヘッドレスの対話運用)。案C(自動オーケストレータ)は
  本サーバーの関数を再利用する前提で設計する。

---

## 0. 目的と非目的

**目的**
1. 「チャットで戦略 → Claude Code で計画 → チャットで批評 → 実行」の手動コピペを排除する。
2. 実行バックエンドを呼び出しごとに `claude | cursor` から選択可能にする(課金経路の分離を含む)。
3. モデルを呼び出しごとに明示指定可能にする(既定: `claude-sonnet-5`)。
4. トークン/コストを毎回計測・記録し、7/8 以降の従量課金を可視化する。

**非目的**
- クラウド公開(リモートMCP化)はしない。**ローカル stdio 限定**。トンネル・認証は扱わない。
- `git push` の自動化はしない(§5)。push は常に人間承認後、エージェント側の責務。
- チャットUIの再実装はしない。人間承認ゲートは「チャット上の会話」そのものとする。

---

## 1. 全体構成

```
Claude Desktop (チャット: Sonnet 5 / Opus 4.8 / 要所で Fable 5)
        │  MCP (stdio)
        ▼
  agent-bridge (Python, MCP server)
        │  subprocess
        ├── backend=claude → `claude -p ...`   (Claude Code headless)
        └── backend=cursor → `agent -p ...`    (Cursor CLI headless、v1)
                │
                ▼
        対象リポジトリ (config の allowlist に登録済みのみ)
                │
        session registry / usage log (~/.agent-bridge/)
```

- 言語/ランタイム: Python 3.11+、公式 `mcp` SDK(stdio server)。パッケージ管理は `uv`。
- 1ツール呼び出し = 1サブプロセス。バックエンド側のセッション継続は
  `claude --resume` / `cursor-agent --resume` に委譲する。

---

## 2. 前提・依存

| 依存 | 要件 | 備考 |
|---|---|---|
| Claude Code | v2.1.170+ (Fable指定時) | `claude -p --output-format json` が session_id / usage を返すこと(フィールド名は実装時に実測。実測結果は README.md に記録) |
| Cursor CLI | 現行版 | `agent -p` は `--force` なしなら**読み取り専用(提案のみ)** = plan相当。`--output-format json`、`--resume` あり。`-p` と `--resume` の併用可否、モデル指定フラグ、JSON内のセッションID/トークン欄は**実装時に要実測(v1)** |
| Claude Desktop | MCP対応版 | `claude_desktop_config.json` に登録(§8) |

---

## 3. ツール定義

共通方針:
- すべての `repo` は **config に登録されたエイリアス**のみ受け付ける(生パス不可)。
- すべての応答に `bridge_session_id`, `backend`, `model`, `usage`, `cost_usd`(取得可能な場合),
  `duration_s`, `warnings[]`, **`next_step_hint`**(チャット側モデルへの次アクション指示文。A1)を含める。
- 長い標準出力は末尾 N KB に切り詰め、全文はログへ(§6)。

### 3.1 `list_repos`
登録済みリポジトリと既定設定を返す(チャットが正しい引数を組めるように)。

```json
{
  "name": "list_repos",
  "description": "利用可能なリポジトリのエイリアス一覧と既定バックエンド/モデルを返す",
  "inputSchema": { "type": "object", "properties": {}, "additionalProperties": false }
}
```

**出力例**
```json
{ "repos": [{"alias":"shibehasu-ops","path":"~/dev/shibehasu-ops","default_backend":"claude"}],
  "defaults": {"backend":"claude","model":{"claude":"claude-sonnet-5","cursor":"auto"}} }
```

### 3.2 `plan`
対象リポジトリの文脈で**計画のみ**を作らせる(ファイル変更なし)。

```json
{
  "name": "plan",
  "description": "指定リポジトリで実装計画を立案させる。ファイルは変更しない。戻り値の計画をチャットで批評し、承認後に execute へ渡す。戻り値の計画は必ずユーザーに提示し、批評・議論を経てから次に進むこと。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task":    { "type": "string", "description": "計画してほしいタスクの記述(背景・制約含む)" },
      "repo":    { "type": "string", "description": "list_repos が返すエイリアス" },
      "backend": { "type": "string", "enum": ["claude", "cursor"], "default": "claude" },
      "model":   { "type": "string", "description": "例: claude-sonnet-5 / claude-fable-5 / opus。省略時は config の既定" },
      "session_id": { "type": "string", "description": "既存プランへの修正指示時に指定(resume)" },
      "context": { "type": "string", "description": "チャット側での議論の要約など、追加で渡す文脈" },
      "confirm_sensitive_model": { "type": "boolean", "default": false, "description": "sensitive repo で model=claude-fable-5 を使う場合の明示的な二重確認フラグ(§5-8)。model 指定だけでは不足" }
    },
    "required": ["task", "repo"],
    "additionalProperties": false
  }
}
```

**バックエンド対応表**

| backend | 実行コマンド(骨子) |
|---|---|
| claude | `claude -p "<task+context>" --permission-mode plan --model <model> --output-format json` (cwd=repo、resume時は `--resume <sid>`) |
| cursor | `agent -p "<task+context>" --output-format json` (cwd=repo, `--force` なし=提案のみ。**v1 未実装**、v0では isError で拒否) |

**出力**: `{ plan_markdown, bridge_session_id, backend_session_id, usage, cost_usd, warnings[], next_step_hint }`
`next_step_hint` 固定文言: 「このプランをユーザーに提示し、『OK』『実行して』等の明示的な承認を得るまで execute を呼ばないこと」。

### 3.3 `execute`
チャット上で人間が承認した計画を実行する。

```json
{
  "name": "execute",
  "description": "承認済みの計画を実行する。呼び出し前に必ずユーザーの明示的な承認をチャットで得ること。ユーザーの明示的な承認発話(『OK』『実行して』等)を得るまで呼び出し禁止。実行後は必ず get_diff でレビューを提示すること。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "session_id": { "type": "string", "description": "plan が返した bridge_session_id" },
      "approved":   { "type": "boolean", "const": true, "description": "ユーザー承認済みであることの明示。true 以外は拒否" },
      "instructions": { "type": "string", "description": "承認時の修正条件・注意点(チャットでの議論の反映)" },
      "mode": { "type": "string", "enum": ["acceptEdits", "default"], "default": "acceptEdits",
                "description": "claude backend の --permission-mode。ヘッドレスでは対話承認不可のため acceptEdits を基本とする" },
      "use_worktree": { "type": "boolean", "default": true, "description": "git worktree を切って隔離実行する" },
      "timeout_min": { "type": "integer", "default": 30, "maximum": 120 }
    },
    "required": ["session_id", "approved"],
    "additionalProperties": false
  }
}
```

**バックエンド対応表**

| backend | 実行コマンド(骨子) |
|---|---|
| claude | `claude -p "<execute指示+instructions>" --resume <sid> --permission-mode acceptEdits --output-format json` |
| cursor | `agent -p "<execute指示+instructions>" --force --resume <chat-id> --output-format json`(v1 未実装) |

**プロンプト規約(サーバーが自動付加)**: 「コミットは Conventional Commits で作成してよいが、
**push は行わない**。完了時に変更ファイル一覧と要約を出力すること。」

**状態機械ガード**: 同一 `session_id` に対応する `plan` 成果物が存在しない場合は拒否
(`has_plan` フラグをセッションレジストリで管理。§4)。`orchestrate`(v2)経由のセッションも同様に扱う。

**出力**: `{ result_markdown, changed_files[], bridge_session_id, usage, cost_usd, exit_code, next_step_hint }`
`next_step_hint` 固定文言: 「get_diff で差分レビューを提示すること」。

### 3.4 `get_diff`
実行結果をチャットでレビューするための差分取得。

```json
{
  "name": "get_diff",
  "description": "セッションの作業ツリー(worktree含む)の git diff と変更ファイル一覧を返す",
  "inputSchema": {
    "type": "object",
    "properties": {
      "session_id": { "type": "string" },
      "stat_only":  { "type": "boolean", "default": false, "description": "true なら --stat のみ" }
    },
    "required": ["session_id"],
    "additionalProperties": false
  }
}
```

### 3.5 `status`
```json
{
  "name": "status",
  "description": "セッション一覧または単一セッションの状態(running/done/failed、経過時間、累計コスト)を返す",
  "inputSchema": {
    "type": "object",
    "properties": { "session_id": { "type": "string" } },
    "additionalProperties": false
  }
}
```

### 3.6 `usage_report`(v0。追補 A3)
bridge 経由の推計コストとトークン使用量を集計して返す(JSONLログ由来)。

```json
{
  "name": "usage_report",
  "description": "bridge 経由の推計コストとトークン使用量を集計して返す(JSONLログ由来)。チャット(claude.ai)側の使用量は含まれない点を応答に明記する。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "period":   { "type": "string", "enum": ["today", "week", "month", "all"], "default": "week" },
      "group_by": { "type": "string", "enum": ["model", "backend", "repo", "tool"], "default": "model" }
    },
    "additionalProperties": false
  }
}
```

出力: Markdown表(グループ別 呼び出し数 / input / output tokens / 推計USD)+合計+期間。
**必須の注記**(応答に毎回含める):
- `cost_usd` はヘッドレスCLIが同梱価格表からクライアント側で計算する推計値であり、
  請求の正とは乖離しうる(公式ドキュメントの警告)。予算感の把握用途に限定。
- 課金の正: サブスク消費・使用クレジットは claude.ai の 設定 > 使用量、
  API 経路は Console / Usage and Cost API。
- チャット側(claude.ai)の Fable 消費は bridge から観測不能。

### 3.7 `critique` — v2(案C用、任意。**v0/v1 では実装しない**)
独立コンテキストの批評専用呼び出し。チャット(人間+司令塔モデル)の代わりに
自動ループで使う。

```json
{
  "name": "critique",
  "description": "plan の成果物を独立インスタンスに批評させる(案C自動ループ用)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "session_id": { "type": "string" },
      "model": { "type": "string", "default": "claude-fable-5" },
      "max_rounds_guard": { "type": "integer", "default": 3 }
    },
    "required": ["session_id"],
    "additionalProperties": false
  }
}
```
判定は `APPROVE | REVISE(reasons[])` の構造化出力を強制。無限REVISE防止に往復上限。

`orchestrate` ツール(v2。planner↔critic自動往復)の定義は §11 A2 参照。v0/v1では実装しない。

---

## 4. セッションレジストリ

`~/.agent-bridge/sessions.json`(排他ロック付き)。

```json
{
  "b-20260706-a1f3": {
    "backend": "claude",
    "backend_session_id": "…",
    "repo": "shibehasu-ops",
    "worktree": "~/.agent-bridge/worktrees/b-20260706-a1f3",
    "model": "claude-sonnet-5",
    "created_at": "2026-07-06T14:02:11+09:00",
    "phase": "planned | executing | done | failed",
    "has_plan": true,
    "cost_usd_total": 0.42
  }
}
```

- `bridge_session_id` は本サーバーが採番。バックエンドIDへの写像を一元管理する
  (claude と cursor で resume の意味論が違っても、チャットからは同じIDで扱える)。
- `has_plan` は execute の状態機械ガード(§3.3)専用のフラグ。phase からの推測ではなく
  明示フィールドとして管理する(phase は execute 実行後に executing/done/failed へ遷移するため)。
- 7日超の done/failed は `gc` で worktree ごと掃除(v1)。

---

## 5. セキュリティ / ガードレール

1. **リポジトリ allowlist**: config 登録済みエイリアス以外は即エラー。生パス・`..` は拒否。
2. **worktree 隔離**(既定ON): 実行は `git worktree add` した作業ツリーで行い、
   本線へは diff レビュー後に人間がマージ判断。**注意**: worktree は隔離された作業ツリーのため、
   メインの作業ツリーにある未コミットの変更はセッションから見えない(README 運用注意参照)。
3. **push 禁止**: サーバーは push を実行しない。エージェントへのプロンプトにも禁止を明記(§3.3)。
4. **承認ゲート**: `execute.approved === true` 必須。加えてサーバー側で
   「同一 session の plan 出力が存在すること」を検証(planなし実行の拒否)。
5. **資源制限**: 同時実行 max 2(config)、timeout 既定30分、超過は SIGTERM→SIGKILL。
6. **秘密情報**: 環境変数はサブプロセスに最小継承(PATH, HOME, 必要なもののみ)。
   ログに stdin プロンプト全文は残すが、`ANTHROPIC_API_KEY` 等の値は残さない。
7. **モデル既定**: `claude-fable-5` は**明示指定時のみ**。既定に置かない
   (7/8以降の無自覚クレジット消費防止 — settings.json 側の既定確認も運用手順に含める)。
8. **sensitive repo 個別ガード**: config で `"sensitive": true` の repo は、
   `backend=cursor` と `model=claude-fable-5` を**既定で拒否**し、明示 override 引数を要求する
   (30日データ保持ポリシー配慮。会計・未公開研究向け)。v0 は backend=claude のみ実装のため
   cursor 側は実質的に到達不能だが、**検証ロジックは v0 の段階でコードに実装しておく**
   (v1 で cursor backend を追加した初日から漏れなく効くようにするため。関数として独立させ、
   cursor 実装を待たずに単体テスト可能にする)。

---

## 6. 計測・ログ

- `~/.agent-bridge/log/YYYY-MM-DD.jsonl` に 1呼び出し1行:
  `{ts, tool, backend, model, repo, bridge_session_id, duration_s, usage:{input_tokens, output_tokens, ...}, cost_usd, exit_code}`
- `claude -p --output-format json` の usage/cost フィールドをそのまま採録
  (フィールド名は実装時に実測して README に記録)。cursor 側に usage が無い場合は
  `usage: null` で欠測を明示(推計値を捏造しない)。
- `usage_report`(§3.6)はこのログを集計する。週次集計は当面 `usage_report(period=week)` の
  呼び出しで代替し、専用スクリプト化(`bridge-usage-report`)は v1 で検討。

---

## 7. エラー処理

| 事象 | 応答 |
|---|---|
| 未登録 repo / 不正引数 | `isError: true` + 修正方法の短文 |
| サブプロセス非0終了 | stderr 末尾を添えて failed 記録 |
| JSONパース失敗 | 生テキストを `raw_output` として返しつつ warning |
| resume 不能(期限切れ等) | 新規セッション作成を提案する明示エラー(黙って作り直さない) |
| timeout | kill 後、部分出力とログパスを返す |
| claude バイナリが見つからない(ENOENT) | 設定済みパス(`binaries.claude`)を含む明示エラーを返す |

---

## 8. 設定

`~/.agent-bridge/config.json`(**Git 管理外**。実行するマシンごとのローカル設定)
```json
{
  "repos": {
    "shibehasu-ops":   { "path": "~/dev/shibehasu-ops" },
    "answer-prompter": { "path": "~/dev/answer-prompter" },
    "solar-farmland":  { "path": "~/dev/solar-farmland", "sensitive": true }
  },
  "defaults": { "backend": "claude",
                "model": { "claude": "claude-sonnet-5", "cursor": "auto" } },
  "limits":   { "concurrency": 2, "timeout_min": 30 },
  "binaries": { "claude": "claude", "cursor": "agent" }
}
```
`sensitive: true` の repo は `backend=cursor` と `model=claude-fable-5` を既定で拒否し、
明示 override 引数を要求する(30日データ保持ポリシー配慮。会計・未公開研究向け)。

リポジトリには機微な実パスを含めないよう `config.example.json` を同梱し、
実運用の `~/.agent-bridge/config.json` は各マシンでローカルに作成する。

**Claude Desktop 登録**(`claude_desktop_config.json`)
```json
{ "mcpServers": { "agent-bridge": {
    "command": "uv",
    "args": ["run", "--directory", "<abs-path>/agent-bridge", "agent-bridge"]
} } }
```
(`<abs-path>` はこのリポジトリの実際の絶対パスに置き換える。実際の値は README.md 参照)

---

## 9. 実装の進め方(Claude Code への指示テンプレ・2026-07-06 時点版)

> `agent-bridge` リポジトリ(独立プライベートリポジトリ、既に `git init` 済み・
> GitHub `sosakubito-cyber/agent-bridge` に remote 登録済み)直下に、同梱の `SPEC.md` と
> `tools.schema.json` に従って実装してください。
> v0 スコープ: `list_repos` / `plan` / `execute` / `get_diff` / `status` / `usage_report`、
> backend=claude のみ。A1(契約内蔵: description 追記・next_step_hint・plan必須の状態機械)
> と JSONL ログは v0 に含む。`critique` と `orchestrate`、`cursor` backend は実装しない(v1/v2)。
> Cursor CLI の `-p`+`--resume` 併用可否・JSONフィールドは v1 で実測し、結果を README に記録した
> 上で backend=cursor を追加。pytest のスモークテスト(モックsubprocess)を同梱。
> 完了後 Conventional Commits でコミットし、**push は私の承認を得てから**実行してください。
> 提案コミットメッセージ: `feat(agent-bridge): add MCP bridge for chat-driven headless agents (claude backend, v0)`

**マイルストーン**
- v0(今週): claude backend のみ、worktree、ログ、usage_report、A1契約内蔵。
  Desktop から一連の plan→批評→execute→diff を通す。
- v1: cursor backend、status/gc、usage レポートの整形・スクリプト化。
- v2: critique / orchestrate 追加(案C。planner↔critic N往復→人間承認1回→execute)。

---

## 10. 付録: Fable 無償枠での実測(〜7/7 PT)

ラッパー完成を待たず、今日そのまま実行して計測できる:

```bash
cd <repo>
claude -p "<代表的タスクの計画>" --permission-mode plan \
  --model claude-fable-5 --output-format json | tee /tmp/fable-plan.json
# usage / cost フィールドを確認し、同一タスクを --model claude-sonnet-5 でも実行して比較
```

比較observables: 入出力トークン、(あれば)コスト、計画の質(批評観点の数・前提の妥当性)。
この実測値が §6 レポートの基準線になり、7/8 以降「批評役に Fable を使う頻度」の
意思決定材料になる。

---

## 11. 付録: 2026-07-06 追補(A0–A5)適用ログ

本節は元の追補文書の要点と、本 SPEC への反映箇所の対応表。追補と本文が矛盾する場合は
追補が優先(本統合版では既に本文に反映済み)。

### A0. 配置の変更: 独立リポジトリ化(反映済み — 冒頭・本ファイルの配置そのもの)
決定: agent-bridge は shibehasu-ops(や他の操作対象リポジトリ)内ではなく、
独立プライベートリポジトリ `agent-bridge` に置く。
理由: (1) ドメイン分離 — bridge は全リポジトリ横断の開発インフラ。
(2) 自己参照の回避 — 道具が操作対象の中に住むと worktree の中に自分のソースが現れる等の
再帰が生じる。(3) コンテキスト衛生 — one-rule-one-location 方針との整合。
(4) セキュリティ境界 — acceptEdits でサブプロセスを起動する感度の高いコード。

### A1. ワークフロー契約のコード内蔵(反映済み — §3 共通方針・§3.2・§3.3・§4 has_plan)
チャット側モデルのユーザープリファレンスに依存せず、ツール description・
`next_step_hint` フィールド・状態機械(plan なし execute 拒否)をサーバー側に埋め込む。

### A2. `orchestrate` ツール(v2。**未実装**、定義のみ将来参照用に記載)

```json
{
  "name": "orchestrate",
  "description": "計画立案(planner)と独立批評(critic)を自動でN往復させ、収束した最終計画とコスト内訳を返す。実行は行わない。返された計画はユーザーに提示し、承認後に execute を使うこと。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task":    { "type": "string" },
      "repo":    { "type": "string" },
      "cost_cap_usd": { "type": "number", "description": "推計コストの上限。超過見込みで往復を中断し、途中経過を返す。必須",
                        "minimum": 0.1, "maximum": 20 },
      "max_rounds": { "type": "integer", "default": 3, "maximum": 5 },
      "planner_backend": { "type": "string", "enum": ["claude", "cursor"], "default": "claude" },
      "planner_model":   { "type": "string", "default": "claude-sonnet-5" },
      "critic_model":    { "type": "string", "default": "claude-fable-5",
                           "description": "批評役。低トークン工程なので高性能モデルを既定とする" },
      "context": { "type": "string" }
    },
    "required": ["task", "repo", "cost_cap_usd"],
    "additionalProperties": false
  }
}
```

ループ仕様: (1) planner が `--permission-mode plan` で計画生成。(2) critic に計画全文+タスクを渡し
`{"verdict": "APPROVE"|"REVISE", "reasons": [...], "must_fix": [...]}` を強制(critic は Read 系のみ)。
(3) REVISE なら must_fix を resume で渡し再計画。APPROVE か max_rounds 到達か cost_cap 超過見込みで終了。
(4) 戻り値: 最終計画、ラウンド別判定サマリ、モデル別usage/コスト内訳、終了理由、`next_step_hint`。
コストガード: 累計+直近ラウンド実測コストが cap を超えるなら次ラウンドへ入らない。
critic が2回連続で同一 must_fix を返した場合は早期終了(空回り検出)。

### A3. `usage_report` ツール(v0。反映済み — §3.6)

### A4. 運用: コスト上限の二重化(v1以降の運用チェックリスト用メモ)
1. bridge 層: `orchestrate` の `cost_cap_usd`(呼び出し単位。v2実装時)。
2. アカウント層: Claude Code の `/usage-credits` で使用クレジットの月間支出上限を設定
   (Pro/Max、請求アクセス必要)。claude.ai 設定 > 請求側の支出上限も併用可。
3. 週次で `usage_report(period=week)` と 設定>使用量 を突き合わせる。

### A5. スコープ改訂(反映済み — 本 SPEC 全体がこの改訂後の姿)
- v0(このリポジトリで実装): `list_repos` / `plan` / `execute` / `get_diff` / `status` +
  A1(契約内蔵) + `usage_report`。backend=claude のみ。
- v1: backend=cursor、gc、レポート整形。
- v2: `orchestrate`(`critique` 単体ツールは orchestrate に吸収し、独立ツールとしては保留)。
