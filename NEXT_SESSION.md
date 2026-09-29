# DOFBOT（Xinu＋AIPL）—— 次のセッションへの引き継ぎ

最終更新: 2026-09-14 16:10（セッション終了時）

## 30 秒で状況を掴む

| 板 | 何が動いているか | 番地 |
|---|---|---|
| DOFBOT の Pi 5 | **Xinu**（USB メモリ `XINU5` から起動、Linux の SD は抜いてある）。腕（I²C 0x15）・USB カメラ（UVC 等時）・ファン・AIPL アクター `dofbot` | 192.168.3.101（有線） |
| もう一つの Pi 5 | Linux（Yahboom の SD）。カメラは外してある | 192.168.3.19（`yahboom.local`） |
| Mac | AIPL 正典（OCaml）、Xinu シミュレータ aice-avm（:8080） | — |

**板に焼いてあるのは build `Sep 14 2026 12:18:34`（xinu-rpi5 `3b37708`）。**
**未焼きの最新は `d4eac11`（build 15:49:58）** —— 起動時のアクター載せ＋カメラ開始を専用プロセスに移した版。
12:18 の板は再起動のたびに **HTTP が固まる可能性がある**（12:18 版で 1 回発生。UDP/9010 と ping は生きる）。
→ **次回はまず `d4eac11` を焼く**（`make pi5` → `XINU5` に `kernel_2712.img` を写す → md5 → 電源入れ直し）。

## 使い方（いつもの手順）

```sh
# 版の確認（焼いたあと必ず。HTTP が応答する≠再起動済み）
curl -s http://192.168.3.101/version | head -1
# 腕（文字列命令。シェルなら `arm ...`）
curl "http://192.168.3.101/arm/read"
curl "http://192.168.3.101/arm/pose/90/90/90/90/90/30/2000"
# カメラ（起動 50 s 後に自動開始。止まっていれば /cam/start）
curl "http://192.168.3.101/cam?w=160"          # "DW DH SRCW SRCH LEN streaming|idle"
curl "http://192.168.3.101/cam/start?frame=3&fps=10"
# ファン（温度追従が既定。手動は level=、戻すのは auto=1）
curl "http://192.168.3.101/fan"
# アクター（起動時に自動で載る。無ければ）
curl --data-binary @$HOME/dofbot_pi5/aipl/dofbot_arm.aipl http://192.168.3.101/cc
curl "http://192.168.3.101/api/x/"
```

シミュレータ: `cd ~/projects/aice-avm && ./_build/default/server.exe 8080`（`eval "$(opam env)"` 必要）→ `http://localhost:8080/#arm-xinu`
（DOFBOT arm 窓＋AIPL program 窓、映像元は Xinu のカメラ）。

振り付け（模型 → 実機）:
```sh
cd ~/dofbot_pi5/aipl && printf 'load %s\ncompile\n' "$PWD/complex.aipl" > r.repl
cd ~/aios/abclcp && ./src/abclrepl_thread -q -f ~/dofbot_pi5/aipl/r.repl
```
実測: 44 応答すべて ok（12:04 版以降、I²C 待ち 100 ms・再試行 3 回で時間切れは消えた）。

## 今日できたこと（時系列）

1. Linux 上で SSH→Python→I²C の三層を整理（レポート第 1〜3 節）。把持は未達（カメラに指が映らない）。
2. Linux を外し Xinu へ: `device/i2c/rp1i2c.c`（RP1 i2c1）＋ `system/arm.c`（電文）＋ `/arm/...`。
3. AIPL 化: 正典に `remote_call`／`arm_cmd`／実行位置通知（UDP/9011）。板に `Arm` アクター（`arm_cmd` 組込み）。
4. シミュレータに DOFBOT arm 窓（3D 模型・カメラ・スライダ・模型/実機切替）と AIPL program 窓（実行行を反転）。
5. **UVC カメラドライバ**（xHCI 等時 IN、TRB 環 512、UVC ヘッダでフレーム組立）→ 320×240 @10fps。`/cam?w=&off=` で RGB565 分割配信。
6. ファン（RP1 PWM1 ch3、温度追従）、起動時自動開始、腕基板の自動リセット、I²C 待ち延長。
7. レポート 8 頁を kodamay.org 研究レポート 90 本目として公開: `reports/2026-09-14_dofbot_xinu_aipl_uvc.pdf`。

## 踏んだ罠（再発防止）

