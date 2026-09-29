# 2026-09-29 色で振り分け — 実機で完了した状態

模型（Xinu シミュレータの CG）→ 実機（DOFBOT + Xinu Pi 5）の順に `sort.aipl` を流し、
実機が青い立方体（1 辺 3 cm）を 1 回で挟んで左の置き場（土台 30°）へ運び、置いた（先生の目視で完了を確認）。
結果の記録は `sort_run19_success.log`。

## 動いたときの版

| もの | 版 / 場所 |
|---|---|
| Xinu カーネル（USB メモリ XINU5） | `Sep 14 2026 15:49:58`（xinu-rpi5 `d4eac11`、md5 `9ceb965f…`） |
| 腕のアクター | `dofbot_arm.aipl`（起動ごとに POST /cc で載せる） |
| 色判定・探索・PLAN の係 | `color_service.py` + `locate.py`（Mac、UDP 9012 / HTTP 8091） |
| 寸法の正本 | `geometry.json` |
| 振り付け | `sort.aipl`（模型→実機）/ `sort_sim.aipl`（模型だけ） |
| シミュレータの画面 | `xinu.js`（aice-avm `www/js/xinu.js`、未コミットの変更を含む写し） |

## 効いた設定（geometry.json / locate.py）

- 立方体 1 辺 3 cm（実測）。置き場は土台 150°（右・緑）/ 30°（左・青）の前 17 cm。
- 指（サーボ6）の幅（実測）: 30,50→6.2 70→5.8 90→5.2 110→4.2 131→3.0 135→2.8 cm。挟むときは 135。
- 挟めた判定: 135 で閉じた後の読み戻しが 133 以下（今回は 133 ちょうど。空なら 135）。
- 指の長さ LG = 8.3 cm（卓に当たった高さからの推定）、挟む・置く高さ TIP_Y = 1.5 cm。
- 実機の土台補正 +1°（計算より 1° 左を掴みに行くため）。
- Xinu のカメラ画像は回っていない（Linux のときの 180° は当てはまらない）。
- 立方体を見られるのは土台の軸から 14〜23 cm。

## 流す手順

1. Chrome を終了しておく（Chrome が板の :80 に空の接続を張ると Xinu の HTTP が詰まる）。
2. 板の起動を待つ → `curl http://192.168.3.101/version`（15:49:58）。
3. 起動時に自動で行われない 3 つを手で:
   `curl "…/fan?level=75"` → `curl --data-binary @dofbot_arm.aipl …/cc` → `curl "…/cam/start?frame=3&fps=10"`。
   UDP で腕が答えるか: `python3 -c "import locate as L; print(L.arm_udp('ver'))"`。
4. シミュレータのサーバ（`~/projects/aice-avm/_build/default/server.exe 8080`）と `color_service.py` が動いていること。
5. Chrome で `http://localhost:8080/#arm-xinu` を開き、`curl localhost:8091/stat` の `cg_age` が数字になるのを待つ。
6. `cd ~/aios/abclcp && ./src/abclrepl_thread -q -f ~/dofbot_pi5/aipl/r_sort.repl`。
   CG の左上に PLAN（実行中の手が反転）、AIPL 窓の下に色の認識率バー、中央に CG / 実機カメラ。

## 残っている問題

- 腕の基板（STM8）が止まる: Xinu の /arm read が「6 軸とも ?」を 3 回続けると基板リセットを送り、電源を入れ直すまで戻らない疑い。
  Mac 側は読みを減らして回避中。根本は system/arm.c の自動リセットを外して焼き直す。
- d4eac11 はファンの温度追従が消えている・起動時の仕事（アクター/カメラ）が動かない。
- 仮の寸法（台座、指の長さ、カメラの位置と画角）は未実測。
