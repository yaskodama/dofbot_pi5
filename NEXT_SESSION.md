# DOFBOT (Xinu + AIPL) — handoff to the next session

Last updated: 2026-09-14 16:10 (end of session)

## The situation in 30 seconds

| Board | What runs on it | Address |
|---|---|---|
| The DOFBOT's Pi 5 | **Xinu** (boots from the USB stick `XINU5`; the Linux SD card has been removed). Arm (I²C 0x15), USB camera (UVC isochronous), fan, AIPL actor `dofbot` | 192.168.3.101 (wired) |
| The other Pi 5 | Linux (Yahboom's SD card). Camera removed | 192.168.3.19 (`yahboom.local`) |
| Mac | Canonical AIPL implementation (OCaml), Xinu simulator aice-avm (:8080) | — |

**The board is flashed with build `Sep 14 2026 12:18:34` (xinu-rpi5 `3b37708`).**
**The latest, not yet flashed, is `d4eac11` (build 15:49:58)** — the version that moves boot-time actor loading + camera start into a dedicated process.
The 12:18 board **may hang its HTTP on every reboot** (happened once with the 12:18 build; UDP/9010 and ping stay alive).
→ **Next time, flash `d4eac11` first** (`make pi5` → copy `kernel_2712.img` to `XINU5` → md5 → power-cycle).

## Usage (the usual steps)

```sh
# Check the version (always after flashing; HTTP answering ≠ rebooted)
curl -s http://192.168.3.101/version | head -1
# Arm (string commands; from the shell, `arm ...`)
curl "http://192.168.3.101/arm/read"
curl "http://192.168.3.101/arm/pose/90/90/90/90/90/30/2000"
# Camera (starts automatically 50 s after boot; if stopped, /cam/start)
curl "http://192.168.3.101/cam?w=160"          # "DW DH SRCW SRCH LEN streaming|idle"
curl "http://192.168.3.101/cam/start?frame=3&fps=10"
# Fan (temperature-following by default; manual with level=, back to automatic with auto=1)
curl "http://192.168.3.101/fan"
# Actor (loaded automatically at boot; if missing, load it)
curl --data-binary @$HOME/dofbot_pi5/aipl/dofbot_arm.aipl http://192.168.3.101/cc
curl "http://192.168.3.101/api/x/"
```


Simulator: `cd ~/projects/aice-avm && ./_build/default/server.exe 8080` (needs `eval "$(opam env)"`) → `http://localhost:8080/#arm-xinu`
(DOFBOT arm window + AIPL program window; the video source is the Xinu camera).

Choreography (simulator model → real robot):
```sh
cd ~/dofbot_pi5/aipl && printf 'load %s\ncompile\n' "$PWD/complex.aipl" > r.repl
cd ~/aios/abclcp && ./src/abclrepl_thread -q -f ~/dofbot_pi5/aipl/r.repl
```
Measured: all 44 replies ok (from the 12:04 build on, with a 100 ms I²C wait and 3 retries, the timeouts are gone).

## What got done today (chronological)

1. On Linux, sorted out the three layers SSH→Python→I²C (report Sections 1–3). Grasping not achieved (the fingers are not visible in the camera).
2. Dropped Linux and moved to Xinu: `device/i2c/rp1i2c.c` (RP1 i2c1) + `system/arm.c` (message protocol) + `/arm/...`.
3. Moved to AIPL: added `remote_call` / `arm_cmd` / execution-position notification (UDP/9011) to the canonical implementation. An `Arm` actor on the board (with `arm_cmd` built in).
4. In the simulator, a DOFBOT arm window (3D model, camera, sliders, model/real switch) and an AIPL program window (highlights the executing line).
5. **UVC camera driver** (xHCI isochronous IN, TRB ring of 512, frame assembly from UVC headers) → 320×240 @10fps. Served as RGB565 in chunks via `/cam?w=&off=`.
6. Fan (RP1 PWM1 ch3, temperature-following), auto-start at boot, automatic arm-board reset, longer I²C wait.
7. Published an 8-page report as the 90th research report on kodamay.org: `reports/2026-09-14_dofbot_xinu_aipl_uvc.pdf`.

## Traps we hit (to avoid repeats)

- **The EP0 transfer ring is shared by all USB devices.** Addressing another device makes every camera control transfer time out → re-address the camera every time streaming starts.
- **If remote_call request IDs always start from 20000, the peer treats them as "retransmissions" and returns the previous answer** → offset them by the boot time.
- **The `pkill -f` pattern matched its own `bash -c` line and killed itself** (camera helper on the Linux Pi) → `pkill -f "^python3 -u /home/pi/cam_service.py"`.
- **The arm board's I²C response exceeds 20 ms while it is talking to the servos.** Right after a move every read fails (writes are ACKed) → 100 ms wait and retries; after 3 total failures, reset the board.
- **Doing long work in the net tick collides with the screen loop and hangs HTTP** → dedicated process (`dofbot_boot_proc`).
- **The latest frame gets replaced while one frame is being fetched in chunks** → snapshot it at off=0 (included in the 12:18 build).
- For 30–60 s right after boot, HTTP is kept waiting by the on-board browser (not a fault).
- Power-cycling the board erases actors in RAM (they are reloaded automatically). Camera streaming stops too (auto-start exists).

## Next moves (candidates)

1. Flash `d4eac11` and confirm HTTP survives 3 reboots.
2. Use camera images from AIPL (built-ins `cam_frame()` / tag detection). A camera window on the HDMI screen.
3. Grasping: needs a camera that watches from outside the arm (move it to the Linux Pi 5 with `cam_service.py`) or a contact sensor. The fingers are not visible in the wrist camera.
4. Split into the 6+1 actor design from the Sept 7 report (6 joints = decision layer, 1 arm = I/O).

## Locations

- Board side: `~/projects/xinu-rpi5` (branch `feat/smp-symmetric`): `device/i2c/rp1i2c.c` `system/arm.c` `device/usb/rp1usb.c` (UVC at the end) `device/genet/rp1fan.c` `loader/main.c` (`dofbot_boot_proc`) `system/tcp_server.c` (`/arm` `/cam` `/fan` `/usb/cam-probe`) `cc/cc.c` (`v_arm_cmd`)
- Canonical implementation: `~/aios/abclcp` (branch `make-src-base`): `src/eval_thread.ml` (`remote_call` `arm_cmd` `trace_pc`) `src/typing_env.ml`
- Simulator: `~/projects/aice-avm` (main): `server.ml` (`/api/arm` model `sim_cmd` UDP/9011) `www/js/xinu.js` (`openArm` `openAiplProgram`)
- AIPL and tools: `~/dofbot_pi5/` (`aipl/complex.aipl` `aipl/dofbot_arm.aipl` `cam_service.py` `arm.py` `dofbot_control_path.tex/pdf`)
- Copy of the report source: `~/kodamay_org_site/kodamay.org/reports-src/2026-09-14_dofbot_xinu_aipl_uvc/report.tex`
- Memory: `project-dofbot-ultra-baremetal-arm` `project-xinu-pi5-uvc-camera` `project-dofbot-pi5-real-arm`

## Addendum (16:10)

- Added a robot-arm section (English and Japanese) and the demo video https://youtu.be/MSeznEtUzes to the xinu-rpi5 README (`0d5dac5`).
- **Fast-forwarded GitHub `main` to the tip of `feat/smp-symmetric`** (no divergence; the previous tip of main was `5887c97`).
  From now on, after pushing to `feat/smp-symmetric`, also run `git push origin feat/smp-symmetric:main` (so the README shows on main).
- All repositories (xinu-rpi5 / abclcp / aice-avm / kodamay-org-web) are committed and pushed. The only uncommitted files in abclcp are build artifacts.

## Addendum (2026-09-26)

- The board is **still on the 12:18 build** (d4eac11 was flashed once but rolled back). Backup: `xinu-rpi5/compile/kernel_2712.img.bak-0914-1218`.
- HTTP looked dead on d4eac11 because Chrome's `#arm-xinu` page and a polling loop kept hammering the board while it was booting. The 12:18 build shows the same symptom and recovers about 1 minute after they stop. **d4eac11 has not been evaluated.**
- Re-evaluation procedure: close the simulator page → `lsof -nP -i @192.168.3.101` is empty → flash → a single `/version` request every 10 seconds.
- The 22 moves of complex.aipl: simulator 22/22, real robot 22/22 (with the page closed, I²C fail=0).

## Addendum 2 (2026-09-26 13:25) d4eac11 re-evaluated (the board is now on d4eac11)

- Booted with no flood → HTTP answers after about 40 s and does not hang (the goal was achieved).
- **Bug ①** The fan's temperature tracking (`rp1fan_thermal_tick`) was removed from the net tick and never moved anywhere → `fan level=-1`.
- **Bug ②** `dofbot_boot_proc` does not load the actor or start the camera even after 2+ minutes (unknown whether proc_create failed or it is stuck inside; there is no /ps-like instrument).
- Workaround (needed on every boot): `/fan?level=75` → `POST /cc dofbot_arm.aipl` → `/cam/start?frame=3&fps=10`. With this, simulator 22/22, real robot 22/22, I²C fail=0.
- Next: put the fan tick back in the net tick + log each stage of the boot proc to uart/a ring buffer viewable via `/bootlog`, then fix it.

## Addendum 3 (2026-09-27) Sorting by color (sort.aipl)

- `aipl/sort.aipl`: before grasping, ask for the color in the "look at the grasp spot" pose (90 75 15 35); green → base 150° (right), blue → 30° (left), no color → back to 90°. Simulator model first, then the real robot. `r_sort.repl`.
- `color_service.py` (Mac, the "Camera" on UDP/9012, HTTP/8091): computes the camera pose from the arm pose by FK (top of the wrist, 3.2 cm from the finger axis, 60° field of view),
  and classifies only inside the region (ROI) where the grasp spot (a 3.5 cm cube under the P_CENTER fingertip) appears. A color covering ≥30% of the region counts. Real images are rotated 180° (--no-rot180).
  Images are sent by the aice-avm window (/simframe = CG camera, /realframe = real camera frames received from the board). The board is queried directly only when no window is open.
- aice-avm `www/js/xinu.js`: CG cube (grasp/carry/place), CG wrist camera, central Camera window (CG and real side by side with the ROI box), color-recognition-rate bar under the AIPL window.
  `/sim?c=green|blue` changes the CG cube's color and puts it back.
- Unconfirmed: whether the real-robot ROI box matches the actual grasp spot (there was no cube on the real table). Place a cube and see if it overlaps the box in the Camera window. If off, adjust --fov / CAM_UP.
- The window's camera fetch interval was lowered to 250 ms (at 50 ms the board's HTTP clogged and finally the whole board went down).
- The board is still on d4eac11. Every boot needs `/fan?level=75` → `POST /cc dofbot_arm.aipl` → `/cam/start?frame=3&fps=10`.

