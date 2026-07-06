# DECISIONS

- 2026-07-06: [暫定] v2 orchestrate の `critic_model` 既定値を `claude-fable-5` から `claude-sonnet-5` に変更(fable は明示指定時のみ)。根拠: answer-prompter リポジトリでの同一タスクplan比較(n=1)でSonnet 5がコスト・時間・信頼性の全指標でFable 5を上回った。詳細: `answer-prompter/docs/fable-baseline-20260706.md`。追加計測で再評価の余地あり。
