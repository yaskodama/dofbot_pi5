# E0′ Baseline performance of the real robot — Results (2026-09-29 to 30)

Protocol: `protocol/E0prime_v1.md` (fixed before seeing results; mid-course changes appended with timestamps). Per-trial records, one line each: `trials.jsonl`.

## Totals

| | Full success | Pass criterion |
|---|---|---|
| 1 cube (original 20 trials) | 15/20 = 0.75 | ≥ 0.8 → fail |
| 2 cubes (original 10 trials, conditions changed 3 times mid-course) | 3/10 = 0.3 | ≥ 0.7 → fail |
| Arm-board stalls (all 46 runs) | 8 | ≤ 1 → fail |

Redos (on Prof. Kodama's instruction, after seeing results): 15 runs, 12 successes. Not used for estimating the success rate.

Grasp check (readback ≤141 after closing at 145): grasped 138–140, missed 143–145; every case was classified correctly.

## 1 cube (trials 1–20)

| Trial | Condition | Result | Min | Reason for failure |
|---|---|---|---|---|
| 1 | green P1 (17cm front) | success | 2.97 |  |
| 2 | blue P2 (15cm, 20deg toward the left place) — redo | success | 1.80 |  |
| 3 | green P3 (20cm, 20deg toward the right place; pointed at bas | success | 2.10 |  |
| 4 | blue P4 (17cm, 35deg toward the blue place; pointed at base  | success | 1.80 |  |
| 5 | green P5 (20cm, 35deg toward the green place; pointed at bas | failure | 4.81 | grasp missed twice (readback 143->145): fingers landed beyond (far side of) the cube at 20 |
| 6 | blue P1 (17cm front; pointed at base 90) | success | 1.77 |  |
| 7 | green P2 (15cm, 20deg toward the blue place; pointed at base | failure | 1.80 | no grasp attempt: surveyed at 13.6 cm, base 56 (pointed 15 cm, base 70); refinement put it |
| 8 | blue P3 (20cm, 20deg toward the green place; pointed at base | success | 2.17 |  |
| 9 | green P4 (17cm, 35deg toward the blue place; pointed at base | success | 2.17 |  |
| 10 | blue P5 (20cm, 35deg toward the green place; pointed at base | success | 2.20 |  |
| 11 | green P1 (17cm front; pointed at base 90) | success | 1.87 |  |
| 12 | blue P2 (15cm, 20deg toward the blue place; pointed at base  | failure | 2.27 | no grasp attempt: 3 surveys found nothing in reach (glimpses 2, 2, 0); P2 (15 cm) at the i |
| 13 | green P3 (20cm, 20deg toward the green place; pointed at bas | success | 1.97 |  |
| 14 | blue P4 (17cm, 35deg toward the blue place; pointed at base  | success | 2.24 |  |
| 15 | green P5 (20cm, 35deg toward the green place; pointed at bas | success | 2.17 |  |
| 16 | blue P1 (17cm front; pointed at base 90) | success | 2.17 |  |
| 17 | green P2 (15cm, 20deg toward the blue place; pointed at base | success | 1.90 |  |
| 18 | blue P3 (20cm, 20deg toward the green place; pointed at base | failure | 9.15 | arm board stopped (2nd stop in E0′) during the attempt; located at base 105 on the 2nd sur |
| 19 | green P4 (17cm, 35deg toward the blue place; pointed at base | success | 1.94 |  |
| 20 | blue P5 (20cm, 35deg toward the green place; pointed at base | failure | — | arm board stopped (3rd stop incl. excluded trial 2) during the first grasp; later attempts |

## 2 cubes (trials 21–30)

| Trial | Condition | Result | Min | Reason for failure |
|---|---|---|---|---|
| 21 | Q1: green P3 + blue P2 (A+B) | failure | 4.61 | green placed (1st try); blue at P2 was surveyed at 14.8 cm base 67 but refinement went und |
| 22 | Q2: green P2 + blue P3 (A+B, inner-edge clamp) | failure | — | first grasp of green at P2 missed (143->145), then the arm board stopped (4th stop; 1st af |
| 23 | Q3: green P5 + blue P4 (A+B, inner-edge clamp) | success | 3.14 |  |
| 24 | Q4: green P4 + blue P5 (A+B, inner-edge clamp) | failure | 1.01 | arm board stopped (5th) about 1 min in, while lowering to grasp the green at base 56; run  |
| 25 | Q5: green P1 + blue P4 (A+B+clamp+one-move lowering) | failure | 3.28 | blue at base 56 (P4) missed (143->145) and apparently pushed out of view; green found at b |
| 26 | Q1: green P3 + blue P2 (all changes) | failure | 5.45 | green placed (first try); blue found twice at 13.6–13.8 cm (base 62) but "cannot be graspe |
| 27 | Q2: green P2 + blue P3 (all changes + 1-degree tilt) | failure | 1.01 | arm board stopped (7th) about 1 min in, during the survey — no grasp or lowering had happe |
| 28 | Q3: green P5 + blue P4 (all changes + 1-degree tilt) | failure | 3.01 | blue held when closed (140) but dropped while lifting (144); green placed; then the arm bo |
| 29 | Q4: green P4 + blue P5 (all changes + 1-degree tilt) | success | 2.37 |  |
| 30 | Q5: green P1 + blue P4 (all changes + 1-degree tilt) | success | 3.21 |  |

## Redos

| Trial | Condition | Result | Min | Notes |
|---|---|---|---|---|
| 5r | 5r: redo of trial 5 — green P5 (20cm, 35deg toward the green | success | 3.31 |  |
| 7r | 7r: redo of trial 7 — green P2 (15cm, 20deg toward the blue  | success | 2.37 |  |
| 12r | 12r: redo of trial 12 — blue P2 (15cm, 20deg toward the blue | failure | 2.17 | blue at P2 not found (3 surveys); diagnosed: blue appears saturation 1.0 but value 0.1–0.2 |
| 12r2 | 12r2: 2nd redo of trial 12 with A+B — blue P2 (15cm, 20deg t | invalid | 9.12 | the Mac changed its IP address (Wi-Fi, .26 -> .24) during the run; the board HTTP stalled  |
| 12r3 | 12r3: redo of trial 12 with A+B — blue P2 (15cm, 20deg towar | success | 1.97 |  |
| 18r | 18r: redo of trial 18 with A+B — blue P3 (20cm, 20deg toward | success | 2.14 |  |
| 20r | 20r: redo of trial 20 with A+B — blue P5 (20cm, 35deg toward | success | 2.17 |  |
| 24r | 24r: redo of trial 24 with one-move lowering — Q4: green P4  | success | 2.37 |  |
| 21r | 21r: redo of trial 21 — Q1: green P3 + blue P2 (all changes) | failure | 2.51 | green placed (first try, 139/139), then the arm board stopped (6th stop; 1st after one-mov |
| 21r2 | 21r2: 2nd redo of trial 21 — Q1: green P3 + blue P2 (all cha | success | 5.38 |  |
| 22r | 22r: redo of trial 22 — Q2: green P2 + blue P3 (all changes) | success | 2.74 |  |
| 25r | 25r: redo of trial 25 — Q5: green P1 + blue P4 (all changes) | success | 2.51 |  |
| 26r | 26r: redo of trial 26 — Q1: green P3 + blue P2 (all changes) | success | 5.58 |  |
| 27r | 27r: redo of trial 27 — Q2: green P2 + blue P3 (all changes) | success | 2.81 |  |
| 28r | 28r: redo of trial 28 — Q3: green P5 + blue P4 (all changes) | success | 8.32 |  |