- **EP0 の転送環は全 USB 装置で共有**。別の装置を address するとカメラの制御転送が全部時間切れ → 配信開始のたびにカメラを address し直す。
- **remote_call の要求番号を毎回 20000 から始めると、相手が「再送」と見て前回の答えを返す** → 起動時刻からずらした。
- **pkill -f のパターンに自分の bash -c 行が当たって自殺**（Linux Pi のカメラ係） → `pkill -f "^python3 -u /home/pi/cam_service.py"`。
- **腕基板はサーボ通信中に I²C 応答が 20 ms を超える**。動作直後に読みが全滅（書きは ACK）→ 待ち 100 ms・再試行、3 回全滅で基板リセット。
- **net tick で長い仕事をすると画面ループ側で当たって HTTP が固まる** → 専用プロセス（`dofbot_boot_proc`）。
- **1 枚を分割して取るあいだに最新が入れ替わる** → off=0 で写し取る（12:18 版に入っている）。
- 起動直後 30〜60 s は機内ブラウザで HTTP が待たされる（故障ではない）。
- 板を電源から入れ直すと RAM 上のアクターは消える（自動載せ直しあり）。カメラ配信も止まる（自動開始あり）。

## 次の一手（候補）

1. `d4eac11` を焼いて、再起動 3 回で HTTP が生きることを確かめる。
2. カメラの画像を AIPL から使う（`cam_frame()`／タグ検出の組込み）。HDMI 画面にカメラ窓。
3. 把持: 腕の外から見るカメラ（Linux Pi 5 に付け替えて `cam_service.py`）か接触センサが要る。手首カメラには指が映らない。
4. 9 月 7 日レポートの 6＋1 アクタ設計（関節 6＝判断層、arm 1＝io）に分ける。

## 場所

- 板側: `~/projects/xinu-rpi5`（branch `feat/smp-symmetric`）: `device/i2c/rp1i2c.c` `system/arm.c` `device/usb/rp1usb.c`（UVC は末尾）`device/genet/rp1fan.c` `loader/main.c`（`dofbot_boot_proc`）`system/tcp_server.c`（`/arm` `/cam` `/fan` `/usb/cam-probe`）`cc/cc.c`（`v_arm_cmd`）
- 正典: `~/aios/abclcp`（branch `make-src-base`）: `src/eval_thread.ml`（`remote_call` `arm_cmd` `trace_pc`）`src/typing_env.ml`
- シミュレータ: `~/projects/aice-avm`（main）: `server.ml`（`/api/arm` 模型 `sim_cmd` UDP/9011）`www/js/xinu.js`（`openArm` `openAiplProgram`）
- AIPL と道具: `~/dofbot_pi5/`（`aipl/complex.aipl` `aipl/dofbot_arm.aipl` `cam_service.py` `arm.py` `dofbot_control_path.tex/pdf`）
- レポート原稿の写し: `~/kodamay_org_site/kodamay.org/reports-src/2026-09-14_dofbot_xinu_aipl_uvc/report.tex`
- メモリ: `project-dofbot-ultra-baremetal-arm` `project-xinu-pi5-uvc-camera` `project-dofbot-pi5-real-arm`

## 追記（16:10）

- xinu-rpi5 の README にロボットアームの節（英・日）と実演動画 https://youtu.be/MSeznEtUzes を載せた（`0d5dac5`）。
- **GitHub の `main` を `feat/smp-symmetric` の先端まで早送りした**（分岐なし。以前の main の先端は `5887c97`）。
  以後は `feat/smp-symmetric` へ push したら `git push origin feat/smp-symmetric:main` も打つ（README を main で見せるため）。
- 全リポジトリ（xinu-rpi5 / abclcp / aice-avm / kodamay-org-web）はコミット・push 済み。abclcp の未コミットは build 生成物だけ。

## 追記（2026-09-26）

- 板は **12:18 版のまま**（d4eac11 を一度焼いたが差し戻した）。控え: `xinu-rpi5/compile/kernel_2712.img.bak-0914-1218`。
- d4eac11 で HTTP が死んだように見えたのは、Chrome の `#arm-xinu` 画面と待ちループが起動中の板を叩き続けたため。12:18 版でも同じ症状、止めたら約1分で復帰。**d4eac11 は未評価**。
- 再評価手順: シミュレータ画面を閉じる → `lsof -nP -i @192.168.3.101` が空 → 焼く → 10 秒おきに `/version` 1 本だけ。
- complex.aipl の 22 手: 模型 22/22、実機 22/22（画面を閉じた状態で I²C fail=0）。

