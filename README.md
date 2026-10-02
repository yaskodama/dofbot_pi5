# dofbot_pi5

Yahboom DOFBOT（6 軸、Raspberry Pi 5 版）を **Embedded Xinu + AIPL** で動かすための Mac 側の道具と振り付け。
Xinu 側（I²C の腕ドライバ、UVC カメラ）は [xinu-rpi5](https://github.com/yaskodama/xinu-rpi5)、
シミュレータ（CG の腕・立方体・手首カメラ、PLAN 表示）は [aice-avm](https://github.com/yaskodama/aice-avm) にある。

## 動画

[![2026年9月14日（YouTube）](https://img.youtube.com/vi/MSeznEtUzes/hqdefault.jpg)](https://www.youtube.com/watch?v=MSeznEtUzes)

https://www.youtube.com/watch?v=MSeznEtUzes

| ファイル | 中身 |
|---|---|
| `aipl/sort.aipl` | 立方体を手首カメラで探して挟み、緑は右・青は左に置く。模型 → 実機の順に同じプログラムで実行 |
| `aipl/dofbot_arm.aipl` | 板に載せる腕のアクター（POST /cc） |
| `color_service.py` | Mac で動く「Camera」「Plan」節点（UDP 9012 / HTTP 8091）。色判定・探索・下ろし・挟めた判定・PLAN |
| `locate.py` | 逆運動学、カメラ画像から卓上への逆射影、立方体の探索と段階的な下ろし |
| `geometry.json` | 寸法の正本（出典つき: URDF / 仮 / 実測）。CG と逆運動学が同じ値を使う |
| `snapshots/2026-09-29_sort_ok/` | 実機で完遂した時の一式と手順（README.md） |
| `NEXT_SESSION.md` | 経緯と引き継ぎ |
| `aipl/sort_run*.log` | 実行記録（論文①の 7.4 節の根拠） |

動かし方は `snapshots/2026-09-29_sort_ok/README.md` を見る。
