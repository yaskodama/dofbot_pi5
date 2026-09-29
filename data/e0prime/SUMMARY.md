# E0′ 実機の基礎性能 — 結果（2026-09-29〜30）

手順書: `protocol/E0prime_v1.md`（結果を見る前に固定、途中の変更は日時つきで追記）。1 行 1 試行の記録: `trials.jsonl`。

## 集計

| | 完遂 | 合格条件 |
|---|---|---|
| 1 個（元の 20 回） | 15/20 = 0.75 | 0.8 以上 → 不合格 |
| 2 個（元の 10 回、途中で条件を 3 回変更） | 3/10 = 0.3 | 0.7 以上 → 不合格 |
| 腕の基板の停止（全 46 回の実行） | 8 回 | 1 回以下 → 不合格 |

やり直し（先生の指示、結果を見た後）: 15 回実行、12 回成功。成功率の推定には使わない。

挟めた判定（145 で閉じた後の読み戻し ≤141）: 挟んだ 138〜140、空振り 143〜145 で全件正しく分かれた。

## 1 個（試行 1〜20）

| 試行 | 条件 | 結果 | 分 | 失敗の理由 |
|---|---|---|---|---|
| 1 | green P1 (17cm front) | 成功 | 2.97 |  |
| 2 | blue P2 (15cm, 20deg toward the left place) — redo | 成功 | 1.80 |  |
| 3 | green P3 (20cm, 20deg toward the right place; pointed at bas | 成功 | 2.10 |  |
| 4 | blue P4 (17cm, 35deg toward the blue place; pointed at base  | 成功 | 1.80 |  |
| 5 | green P5 (20cm, 35deg toward the green place; pointed at bas | 失敗 | 4.81 | grasp missed twice (readback 143->145): fingers landed beyond (far side of) the cube at 20 |
| 6 | blue P1 (17cm front; pointed at base 90) | 成功 | 1.77 |  |
| 7 | green P2 (15cm, 20deg toward the blue place; pointed at base | 失敗 | 1.80 | no grasp attempt: surveyed at 13.6 cm, base 56 (pointed 15 cm, base 70); refinement put it |
| 8 | blue P3 (20cm, 20deg toward the green place; pointed at base | 成功 | 2.17 |  |
| 9 | green P4 (17cm, 35deg toward the blue place; pointed at base | 成功 | 2.17 |  |
| 10 | blue P5 (20cm, 35deg toward the green place; pointed at base | 成功 | 2.20 |  |
| 11 | green P1 (17cm front; pointed at base 90) | 成功 | 1.87 |  |
| 12 | blue P2 (15cm, 20deg toward the blue place; pointed at base  | 失敗 | 2.27 | no grasp attempt: 3 surveys found nothing in reach (glimpses 2, 2, 0); P2 (15 cm) at the i |
| 13 | green P3 (20cm, 20deg toward the green place; pointed at bas | 成功 | 1.97 |  |
| 14 | blue P4 (17cm, 35deg toward the blue place; pointed at base  | 成功 | 2.24 |  |
| 15 | green P5 (20cm, 35deg toward the green place; pointed at bas | 成功 | 2.17 |  |
| 16 | blue P1 (17cm front; pointed at base 90) | 成功 | 2.17 |  |
| 17 | green P2 (15cm, 20deg toward the blue place; pointed at base | 成功 | 1.90 |  |
| 18 | blue P3 (20cm, 20deg toward the green place; pointed at base | 失敗 | 9.15 | arm board stopped (2nd stop in E0′) during the attempt; located at base 105 on the 2nd sur |
| 19 | green P4 (17cm, 35deg toward the blue place; pointed at base | 成功 | 1.94 |  |
| 20 | blue P5 (20cm, 35deg toward the green place; pointed at base | 失敗 | — | arm board stopped (3rd stop incl. excluded trial 2) during the first grasp; later attempts |

## 2 個（試行 21〜30）

| 試行 | 条件 | 結果 | 分 | 失敗の理由 |
|---|---|---|---|---|
| 21 | Q1: green P3 + blue P2 (A+B) | 失敗 | 4.61 | green placed (1st try); blue at P2 was surveyed at 14.8 cm base 67 but refinement went und |
| 22 | Q2: green P2 + blue P3 (A+B, inner-edge clamp) | 失敗 | — | first grasp of green at P2 missed (143->145), then the arm board stopped (4th stop; 1st af |
| 23 | Q3: green P5 + blue P4 (A+B, inner-edge clamp) | 成功 | 3.14 |  |
| 24 | Q4: green P4 + blue P5 (A+B, inner-edge clamp) | 失敗 | 1.01 | arm board stopped (5th) about 1 min in, while lowering to grasp the green at base 56; run  |
| 25 | Q5: green P1 + blue P4 (A+B+clamp+one-move lowering) | 失敗 | 3.28 | blue at base 56 (P4) missed (143->145) and apparently pushed out of view; green found at b |
| 26 | Q1: green P3 + blue P2 (all changes) | 失敗 | 5.45 | green placed (first try); blue found twice at 13.6–13.8 cm (base 62) but "cannot be graspe |
| 27 | Q2: green P2 + blue P3 (all changes + 1-degree tilt) | 失敗 | 1.01 | arm board stopped (7th) about 1 min in, during the survey — no grasp or lowering had happe |
| 28 | Q3: green P5 + blue P4 (all changes + 1-degree tilt) | 失敗 | 3.01 | blue held when closed (140) but dropped while lifting (144); green placed; then the arm bo |
| 29 | Q4: green P4 + blue P5 (all changes + 1-degree tilt) | 成功 | 2.37 |  |
| 30 | Q5: green P1 + blue P4 (all changes + 1-degree tilt) | 成功 | 3.21 |  |

## やり直し

| 試行 | 条件 | 結果 | 分 | 備考 |
|---|---|---|---|---|
| 5r | 5r: redo of trial 5 — green P5 (20cm, 35deg toward the green | 成功 | 3.31 |  |
| 7r | 7r: redo of trial 7 — green P2 (15cm, 20deg toward the blue  | 成功 | 2.37 |  |
| 12r | 12r: redo of trial 12 — blue P2 (15cm, 20deg toward the blue | 失敗 | 2.17 | blue at P2 not found (3 surveys); diagnosed: blue appears saturation 1.0 but value 0.1–0.2 |
| 12r2 | 12r2: 2nd redo of trial 12 with A+B — blue P2 (15cm, 20deg t | 無効 | 9.12 | the Mac changed its IP address (Wi-Fi, .26 -> .24) during the run; the board HTTP stalled  |
| 12r3 | 12r3: redo of trial 12 with A+B — blue P2 (15cm, 20deg towar | 成功 | 1.97 |  |
| 18r | 18r: redo of trial 18 with A+B — blue P3 (20cm, 20deg toward | 成功 | 2.14 |  |
| 20r | 20r: redo of trial 20 with A+B — blue P5 (20cm, 35deg toward | 成功 | 2.17 |  |
| 24r | 24r: redo of trial 24 with one-move lowering — Q4: green P4  | 成功 | 2.37 |  |
| 21r | 21r: redo of trial 21 — Q1: green P3 + blue P2 (all changes) | 失敗 | 2.51 | green placed (first try, 139/139), then the arm board stopped (6th stop; 1st after one-mov |
| 21r2 | 21r2: 2nd redo of trial 21 — Q1: green P3 + blue P2 (all cha | 成功 | 5.38 |  |
| 22r | 22r: redo of trial 22 — Q2: green P2 + blue P3 (all changes) | 成功 | 2.74 |  |
| 25r | 25r: redo of trial 25 — Q5: green P1 + blue P4 (all changes) | 成功 | 2.51 |  |
| 26r | 26r: redo of trial 26 — Q1: green P3 + blue P2 (all changes) | 成功 | 5.58 |  |
| 27r | 27r: redo of trial 27 — Q2: green P2 + blue P3 (all changes) | 成功 | 2.81 |  |
| 28r | 28r: redo of trial 28 — Q3: green P5 + blue P4 (all changes) | 成功 | 8.32 |  |
