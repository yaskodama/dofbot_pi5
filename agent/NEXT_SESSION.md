# モバイルエージェント実験基盤 — 次のセッションへの引き継ぎ

最終更新: 2026-10-11 16:00 頃（セッション終了時）

## 30 秒で状況

- 生成 AIPL を **モバイルエージェント**として扱う方式に変わった（先生の指示、2026-10-11）。
  同じソース `sort_agent.aipl` を **Xinu シミュレータ（aice-avm）→ 関門 → Pi 5 の Xinu** の順に送る。
- **実機でも成功済み**: 15:29 の起動で模型 2 個・実機 2 個（各 35 段、107 秒 / 144 秒）。記録 `runs/2026-10-11_1529_sim_then_real_ok.log`。
- **関門（論文の式(1)）を港に実装済み**。却下（緑を 120° に置く壊れた版）と合格（正規版、模型のみ）は試験済み。
  **未試験: 合格 → 実機へ移動 → 実行の通し**（実機の立方体が置き場に残っているので、腕の前へ戻してから）。
- 論文①はこの方式へ改稿済み（20 頁）: `~/paper1_sim2real/tex/paper1.tex`、写し `../paper/`（push 済 `ddb3753`）。

## 未コミット（次に最初にやること）

| repo | ファイル | 中身 |
|---|---|---|
| `~/dofbot_pi5` | `agent/dock.py` | 関門（`gate()`）、`--cubes` `--agent` `--no-gate`、却下で exit 2 |
| `~/dofbot_pi5` | `color_service.py` | 窓から全立方体の位置を受け、`/stat` に `cubes` / `cubes_age` |
| `~/dofbot_pi5` | `agent/runs/` 新規 4 件 | `gate.jsonl`、却下・合格の記録、壊れた版 `bad_agent_green120.aipl` |
| `~/projects/aice-avm` | `www/js/xinu.js`, `www/index.html` | 窓が全立方体 `cubes=color:x,y,z,held;...` を送る（`?v=21`） |

コミット済み・push 済み: aice-avm `44a95d6`（arm_cmd・文字列比較・置き場）、dofbot_pi5 `8602910`（agent 一式）、`ddb3753`（論文）。
ブランチ `feat/mobile-agent` は両 repo に残っている（main へ早送り済み、消してよい）。

## 動いているもの（2026-10-11 終了時）

| もの | 起動のしかた | 備考 |
|---|---|---|
| aice-avm（:8080, UDP 9010/9011） | `cd ~/projects/aice-avm && eval "$(opam env)" && nohup ./_build/default/server.exe 8080 --no-open > /tmp/aice-avm.log 2>&1 &` | **`/api/restart` は使わない**（stdout が閉じた端末のままで UDP 9010 の受け口が死ぬ）。必ず出力をファイルへ |
| color_service（:8091, UDP 9012） | `cd ~/dofbot_pi5 && nohup python3 -u color_service.py >> color_service.log 2>&1 &` | 15:43 に再起動（新しい `cubes` を含む版） |
| 窓 | Chrome で `http://localhost:8080/#arm-xinu` | `curl -s localhost:8091/stat` の `cg_age` と `cubes_age` が 1 秒前後なら CG が生きている |
| Pi 5 の Xinu | USB `XINU5`、build `Sep 29 2026 09:57:23`、192.168.3.101 | 常駐は標準の `dofbot_arm`（港が去るときに戻す） |

## 流し方

```sh
cd ~/dofbot_pi5/agent
python3 dock.py                 # 模型 → 関門 → 実機（立方体 2 個を腕の前、軸から 14–23 cm・正面 ±45°）
python3 dock.py --only sim      # 模型だけ（関門の判定も出る。実機には触らない）
python3 dock.py --agent X.aipl  # 別のエージェント
python3 dock.py --no-gate       # 関門で落ちても移る（gate.jsonl には記録）
```
起動前: 板が起動直後なら ping だけで待ち、40 秒後に `/version` 1 回 → `/fan?level=75` → `/cam/start?frame=3&fps=10`
（**起動中の板に HTTP を連打しない**）。港は実機へ移る前にカメラが streaming か確かめ、止まっていれば始動する。

## 関門の中身（dock.py `gate()`）

1. エージェントの申告 `placed` ＝ CG の卓の個数（`--cubes both` なら 2）
2. エージェントの申告と独立に、CG の全立方体が卓上（持たれていない、y ≤ 2 cm）で、
   色の置き場（緑 150° / 青 30°、軸から 17 cm）の **3 cm 以内**
3. 窓からの位置が新しい（3 秒以内）

だめなら実機へ移らず exit 2。判定は毎回 `runs/gate.jsonl` に 1 行。

## 罠（今日見つかったもの）

- **Pi 5 の板コンパイラ**（カーネル焼き直しが要るので回避中、直すのは今後）:
  フィールド初期値は int/bool のみ ／ **コメント中の非 ASCII（§）で黙って壊れる** ／
  `web_expose` を 2 本書くと両方 actor #0 ／ `/cc` が「=> 0」でも取り込まれないことがある（港が status で確かめ再送）。
- **板の実行は 1 回 250 ms で打ち切り**、その経路で `wait` 不可 → エージェントは `step()` で 1 断片ずつ進む状態機械。
- **`/cc` の後に手首カメラが止まり `cam: enum failed`** で戻らなかった（1 回）。電源の入れ直しで復旧。原因不明。
- color_service は今 **Command Line Tools の Python 3.9** で動いている（以前は Homebrew 3.14）。動作は問題なし。

## 次の候補

1. 上の未コミットをコミット・push（先生の指示があれば）
2. 立方体を戻して **合格 → 実機** の通し試験
3. Actor 契約（observe/pick/place）を両方の主の操作として実装し、LLM が生成したエージェントを移動させる
4. 待つ形（`now r.pick()`）→ 断片列への変換（aice-avm の `split_at_now` が手がかり、未検証）
5. Pi 5 カーネルの 3 つの差を直す、カメラ停止の原因調査
6. 論文の新しい参考文献 4 件（Fuggetta 1998 ほか）の書誌を確認

関連文書: `../NEXT_SESSION.md`（DOFBOT 全体、9/14 時点）、`../snapshots/2026-09-29_sort2_ok/README.md`（従来方式の手順）。
