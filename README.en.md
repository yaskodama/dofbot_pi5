# dofbot_pi5

[日本語](README.md) | English

Mac-side tools and choreography for running the Yahboom DOFBOT (6-axis, Raspberry Pi 5 edition) on **Embedded Xinu + AIPL**.
The Xinu side (I²C arm driver, UVC camera) lives in [xinu-rpi5](https://github.com/yaskodama/xinu-rpi5),
and the simulator (CG arm, cubes, wrist camera, PLAN overlay) lives in [aice-avm](https://github.com/yaskodama/aice-avm).

## Video

[![September 14, 2026 (YouTube)](https://img.youtube.com/vi/MSeznEtUzes/hqdefault.jpg)](https://www.youtube.com/watch?v=MSeznEtUzes)

https://www.youtube.com/watch?v=MSeznEtUzes

## Files

| File | Contents |
|---|---|
| `aipl/sort.aipl` | Finds a cube with the wrist camera, grasps it, and places green cubes on the right and blue cubes on the left. The same program runs first in the simulator, then on the real robot |
| `aipl/dofbot_arm.aipl` | The arm actor loaded onto the board (POST /cc) |
| `color_service.py` | The "Camera" and "Plan" nodes running on the Mac (UDP 9012 / HTTP 8091): color classification, search, lowering, grasp check, PLAN |
| `locate.py` | Inverse kinematics, back-projection from the camera image onto the table, cube search, and stepwise lowering |
| `geometry.json` | The single source of dimensions (each with its source: URDF / estimate / measured). The CG and the inverse kinematics use the same values |
| `snapshots/2026-09-29_sort_ok/` | The complete set of files and the procedure from the run that succeeded on the real robot (README.md, in Japanese) |
| `NEXT_SESSION.md` | History and handoff notes (in Japanese) |
| `aipl/sort_run*.log` | Run logs (the evidence for Section 7.4 of Paper ①) |

For how to run it, see `snapshots/2026-09-29_sort_ok/README.md` (in Japanese).
