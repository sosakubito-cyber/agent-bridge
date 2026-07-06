# DECISIONS

- 2026-07-06: [暫定・未確定] v2 orchestrate の `critic_model` 暫定既定を `claude-sonnet-5` とする(fable は明示指定時のみ)。根拠: answer-prompter でのUI実装計画立案(n=1、Fableが本来得意としない領域の題)比較で、Sonnet 5がコスト・時間・信頼性の全指標でFable 5を上回った。ただしcriticの本来の仕事(計画の論理的な批評)はUI実装計画立案とは異なる認知能力を要するため、この結果だけでは`critic_model`既定の最終決定には不十分。アルゴリズム設計・リファクタ方針・研究設計など推論寄りの題で追加計測してから最終判断する。追加計測は日常のagent-bridge運用(usage_reportでの蓄積)で自然に行う。詳細: `answer-prompter/docs/fable-baseline-20260706.md`。