## 追記2（2026-09-26 13:25）d4eac11 を再評価（板は今 d4eac11）

- 洪水なしで起動 → HTTP は約40 s で応答、固まらない（狙いは達成）。
- **不具合①** ファンの温度追従（`rp1fan_thermal_tick`）が net tick から消えたまま移されていない → `fan level=-1`。
- **不具合②** `dofbot_boot_proc` が 2 分以上たってもアクター載せ・カメラ開始をしない（proc_create 失敗か、中で止まっているか不明。/ps 相当の計器が無い）。
- 手当て（起動ごとに要る）: `/fan?level=75` → `POST /cc dofbot_arm.aipl` → `/cam/start?frame=3&fps=10`。これで模型 22/22・実機 22/22、I²C fail=0。
- 次: ファン tick を net tick に戻す＋boot proc の各段で uart/リングに記録し `/bootlog` で見えるようにしてから直す。

## 追記3（2026-09-27）色で振り分け（sort.aipl）

- `aipl/sort.aipl`: 掴む前に「掴む所を見る」姿勢（90 75 15 35）で色を聞き、緑→土台150°（右）、青→30°（左）、色なし→90°に戻す。模型→実機の順。`r_sort.repl`。
- `color_service.py`（Mac、UDP/9012 の "Camera"、HTTP/8091）: 姿勢から FK でカメラ（手首上面、指の軸から 3.2 cm・画角 60°）を出し、
  掴む所（P_CENTER 指先の下の 3.5 cm 立方体）が写る枠（ROI）だけで判定。枠の 30% 以上で色と判定。実機画像は 180° 回す（--no-rot180）。
  画像は aice-avm の窓が送る（/simframe = CG カメラ、/realframe = 板から受けた実機カメラ）。板に直接聞くのは窓が無いときだけ。
- aice-avm `www/js/xinu.js`: CG 立方体（掴む/運ぶ/置く）、CG 手首カメラ、中央 Camera 窓（CG と実機を並べ ROI 枠）、AIPL 窓下に色の認識率バー。
  `/sim?c=green|blue` で CG 立方体の色を変えて置き直す。
- 未確認: 実機の ROI 枠が現実の掴む所と合っているか（実機の卓上に立方体が無かった）。立方体を置いて Camera 窓の枠と重なるか見る。ずれたら --fov / CAM_UP を合わせる。
- 窓のカメラ取得は 250 ms 間隔に落とした（50 ms では板の HTTP が詰まり、最後は板ごと落ちた）。
- 板は d4eac11 のまま。起動ごとに `/fan?level=75` → `POST /cc dofbot_arm.aipl` → `/cam/start?frame=3&fps=10` が要る。

## 追記4（2026-09-27）ずらして撮ってから挟む

- カメラは手首の**上面**（-cross(d3,l) 側）。以前の模型は下面に付けていた → xinu.js と color_service.py で符号を直した。
- 立方体は土台の前 17 cm（CUBE.x / CUBE_X）。姿勢は IK で求めた（手の傾き 165°）:
  見る 90 84 3 18（カメラ軸が立方体中心を通る、距離 12 cm）→ 手前 90 59 35 10 → 挟む 90 39 28 38（指先を中心より 2 cm 奥）。
- color_service の real は「問い合わせ後に届いた 1 枚」を待って判定（腕が止まる前の古い 1 枚で 19.5% になっていた）。
- 結果: 模型 緑 87.9% → 右 150°（CG 立方体が掴まれ (0.085,-0.148) に置かれたのを /stat の cube_at で確認）。
  実機 青 100%（水色、色相 195°）→ 左 30°。実機で本当に挟めたかは未確認（目視が要る）。

## 追記5（2026-09-27）探して挟む・挟めるまで繰り返す

- Xinu のカメラ画像は**回っていない**（土台/腕を動かして実測）。Linux のときの「180°」は当てはまらない。color_service は --rot180 で旧挙動。
- locate.py: 見る姿勢で撮る→色の塊の重心を卓上へ逆射影→向け直す、を収束まで（補正は 6 割、実機の画角は 60° より狭いらしい）。
  見つからなければ 13/17/21 cm × 0/±20° を順に見る。腕は UDP（dofbot アクター、再送）で動かし、角度を読み戻して確かめる。
