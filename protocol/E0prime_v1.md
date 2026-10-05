# E0′ Baseline performance of the real robot — Protocol v1 (2026-09-29, frozen before seeing results)

## Purpose
Before the main experiment (E1), measure the full-success rate, elapsed time, distribution of grasp checks, and arm-board stalls for the color-sorting task, using repeated trials under fixed conditions.

## Frozen conditions
- Software: dofbot_pi5 (the same commit as this protocol), aice-avm 85da963 or later, Xinu `Sep 29 2026 09:57:23` (xinu-rpi5 3bc7bfb)
- Choreography: `aipl/sort_real.aipl` (only the real-robot part of `sort.aipl`; the simulator model is not run)
- Finger close 145, grasp check readback 120–141, fingertip 1.2 cm above the table, search 2 rows × 4 spots (14–23 cm, ±45°), search arm move 2.5 s
- Cubes 3 cm on a side (green, blue). Only white paper on the table (no other colored objects). Drop zones at 17 cm, base 150° (right, green) / 30° (left, blue)
- Arm power adapter: the current one (no higher-capacity replacement available)

## Trials
- 1 cube: 20 trials. 5 positions × 2 colors (green, blue) × 2 repetitions. Positions (distance from the base axis, direction from straight ahead; left = base < 90°):
  P1 17 cm front / P2 15 cm left 20° / P3 20 cm right 20° / P4 17 cm left 35° / P5 20 cm right 35°
  Order as in the table below (decided in advance).
- 2 cubes: 10 trials. Green and blue placed in the following pairs (left/right as seen from the front):
  Q1 green P3, blue P2 / Q2 green P2, blue P3 / Q3 green P5, blue P4 / Q4 green P4, blue P5 / Q5 green P1, blue P4, 2 times each
- 1 trial = place the cube(s) → run `sort_real.aipl` once (at most 30 trials) → check the drop zones with the camera → put the cubes back

## Records (`data/e0prime/trials.jsonl`, one line per trial)
Trial number, condition (1 or 2 cubes, colors and positions), start and end time, number placed (as reported by the program), colors seen at the drop zones (camera),
number of grasp attempts, finger readback (right after closing, after lifting), whether the arm board stalled, operator intervention.

## Definition of success
Every cube placed in the trial is in the drop zone of the correct color (checked with the camera; if it disagrees with visual inspection, visual inspection wins).

## Pass criteria (decided before seeing results, approved by Prof. Kodama 2026-09-29)
1-cube full-success rate ≥ 0.8 (16 or more of 20), 2-cube full-success rate ≥ 0.7 (7 or more of 10), arm-board stalls ≤ 1 over the 30 trials.
If not met, classify the failures, fix exactly one thing, and run the same number of trials again. If the second round also fails, go to the fallback (withdrawal) line.

## Order of the 1-cube trials (decided in advance)
| Trial | Color | Position |
|---|---|---|
| 1 | green | P1 | 
| 2 | blue | P2 |
| 3 | green | P3 |
| 4 | blue | P4 |
| 5 | green | P5 |
| 6 | blue | P1 |
| 7 | green | P2 |
| 8 | blue | P3 |
| 9 | green | P4 |
| 10 | blue | P5 |
| 11–20 | repeat 1–10 | |

## Changes after freezing (before trial 1)
- 2026-09-29 15:40: every HTTP connection to the board is closed with RST (`locate.http_get`), because connections closed on timeout were stalling Xinu's HTTP.
  Conditions (choreography, thresholds, dimensions) unchanged.
- 2026-09-29 15:55: fixed a missing declaration of `var a` in `sort_real.aipl` (the first run of trial 1 stopped at load time and the robot did not move; not counted as a trial).
- 2026-09-29 16:25: trial 2 is invalid because the cube was placed straight ahead (redone on Prof. Kodama's instruction; the 1 arm-board stall is counted).
  POSTs to the board (reloading the actor) are also closed with RST. A helper checks the actor's response every 30 s and reloads it. Conditions unchanged.
- 2026-09-29 16:40 (after trial 2): the timestamp of real-robot images changed from "time the fetch finished" to "time the board captured the frame".
  This was why the drop-zone check came out left/right reversed. It affects only image selection for search and drop-zone checks; choreography, thresholds and dimensions unchanged.
- 2026-09-29 16:50 (after trial 3): a color blob spanning 85% or more of the image both vertically and horizontally is not treated as a cube (a green book beside the left drop zone was classified as green).
  The "green" reported at the left drop zone in the drop-zone check was this error (trial 3 was judged by the green in the right drop zone). The green book was removed from the table.
- 2026-09-29 17:10: on Prof. Kodama's instruction, trial 5 (failure) is redone as 5r ("the desk may have slid"). Trial 5 stays recorded as a failure,
  and the totals are reported both ways: "count 5 as a failure" and "replace with 5r". From now on, any trial disturbed by external causes is treated the same way, whether it succeeded or failed.
- 2026-09-29 19:20: after finishing the 20 one-cube trials, on Prof. Kodama's instruction the failed trials 7, 12, 18, 20 are redone as 7r, 12r, 18r, 20r.
  The results of the original 20 trials (15/20 full success, 3 arm-board stalls) are reported as-is, and the totals with redos substituted are listed separately.
- 2026-09-29 20:05 (during the redos, two fixes decided by Prof. Kodama; recorded as deviations from the protocol):
  A. Lower brightness bound for blue classification 0.2 → 0.06 (blue at P2 appears with saturation 1.0 and value 0.1–0.2 and fell outside the classifier; the cause of 12 and 12r).
  B. Once a grasp is confirmed, loosen the fingers from 145 → 140 while carrying (hypothesis: the current drawn while pressing is what stalls the arm board; unverified).
  The subsequent redos (12r2, 18r, 20r) use these conditions. The totals state explicitly that the conditions differ from the original 20 trials.
- 2026-09-29 21:20: the helper goes quiet for 15 s after 3 consecutive camera-fetch failures (the board's HTTP stalls every time the Mac's Wi-Fi address changes; conditions unchanged).
- 2026-09-29 22:00: the 10 two-cube trials (trials 21–30) are run under conditions A+B (Prof. Kodama's instruction). Each position is indicated by pointing the arm at it, one at a time, and the cube is placed there.
- 2026-09-29 22:20 (after trial 21): during the closing-in stage, if the distance drops below 14 cm, clamp it at 14.1 cm and still go for the grasp (do not give up). After placing one cube, finish only after two consecutive not-found results (not after one). Trial 21 failed under the earlier conditions.
- 2026-09-29 22:50 (after trial 24): all 5 arm-board stalls happened during or right after the "lowering" step (about 8 commands of 0.5 cm each at 0.6 s intervals), so lowering was changed to a single command (2 s). Later trials use this condition.
- 2026-09-29 23:00 (after trial 26): search the hand tilt of the grasp pose in 1° steps instead of 5° steps (there was a gap in reachable poses at 13.6–14.2 cm, so a blue cube that had been found was judged ungraspable).