## Addendum 4 (2026-09-27) Shoot from an offset, then grasp

- The camera is on the **top** of the wrist (the -cross(d3,l) side). The earlier model had it on the bottom → fixed the sign in xinu.js and color_service.py.
- The cube is 17 cm in front of the base (CUBE.x / CUBE_X). Poses solved by IK (hand tilt 165°):
  look 90 84 3 18 (camera axis passes through the cube center, distance 12 cm) → approach 90 59 35 10 → grasp 90 39 28 38 (fingertips 2 cm beyond the center).
- color_service's real mode now waits for "the first frame arriving after the query" before classifying (a stale frame from before the arm stopped had given 19.5%).
- Results: simulator green 87.9% → right 150° (confirmed via cube_at in /stat that the CG cube was grasped and placed at (0.085,-0.148)).
  Real robot blue 100% (light blue, hue 195°) → left 30°. Whether the real robot actually gripped it is unconfirmed (needs visual check).

## Addendum 5 (2026-09-27) Search, grasp, and retry until gripped

- The Xinu camera image is **not rotated** (measured by moving the base/arm). The "180°" from the Linux days does not apply. color_service keeps the old behavior behind --rot180.
- locate.py: shoot in the look pose → back-project the centroid of the color blob onto the table → re-aim, until it converges (60% correction; the real camera's field of view seems narrower than 60°).
  If nothing is found, look at 13/17/21 cm × 0/±20° in turn. The arm is moved over UDP (the dofbot actor, with retransmission), and joint angles are read back to confirm.
- sort.aipl: locate → get base/pre/grasp → grip → lift and locate with the fingers still closed; if the cube is still on the table, grip again (up to 10 times).
- Fingers go up to 110 (right after closing fully at 135 the arm board stopped responding; it did not recover until power-cycled, and the Pi 5 also rebooted).
- Results: the simulator succeeds in 1–2 tries. On the real robot the table was empty on the 6th try (whether it really gripped is not visually confirmed).

## Addendum 6 (2026-09-28) Dimensions in one place, dimension lines in the CG

- `~/dofbot_pi5/geometry.json` is the single source of dimensions (base_h, H, L1, L2, L3, LG, cam_along, cam_up, fov, cube). Each value has a src (URDF / guess / measured).
  color_service reads it (GET/POST :8091/geo), and locate.py's IK and back-projection as well as xinu.js's CG, CG camera and dimension lines all use the same values.
- Simulator DOFBOT window: 「寸法」 ("Dimensions") shows dimension lines (yellow = URDF, orange dashed = guess, green = measured); 「寸法を編集」 ("Edit dimensions") lets you enter cm and save.
- Guesses (not yet measured): base 6.6, fingers 6.0, wrist → camera 6.25, finger axis → camera center 3.2, field of view 60°, cube 3.5 (cm). Need measuring.
- Real-robot grasp height unsolved: by the model's calculation 2.3 cm hits the table, 4.5 cm does not reach, and 3.4 cm also fails to grip. Measuring LG and L3 should fix it.
- The arm board (STM8) stops responding after a grasp motion (2nd time). Power-cycling the arm brings it back.
- The aice-avm server had stopped overnight. Before running, check :8080, UDP 9010, and cg_age in /stat.

## Addendum 7 (2026-09-28 midday) Finger measurements, grasp check, suspected board crash

- Finger (servo 6) measured with a ruler, 7 steps: 30,50→6.2 70→5.8 90→5.2 110→4.2 131→3.0 135→2.8 cm. Stored as grip_cal in geometry.json.
  A 3 cm cube is gripped at 135 (at 110 the opening is 4.2 cm and was not touching).
- Grasp check = servo 6 readback ≤ 133 after closing at 135 (stopped by the object). Empty gives 135. held(real) returned no, matching the measured 135.
- The real robot grasps 1° to the left of the computed position → real_base_offset=+1. Finger length LG=8.3 cm (estimated from the height at which it hit the table), grasp height TIP_Y=1.5 cm.
- On the arm board (STM8) stalls: strong suspicion that **when Xinu's /arm read gets "? on all 6 axes" 3 times in a row it sends a board reset, and the board then stays down until power-cycled**
  ("(board reset)" right before it stops). Mitigation (Mac side): at most 2 reads, 1.5 s apart, no reads during lower. The root fix is to remove the automatic reset from system/arm.c and reflash.
- When the board's UDP endpoint returned empty replies, reloading the arm actor via POST /cc brought it back.
- If Chrome keeps an idle connection (no request) open to the board's :80, Xinu's HTTP clogs (quitting Chrome recovers it immediately).

## Addendum 8 (2026-09-29) Second success (green cube)

- Ran sort.aipl with a new green cube; the real robot gripped it on the 6th attempt and placed it in the right drop zone (base 150°) (Prof. Kodama visually confirmed success).
  Log: `aipl/sort_run20.log`. Attempts 1, 2 and 5 chased small blue blobs (cables etc.) covering only 1.7–7.7% of the detection region and missed;
  each time the finger readback of 135 correctly judged "not gripped". On the attempts that gripped, the readback was 133 (equal to the threshold, both times).
- Fix: color blobs smaller than 1.5% of the image are not treated as cubes (locate.py, bcb6c96). Not yet run since this fix.
- That makes 2 real-robot successes (9/29 blue = run19, green = run20).

## Addendum 9 (2026-09-29 afternoon) Carried both green and blue in one run

- Ran 15 times (13 with 2 cubes, 2 with 1); on the last one, sort2_run13, the real robot carried both (visually confirmed success). Copy in `snapshots/2026-09-29_sort2_ok/`.
- The "placed 2" on runs 4 and 9 were wrong (treated err as a color / counted open fingers at 40 as gripped).
- Arm-board stalls still happened after the automatic reset was removed (cause unknown).