- sort.aipl: locate → get base/pre/grasp → 挟む → 持ち上げて指を閉じたまま locate、卓上に残っていれば挟み直し（上限 10）。
- 指は 110 まで（135 で閉じ切った直後に腕の基板が無応答になった。電源を入れ直すまで戻らず、Pi 5 も再起動した）。
- 結果: 模型は 1〜2 回で成功。実機は 6 回目に卓上が空になった（本当に挟めたかは目視未確認）。

## 追記6（2026-09-28）寸法を一か所に・CG に寸法線

- `~/dofbot_pi5/geometry.json` が寸法の正本（base_h, H, L1, L2, L3, LG, cam_along, cam_up, fov, cube）。各値に src（URDF / guess / measured）。
  color_service が読み（GET/POST :8091/geo）、locate.py の逆運動学・逆射影と、xinu.js の CG・CG カメラ・寸法線が同じ値を使う。
- シミュレータ DOFBOT 窓: 「寸法」で寸法線（黄=URDF、橙破線=仮、緑=実測）、「寸法を編集」で cm 入力→保存。
- 仮（未実測）: 台座 6.6、指 6.0、手首→カメラ 6.25、指の軸→カメラ中心 3.2、画角 60°、立方体 3.5（cm）。実測が要る。
- 実機の挟む高さは未解決: 模型の計算で 2.3 cm は卓に当たり、4.5 cm は届かない、3.4 cm も挟めず。LG や L3 の実測で直るはず。
- 腕の基板（STM8）が挟む動作のあとに無応答になる（2 回目）。腕の電源の入れ直しで戻る。
- aice-avm サーバが一晩で止まっていた。流す前に :8080 と UDP 9010、/stat の cg_age を確かめる。

## 追記7（2026-09-28 昼）指の実測・挟めた判定・基板が落ちる疑い

- 指（サーボ6）の実測（物差し、7 段）: 30,50→6.2 70→5.8 90→5.2 110→4.2 131→3.0 135→2.8 cm。geometry.json の grip_cal。
  3 cm 立方体は 135 で挟む（110 は 4.2 cm で触れていなかった）。
- 挟めた判定 = 135 で閉じた後のサーボ6の読み戻し ≤ 133（物で止まる）。空だと 135。held(real) で実測どおり 135 → no を返した。
- 実機は計算より 1° 左を掴む → real_base_offset=+1。指の長さ LG=8.3 cm（卓に当たった高さからの推定）、挟む高さ TIP_Y=1.5 cm。
- 腕の基板（STM8）が止まる件: **Xinu の /arm read が「6 軸とも ?」を 3 回続けると基板リセットを送り、それで電源を入れ直すまで戻らない**疑いが濃い
  （止まる直前に "(board reset)"）。対策（Mac 側）: 読みは 2 回まで・間 1.5 s、lower では読まない。根本は system/arm.c の自動リセットを外して焼き直し。
- 板の UDP 受け口で答えが空になったときは、腕のアクターを POST /cc で載せ直すと戻った。
- Chrome が板の :80 に要求なしの接続を張ったままにすると Xinu の HTTP が詰まる（Chrome を終了すると即復帰）。

## 追記8（2026-09-29）2 つ目の成功（緑の立方体）

- 新しい緑の立方体で sort.aipl を流し、実機が 6 回目の試行で挟んで右の置き場（土台 150°）へ置いた（先生が目視で成功を確認）。
  記録 `aipl/sort_run20.log`。1・2・5 回目は判定範囲の 1.7〜7.7% しかない小さな青い塊（ケーブル等）を追って空振りし、
  いずれも指の読み戻し 135 で正しく「挟めていない」と判定した。挟めた回の読み戻しは 133（しきい値と等しい、2 回とも）。
- 対策: 画像の 1.5% 未満の色の塊は立方体とみなさない（locate.py、bcb6c96）。この修正の後はまだ流していない。
- これで実機の成功は 2 回（9/29 の青 = run19、緑 = run20）。

## 追記9（2026-09-29 午後）緑と青の 2 つを 1 回で運んだ

- 15 回流して（2 つ 13 回、1 つ 2 回）、最後の sort2_run13 で実機が 2 つとも運んだ（目視で成功）。写し `snapshots/2026-09-29_sort2_ok/`。
- 4 回目・9 回目の「2 つ置いた」は誤り（err を色として扱った／開いた指 40 を挟めたと数えた）。
- 腕基板の停止は、自動リセットを外した後も起きた（原因不明）。
