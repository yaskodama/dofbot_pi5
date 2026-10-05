#!/usr/bin/env python3
# color_service.py — "Camera" node running on the Mac (color classification). Speaks the same messages as cam_service.py.
#
#   Q <reqid> Camera color real s1 s2 s3 s4 -> R <reqid> green|blue|none   (grab one frame from the Xinu board's wrist camera /cam and classify)
#   Q <reqid> Camera color sim  s1 s2 s3 s4 -> R <reqid> green|blue|none   (classify the CG wrist camera image)
#     s1..s4 are the arm pose (servo angles) while "looking".
#   Q <reqid> Camera locate sim|real [grip] [green|blue|any] -> R <reqid> green|blue|none
#     grip: fingers during search (default 30=open). Given a color, search only for that color (so after placing one, only the remaining color is searched)
#     Find a cube (locate.py): shoot in look pose -> back-project the color blob centroid onto the table -> re-aim the camera, until converged.
#     color_service moves the arm (sim: 127.0.0.1:8080/api/arm/sim, real: the board's /arm/pose).
#   Q <reqid> Camera lower <sim|real> here <grip> | <base> <r_cm> <grip> -> R <reqid> ok <fingertip height cm>
#     Lower the fingertip from 5 cm above the table in 0.5 cm steps, reading back angles at each step. If a joint deviates 3° from the command, treat it
#     as hitting the table, raise 0.8 cm and stop (real robot). Sim model goes down to 2.3 cm.
#   Q <reqid> Plan push <sim|real> <command…>   -> R <reqid> <number>     (push the command about to run onto PLAN)
#   Q <reqid> Plan done <number> <result…>        -> R <reqid> ok          (write back the result; ok… means success)
#   Q <reqid> Plan reset                      -> R <reqid> ok
#     PLAN is overlaid on the Xinu simulator CG (GET /plan). locate / lower push their own arm moves too.
#     Commands sent from the window's buttons/sliders are also pushed over HTTP (GET /plan/push?where=&cmd=, /plan/done?i=&r=, /plan/reset).
#   Q <reqid> Camera held <sim|real>          -> R <reqid> yes | no   (is it gripped: finger readback; angle shows in PLAN)
#   Q <reqid> Camera get <sim|real> base|look|pre|grasp|where -> R <reqid> "84" / "91 4 1" … (result of the previous locate)
#   H <reqid>                    -> A <reqid>
#   A resend with the same (sender, reqid) gets the previous answer. Resends during classification are not answered (remote_call will send again).
#
# ★ The camera sits above the fingers (top face of the wrist link, 3.2 cm from the finger axis) and cannot see between the fingers.
#   So sort.aipl shifts the arm to aim the camera axis at the cube and shoots, then aligns the finger axis with the cube and grips.
#   Classification computes camera position and direction from the pose by forward kinematics,
#   projects where the cube (17 cm in front of the base, a 3.5 cm cube on the table) appears in the image,
#   and classifies only inside that box (ROI). The CG camera is drawn with the same geometry and FOV.
#   The Xinu camera image is not rotated (measured by moving base and arm and watching the cube's direction, 2026-09-27).
#   Shots taken under Linux were rotated 180°; use --rot180 for those.
#
# Classification (same function for real and sim): convert ROI pixels to HSV; among pixels with enough saturation and value,
#   count hue 75–165° as green and 190–260° as blue. If the larger count is >= 30% of the ROI, that color, else none
#   (doesn't react to thin cables or edge colors).
#
# HTTP (default 8091, CORS enabled):
#   POST /simframe?w=80&h=60   body = raw RGB pixels, 1 byte each. The Xinu simulator's DOFBOT window sends the CG camera image
#   POST /realframe?w=160&h=120 same format. The window sends the real camera image it got from the board (if within 2 s, the board isn't asked)
#   GET  /sim?c=green|blue     set the CG cube color and have it re-placed (the window follows cube in /stat)
#   GET  /stat                 latest classification (JSON). Read by the simulator's "color recognition rate" bar
#   GET  /geo, POST /geo       dimensions (geometry.json). Simulator CG and dimension lines, and the IK/back-projection here, share these values
#   GET  /last                 latest classification (one line)
#
# Start: python3 color_service.py [--board 192.168.3.101] [--port 9012] [--http 8091]
import socket, time, argparse, threading, colorsys, urllib.request, urllib.parse, json, math, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate as loc
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ap = argparse.ArgumentParser()
ap.add_argument('--board', default='192.168.3.101')
ap.add_argument('--port', type=int, default=9012)
ap.add_argument('--http', type=int, default=8091)
ap.add_argument('--rot180', action='store_true', help='the real image is rotated 180 deg (Linux capture was; the Xinu UVC driver is not — measured 2026-09-27)')
a = ap.parse_args()

lock = threading.Lock()
RING = collections.deque(maxlen=40)          # recent images (time, 'real'|'sim', (w,h,px), sim-model joint angles or None). For "glimpses" during moves
state = {'last': '-', 'simframe': None, 'simframe_t': 0.0, 'realframe': None, 'realframe_t': 0.0,
         'cube': {'color': 'green', 'seq': 0},
         'stat': {'seq': 0, 'mode': '-', 'answer': '-', 'green': 0, 'blue': 0, 'need': 30, 'max_v': 0, 'why': '', 'roi': None}}


# ---- Geometry: arm and camera dimensions are in geometry.json (read by locate.py; xinu.js CG uses the same values via /geo) ----
CUBE_X = 0.17                            # where the cube is placed: 17 cm forward of the base axis (same as CUBE.x in xinu.js)
NEED = 30                                # what % of the ROI must be one color to call it that color


def fk(s):
    r = math.radians
    A1 = r(90 - s[1]); A2 = A1 + r(90 - s[2]); A3 = A2 + r(90 - s[3]); yaw = r(s[0] - 90)
    f = (math.cos(yaw), 0.0, -math.sin(yaw)); l = (math.sin(yaw), 0.0, math.cos(yaw))
    d = lambda A: (f[0] * math.sin(A), math.cos(A), f[2] * math.sin(A))
    add = lambda p, v, k: tuple(p[i] + v[i] * k for i in range(3))
    P1 = (0.0, loc.H0, 0.0); P2 = add(P1, d(A1), loc.L); P3 = add(P2, d(A2), loc.L)
    P5 = add(P3, d(A3), loc.L3); PG = add(P5, d(A3), loc.LG)
    return dict(l=l, P3=P3, PG=PG, d3=d(A3))


def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def dot(a, b): return sum(a[i] * b[i] for i in range(3))
def unit(v): n = math.sqrt(dot(v, v)); return tuple(x / n for x in v)


def roi_for(pose, W, H, rot180):
    """Box (u0, v0, u1, v1) that the cube at the grasp spot occupies in the camera image (W x H) for pose. None if not visible"""
    cube = (CUBE_X, loc.CUBE / 2, 0.0)                         # placement spot is straight ahead of base at 90°
    k = fk(pose); n3 = unit(cross(k['l'], k['d3']))          # camera "up" = direction of the wrist top face
    c = tuple(k['P3'][i] + k['d3'][i] * loc.CAM_ALONG + n3[i] * loc.CAM_UP for i in range(3))
    f = (W / 2) / math.tan(math.radians(loc.FOV / 2))
    us, vs = [], []
    for i in range(8):
        p = (cube[0] + (loc.CUBE / 2 if i & 1 else -loc.CUBE / 2), cube[1] + (loc.CUBE / 2 if i & 2 else -loc.CUBE / 2),
             cube[2] + (loc.CUBE / 2 if i & 4 else -loc.CUBE / 2))
        d = tuple(p[j] - c[j] for j in range(3)); z = dot(d, k['d3'])
        if z <= 0.01:
            return None
        us.append(W / 2 + f * dot(d, k['l']) / z); vs.append(H / 2 - f * dot(d, n3) / z)
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    if rot180:
        u0, u1, v0, v1 = W - u1, W - u0, H - v1, H - v0
    u0, v0, u1, v1 = max(0, int(u0)), max(0, int(v0)), min(W, int(math.ceil(u1))), min(H, int(math.ceil(v1)))
    return (u0, v0, u1, v1) if u1 - u0 >= 2 and v1 - v0 >= 2 else None


HTTP_LOCK = threading.Lock()                 # the board's HTTP handles one at a time; queue requests from the nodes into a single line
loc.HTTP_LOCK = HTTP_LOCK                    # locate.py (fallback capture, actor reload) uses the same queue


def get(url, tries=6):
    for _ in range(tries):             # board HTTP is one at a time; empty replies and timeouts happen, so retry
        try:
            with HTTP_LOCK:            # issuing 2 at once overwhelmed the board's accept and stopped all HTTP (2026-09-29)
                b = loc.http_get(url, 5)   # always close with RST when done (timed-out connections stalled the board's HTTP)
            if b:
                return b
        except Exception:
            pass
        time.sleep(0.5)
    return b''


def grab_real():
    """One real-robot frame. Use the image the simulator window got from the board and sent us (/realframe) if it is fresh
    (board HTTP is one at a time, so don't compete with the window). Otherwise fetch 80x60 straight from the board"""
    # wait for a frame that arrived after the request (don't classify an old frame from before the arm stopped)
    asked, fresh = time.time(), False
    while time.time() - asked < 5:
        with lock:
            f, t = state['realframe'], state['realframe_t']
        if f is not None and t >= asked + 0.3:
            return f, ''
        fresh = fresh or (f is not None and time.time() - t < 2)     # the window is open
        if not fresh and time.time() - asked > 1:
            break                                                    # no window -> ask the board directly
        time.sleep(0.05)
    return grab_board()


def fetch_board_frame(W=160):
    """One frame from the board's /cam (no waiting). off=0 makes it capture, then fetch the rest. -> (w, h, [(r,g,b) 0..1]) or None"""
    base = 'http://%s' % a.board
    t_cap = time.time()                              # the board captures the frame (off=0) around now
    hdr = get('%s/cam?w=%d&t=%d' % (base, W, time.time() * 1000), tries=2).decode('ascii', 'ignore').split()
    if len(hdr) >= 6 and hdr[5] == 'idle':           # after a board reboot the camera is stopped -> make it start streaming
        get('%s/cam/start?frame=3&fps=10' % base, tries=1)
        return None
    if len(hdr) < 6 or hdr[5] != 'streaming':
        return None
    dw, dh = int(hdr[0]), int(hdr[1])
    total, buf = dw * dh * 2, b''
    while len(buf) < total:
        part = get('%s/cam?w=%d&off=%d&t=%d' % (base, W, len(buf), time.time() * 1000), tries=2)
        if not part:
            return None
        buf += part
    px = []
    for k in range(dw * dh):
        v = buf[2 * k] | (buf[2 * k + 1] << 8)
        px.append((((v >> 11) & 31) / 31.0, ((v >> 5) & 63) / 63.0, (v & 31) / 31.0))
    with lock:
        RING.append((t_cap, 'real', (dw, dh, px), None))
    return dw, dh, px, t_cap


def glimpses_between(kind, t0, t1, prev, target, ms):
    """Images captured during [t0, t1] while the arm moved from prev to target (over ms), and the pose at that time.
    Sim model: actual joint angles attached to the image; real robot: estimate interpolated by time"""
    out = []
    with lock:
        frames = [f for f in RING if f[1] == kind and t0 < f[0] < t1]
    for t, _, img, ang in frames:
        if ang and len(ang) >= 4:
            pose = ang[:4]
        else:
            k = min(1.0, max(0.0, (t - t0) / (ms / 1000.0)))
            pose = [p + (q - p) * k for p, q in zip(prev, target)]
        out.append((img, pose))
    return out


def cam_loop():
    """Keep capturing the board camera (this is the only connection to the board).
    Previously the simulator window (Chrome) fetched from the board's :80 directly, and Chrome repeatedly held open request-less connections
    that stalled Xinu's single-threaded HTTP. The window now reads /realframe.bin from here."""
    next_check = 0
    fails = 0
    while True:
        if time.time() >= next_check:            # every 30 s check the arm actor answers; reload it if not (e.g. after a board reboot)
            next_check = time.time() + 30
            try:
                v = loc.arm_udp('ver', tries=2)
                if not v.startswith('board version'):
                    print('  arm actor not answering (%r) — reload' % v, flush=True)
                    loc.reload_actor()
            except Exception:
                pass
        try:
            f = fetch_board_frame(160)
        except Exception:
            f = None
        if f:
            # Timestamp = when the board captured (start of fetch). Using the fetch-end time treated images from before/during the arm move
            # as "after arrival" and confused the drop-off check and position calculation (2026-09-29)
            with lock:
                state['realframe'], state['realframe_t'] = f[:3], f[3]
        fails = 0 if f else fails + 1
        if fails >= 3:                              # after consecutive failures stay quiet for 15 s (continued requests keep the board's HTTP from recovering)
            print('  board HTTP not answering — back off 15 s', flush=True)
            time.sleep(15); fails = 0
        else:
            time.sleep(0.8 if f else 3.0)            # 0.3 s clogged the board's HTTP


def grab_board():
    """One 80x60 frame from the Xinu board. RGB565 little-endian -> (w, h, [(r,g,b) 0..1])"""
    base, W = 'http://%s' % a.board, 80
    hdr = get('%s/cam?w=%d&t=%d' % (base, W, time.time() * 1000)).decode('ascii', 'ignore').split()
    if len(hdr) < 6 or hdr[5] != 'streaming':
        return None, 'camera not streaming: %s' % (' '.join(hdr) or 'no answer')
    dw, dh = int(hdr[0]), int(hdr[1])
    total, buf = dw * dh * 2, b''
    while len(buf) < total:
        part = get('%s/cam?w=%d&off=%d&t=%d' % (base, W, len(buf), time.time() * 1000))
        if not part:
            return None, 'short frame %d/%d' % (len(buf), total)
        buf += part
    px = []
    for k in range(dw * dh):
        v = buf[2 * k] | (buf[2 * k + 1] << 8)
        px.append((((v >> 11) & 31) / 31.0, ((v >> 5) & 63) / 63.0, (v & 31) / 31.0))
    return (dw, dh, px), ''


def grab_sim():
    with lock:
        f, t = state['simframe'], state['simframe_t']
    if f is None:
        return None, 'no CG frame (open the simulator #arm-xinu)'
    if time.time() - t > 3:
        return None, 'CG frame is %.0f s old' % (time.time() - t)
    return f, ''


def classify(img, roi):
    dw, dh, px = img
    green = blue = n = 0
    vmax = 0.0
    u0, v0, u1, v1 = roi
    for y in range(v0, v1):
        for x in range(u0, u1):
            h, s, v = colorsys.rgb_to_hsv(*px[y * dw + x])
            vmax = max(vmax, v)
            n += 1
            if s < 0.35 or v < 0.20:
                continue
            deg = h * 360
            if 75 <= deg <= 165 and s >= 0.5:
                green += 1
            elif 190 <= deg <= 260 and s >= 0.8:             # don't count the light-blue sheet (saturation 0.3-0.7) as blue
                blue += 1
    ans = 'none'
    if max(green, blue) * 100 >= NEED * n:
        ans = 'green' if green >= blue else 'blue'
    return ans, 100.0 * green / n, 100.0 * blue / n, vmax


# ---- PLAN: queue of commands being executed (Dancer.go in sort.aipl, and the arm moves of locate / lower) ----
def plan_push(where, cmd, depth=0):
    with lock:
        pl = state.setdefault('plan', {'seq': 0, 'items': []})
        pl['seq'] += 1
        for it in pl['items']:
            if it['state'] == 'run' and it['depth'] >= depth:
                it['state'] = 'ok?'                 # moved on to the next without writing back an answer
        pl['items'].append({'i': pl['seq'], 'where': where, 'cmd': cmd, 'state': 'run', 'result': '', 'depth': depth, 't': time.time()})
        del pl['items'][:-200]
        return pl['seq']


def plan_done(i, result):
    with lock:
        for it in state.get('plan', {}).get('items', []):
            if it['i'] == i:
                it['state'] = ('ok' if result.startswith(('ok', 'angles', 'green', 'blue'))
                               else 'none' if result.strip() == 'none' else 'fail')   # none: not found (in a check, means "gripped")
                it['result'] = result[:60]
                it['dt'] = round(time.time() - it['t'], 2)
                return 'ok'
    return 'err no such step'


def plan_msg(meth, arg):
    if meth == 'push':
        w = arg.split(' ', 1)
        return str(plan_push(w[0], w[1] if len(w) > 1 else ''))
    if meth == 'done':
        w = arg.split(' ', 1)
        try:
            return plan_done(int(w[0]), w[1] if len(w) > 1 else '')
        except ValueError:
            return 'err'
    if meth == 'reset':
        with lock:
            state['plan'] = {'seq': 0, 'items': []}
        return 'ok'
    return 'err'


def fresh_frame(which, after, wait=6):
    """One frame (simframe / realframe sent by the window) that arrived after time after"""
    t0 = time.time()
    while time.time() - t0 < wait:
        with lock:
            f, t = state[which], state[which + '_t']
        if f is not None and t >= after:
            return f
        time.sleep(0.05)
    return None


def do_locate(mode, grip=30, want=None):
    """grip: fingers while searching (30 open / 135 closed). In the post-lift check, move with them closed (opening drops the cube)"""
    if mode == 'sim':
        goal = {}
        def move_fn(s1, s):
            k = plan_push('sim', 'pose %d %d %d %d 90 %d 2500  (look)' % (s1, s[0], s[1], s[2], grip), 1)
            urllib.request.urlopen('http://127.0.0.1:8080/api/arm/sim?cmd=pose+%d+%d+%d+%d+90+%d+2500' % (s1, s[0], s[1], s[2], grip), timeout=5).read()
            goal['a'] = [s1] + list(s)
            time.sleep(2.8); plan_done(k, 'ok')
        def shoot_fn():
            # use only images shot after the sim model reached that pose (if the window is hidden the model stops and stale images arrive)
            t0 = time.time()
            while time.time() - t0 < 8:
                f = fresh_frame('simframe', time.time() + 0.1, wait=2)
                a4 = (state.get('simframe_a') or [])[:4]
                if f and len(a4) == 4 and all(abs(x - y) <= 2 for x, y in zip(a4, goal.get('a', a4))):
                    return f
            print('  locate(sim) the model did not reach %s (last %s) — is the simulator window hidden?' % (goal.get('a'), state.get('simframe_a')), flush=True)
            return None
    else:
        def move_fn(s1, s):
            k = plan_push('real', 'pose %d %d %d %d 90 %d 2500  (look)' % (s1, s[0], s[1], s[2], grip), 1)
            try:
                loc.move(s1, s, 2500, grip); time.sleep(2.8); loc.check_pose(s1, s)   # slowly (1.5 s swung too fast)
            except Exception as ex:
                plan_done(k, 'FAIL %s' % ex); raise
            plan_done(k, 'ok')
        def shoot_fn():
            f = fresh_frame('realframe', time.time() + 0.3, wait=4)
            return f if f else loc.shoot_board()
    lines = []
    try:
        res = loc.locate(move_fn, shoot_fn, rot180=(mode == 'real' and a.rot180), log=lines.append, want=want,
                         glimpse_fn=lambda t0, t1, prev, target: glimpses_between(mode, t0, t1, prev, target, 2500))
    except Exception as ex:                                  # e.g. the arm didn't move
        lines.append('locate stopped: %s' % ex); res = None
    for ln in lines:
        print('  locate(%s) %s' % (mode, ln), flush=True)
    if res and mode == 'real':                   # the real robot grips 1° left of the computed spot -> correct the base (geometry.json)
        g = state.get('geo') or {}
        res['base'] = int(round(res['base'] + float(g.get('real_base_offset', {}).get('v', 0))))
    with lock:
        state.setdefault('loc', {})[mode] = res
    if not res:
        put_stat(mode, 'none', 0, 0, 0, (lines[-1] if lines else 'locate failed'))
        return 'none'
    # recognition bar: classify, in the last frame, the box where the cube appears (around the centroid, cube-sized)
    img = shoot_fn()
    if img:
        W, H, px = img
        f = (W / 2) / math.tan(math.radians(loc.FOV / 2))
        half = f * loc.CUBE / 2 / 0.12
        b = loc.blob(px, W, H, mode == 'real' and a.rot180, res['color'])   # only the found cube's color (don't mix in a neighboring cube)
        if b:
            u, v = b[0], b[1]
            roi = (max(0, int(u - half)), max(0, int(v - half)), min(W, int(u + half)), min(H, int(v + half)))
            ans, g, bl, vmax = classify(img, roi)
            put_stat(mode, ans, g, bl, vmax, 'cube at %.1f cm, base %d' % (res['r'] * 100, res['base']),
                     [round(roi[0] / W, 3), round(roi[1] / H, 3), round(roi[2] / W, 3), round(roi[3] / H, 3)])
            return ans if ans != 'none' else res['color']
    put_stat(mode, res['color'], 0, 0, 0, 'cube at %.1f cm, base %d' % (res['r'] * 100, res['base']))
    return res['color']


def do_lower(arg):
    """lower <sim|real> here <grip>          … lower stepwise onto the cube found by locate
          lower <sim|real> <base> <r_cm> <grip>  … lower stepwise onto a drop-off spot
          Answer: "ok <fingertip height where stopped, cm>" / "err ..."
    """
    w = arg.split()
    mode = w[0] if w else 'real'
    try:
        if len(w) >= 3 and w[1] == 'here':
            with lock:
                res = state.get('loc', {}).get(mode)
            if not res:
                return 'err no cube located'
            s1, r, grip = res['base'], res['r'], int(w[2])
        else:
            s1, r, grip = int(w[1]), float(w[2]) / 100, int(w[3])
    except (ValueError, IndexError):
        return 'err bad args'
    if mode == 'sim':
        def move_fn(b1, s, g, ms):
            k = plan_push('sim', 'pose %d %d %d %d 90 %d %d  (lower)' % (b1, s[0], s[1], s[2], g, ms), 1)
            urllib.request.urlopen('http://127.0.0.1:8080/api/arm/sim?cmd=pose+%d+%d+%d+%d+90+%d+%d' % (b1, s[0], s[1], s[2], g, ms), timeout=5).read()
            plan_done(k, 'ok')
        angles_fn = None
    else:
        def move_fn(b1, s, g, ms):
            k = plan_push('real', 'pose %d %d %d %d 90 %d %d  (lower)' % (b1, s[0], s[1], s[2], g, ms), 1)
            try:
                loc.move(b1, s, ms, g)
            except Exception as ex:
                plan_done(k, 'FAIL %s' % ex); raise
            plan_done(k, 'ok')
        angles_fn = None     # hitting the table only lifts the body; angles stay as commanded -> undetectable by readback. Reading invites an arm-board reset
    lines = []
    try:
        y = loc.lower(move_fn, angles_fn, s1, r, grip, log=lines.append)
    except Exception as ex:
        lines.append('lower stopped: %s' % ex); y = None
    for ln in lines:
        print('  lower(%s) %s' % (mode, ln), flush=True)
    return 'ok %.1f' % (y * 100) if y is not None else 'err'     # reason is in the print above (AIPL compares against "err")


def do_held(mode):
    """Is it gripped? Real robot: if the readback of the fingers (servo 6) closed at 135 is <= held_max, they stopped against an object.
    Sim model: whether the CG cube is attached to the hand (cube_at.held sent by the window)"""
    if mode == 'sim':
        with lock:
            ca = state.get('cube_at') or {}
        return 'yes' if ca.get('held') else 'no'
    g = state.get('geo') or {}
    lim = float(g.get('held_max', {}).get('v', 141))
    a6 = []
    time.sleep(0.8)                              # read after the arm stops (piling up failed reads invites an arm-board reset)
    ang = loc.read_angles()
    if ang and ang[5] >= 0:
        a6.append(ang[5])
    if not a6:
        return 'err'
    v = sorted(a6)[len(a6) // 2]
    print('  held(real) servo6 = %s (limit %d)' % (a6, lim), flush=True)
    state['held_v'] = v
    with lock:
        state.setdefault('held_hist', []).append((time.time(), v))
    # If the fingers stop short of fully closed, it's "gripped". Commanded 145 with nothing reads 144-145; gripping a 3 cm cube flexes the fingers to 139 (measured 2026-09-29).
    # The old 125-134 (set from unloaded finger opening) said "not gripped" while gripped, and the choreography opened the fingers and dropped it.
    # Open fingers (e.g. 40) are not counted
    return 'yes' if 120 <= v <= lim else 'no'


def do_check(arg):
    """check <sim|real> <base>: shoot the drop-off spot (base angle base, 17 cm) and return the color of the cube there (green|blue|none)"""
    w = arg.split()
    mode = w[0] if w else 'real'
    try:
        s1 = int(w[1])
    except (IndexError, ValueError):
        return 'err'
    look = loc.poses(0.17)[0]
    try:
        if mode == 'sim':
            urllib.request.urlopen('http://127.0.0.1:8080/api/arm/sim?cmd=pose+%d+%d+%d+%d+90+30+2500' % (s1, look[0], look[1], look[2]), timeout=5).read()
            time.sleep(2.8)
            img = fresh_frame('simframe', time.time() + 0.1)
        else:
            loc.move(s1, look, 2500, 30); time.sleep(2.8)
            img = fresh_frame('realframe', time.time() + 0.3, wait=4)
    except Exception as ex:
        print('  check stopped: %s' % ex, flush=True)
        return 'err'
    if not img:
        return 'err'
    W, H, px = img
    best = None
    for col in ('green', 'blue'):
        b = loc.blob(px, W, H, False, col)
        if b and (best is None or b[3] > best[1]):
            best = (col, b[3])
    print('  check(%s) base %d -> %s' % (mode, s1, best), flush=True)
    return best[0] if best else 'none'


def get_loc(arg):
    w = arg.split()
    if len(w) < 2:
        return 'err'
    with lock:
        res = state.get('loc', {}).get(w[0])
    if not res:
        return 'none'
    k = w[1]
    if k == 'base':
        return str(res['base'])
    if k in ('look', 'pre', 'grasp'):
        return ' '.join(str(v) for v in res[k])
    if k == 'where':
        return '%.3f %.3f' % (res['x'], res['z'])
    return 'err'


def put_stat(mode, ans, g, b, v, why, roi=None):
    with lock:
        st = state['stat']
        state['stat'] = {'seq': st['seq'] + 1, 'mode': mode, 'answer': ans, 'green': round(g, 1), 'blue': round(b, 1),
                         'need': NEED, 'max_v': round(v, 2), 'why': why, 't': time.time(), 'roi': roi}
        state['last'] = '%s -> %s  green=%.1f%% blue=%.1f%% max_v=%.2f %s' % (mode, ans, g, b, v, why)


def color(arg):
    w = arg.split()
    mode = 'sim' if w and w[0] == 'sim' else 'real'
    try:
        pose = [float(x) for x in w[1:5]] if len(w) >= 5 else [90, 75, 15, 35]
    except ValueError:
        pose = [90, 75, 15, 35]
    img, why = grab_sim() if mode == 'sim' else grab_real()
    if img is None:
        put_stat(mode, 'none', 0, 0, 0, why)
        return 'none'
    roi = roi_for(pose, img[0], img[1], rot180=(mode == 'real' and a.rot180))
    if roi is None:
        put_stat(mode, 'none', 0, 0, 0, 'the grasp spot is out of the camera view at pose %s' % pose)
        return 'none'
    ans, g, b, v = classify(img, roi)
    nroi = [round(roi[0] / img[0], 3), round(roi[1] / img[1], 3), round(roi[2] / img[0], 3), round(roi[3] / img[1], 3)]
    put_stat(mode, ans, g, b, v, 'dark: no light reaches the lens' if v < 0.2 else '', nroi)
    return ans


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def _send(self, body, ctype='text/plain; charset=utf-8'):
        body = body.encode()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send('')

    def do_POST(self):
        p, _, q = self.path.partition('?')
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if p == '/geo':                                     # saved from the simulator's "dimensions" panel
            try:
                g = json.loads(body.decode('utf-8'))
                with open(loc.GEO_FILE, 'w') as fh:
                    json.dump(g, fh, ensure_ascii=False, indent=2)
                loc.set_geo(g)
                with lock:
                    state['geo'] = g
                self._send('ok\n')
            except ValueError as ex:
                self._send('err %s\n' % ex)
            return
        if p in ('/simframe', '/realframe'):
            kv = dict(x.split('=', 1) for x in q.split('&') if '=' in x)
            w, h = int(kv.get('w', 80)), int(kv.get('h', 60))
            if len(body) >= w * h * 3:
                px = [(body[3 * k] / 255.0, body[3 * k + 1] / 255.0, body[3 * k + 2] / 255.0) for k in range(w * h)]
                which = p[1:]
                with lock:
                    state[which], state[which + '_t'] = (w, h, px), time.time()
                    if which == 'simframe' and 'a' in kv:         # sim-model joint angles when this image was shot
                        try:
                            state['simframe_a'] = [int(v) for v in kv['a'].split(',')]
                        except ValueError:
                            state['simframe_a'] = None
                        RING.append((time.time(), 'sim', (w, h, px), state['simframe_a']))
                    if which == 'simframe' and 'cx' in kv:        # where the CG cube is now (whether it's gripped)
                        state['cube_at'] = {k2: float(kv[k2]) for k2 in ('cx', 'cy', 'cz', 'held') if k2 in kv}
            self._send('ok\n')
        else:
            self._send('no such path\n')

    def do_GET(self):
        p, _, q = self.path.partition('?')
        if p == '/sim':
            c = dict(x.split('=', 1) for x in q.split('&') if '=' in x).get('c', '')
            with lock:
                if c in ('green', 'blue', 'both'):          # both: place green and blue side by side
                    state['cube'] = {'color': c, 'seq': state['cube']['seq'] + 1}
                cube = dict(state['cube'])
            self._send('CG cube = %s (placed again, #%d)\n' % (cube['color'], cube['seq']))
        elif p in ('/plan/push', '/plan/done', '/plan/reset'):   # commands sent from the Xinu simulator window go into the same PLAN
            kv = {}
            for x in q.split('&'):
                if '=' in x:
                    k2, v2 = x.split('=', 1); kv[k2] = urllib.parse.unquote_plus(v2)
            if p.endswith('push'):
                self._send(str(plan_push(kv.get('where', 'sim'), kv.get('cmd', ''))))
            elif p.endswith('done'):
                try:
                    self._send(plan_done(int(kv.get('i', '0')), kv.get('r', '')))
                except ValueError:
                    self._send('err')
            else:
                self._send(plan_msg('reset', ''))
        elif p == '/plan':
            with lock:
                pl = state.get('plan', {'seq': 0, 'items': []})
                body = json.dumps({'seq': pl['seq'], 'items': pl['items'][-40:]}, ensure_ascii=False)
            self._send(body, 'application/json; charset=utf-8')
        elif p == '/realframe.bin':                     # latest real camera frame (raw RGB, 1 byte each). Drawn by the window
            with lock:
                f, t = state['realframe'], state['realframe_t']
            if not f:
                self._send('')
                return
            w, h, px = f
            body = bytes(int(c * 255) for q in px for c in q)
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'X-W, X-H, X-Age')
            self.send_header('X-W', str(w)); self.send_header('X-H', str(h)); self.send_header('X-Age', '%.2f' % (time.time() - t))
            self.end_headers()
            self.wfile.write(body)
        elif p == '/held':                               # readback history of the grip check (since= onward)
            kv = dict(x.split('=', 1) for x in q.split('&') if '=' in x)
            since = float(kv.get('since', '0'))
            with lock:
                h = [x for x in state.get('held_hist', []) if x[0] >= since]
            self._send(json.dumps(h), 'application/json')
        elif p == '/geo':
            with lock:
                g = state.get('geo') or {}
            self._send(json.dumps(g, ensure_ascii=False), 'application/json; charset=utf-8')
        elif p == '/stat':
            with lock:
                st = dict(state['stat']); st['cube'] = dict(state['cube']); st['cube_at'] = state.get('cube_at')
                st['cg_age'] = round(time.time() - state['simframe_t'], 1) if state['simframe'] else None
            self._send(json.dumps(st), 'application/json')
        else:
            self._send(state['last'] + '\n')


state['geo'] = loc.load_geo()
threading.Thread(target=cam_loop, daemon=True).start()
threading.Thread(target=lambda: ThreadingHTTPServer(('', a.http), Hd).serve_forever(), daemon=True).start()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('', a.port))
memo, busy = {}, set()
print('color_service: UDP/%d, HTTP/%d, board %s' % (a.port, a.http, a.board), flush=True)


def serve(key, addr, reqid, actor, meth, arg):
    t0 = time.time()
    w = arg.split()
    if actor == 'Plan':
        ans = plan_msg(meth, arg)
    elif actor != 'Camera':
        ans = 'err'
    elif meth == 'color':
        ans = color(arg.strip())
    elif meth == 'locate':
        k = plan_push(w[0] if w else 'real', 'locate ' + ' '.join(w[1:]))
        ans = do_locate('sim' if w and w[0] == 'sim' else 'real', int(w[1]) if len(w) > 1 and w[1].isdigit() else 30,
                        w[2] if len(w) > 2 and w[2] in ('green', 'blue') else None)   # color to search (if absent, whichever has more)
        plan_done(k, ans)
    elif meth == 'lower':
        k = plan_push(w[0] if w else 'real', 'lower ' + ' '.join(w[1:]))
        ans = do_lower(arg)
        plan_done(k, ans)
    elif meth == 'get':
        ans = get_loc(arg)
    elif meth == 'check':
        ans = do_check(arg)
    elif meth == 'held':
        k = plan_push(w[0] if w else 'real', 'held?')
        ans = do_held('sim' if w and w[0] == 'sim' else 'real')
        hv = state.get('held_v', '')
        plan_done(k, ('ok yes (servo6 %s)' if ans == 'yes' else 'no (servo6 %s)') % hv if ans in ('yes', 'no') else ans)
    else:
        ans = 'err'
    with lock:
        memo[key] = ans
        busy.discard(key)
        if len(memo) > 512:
            memo.pop(next(iter(memo)))
    print('%s %s.%s(%s) -> %s (%.2fs)  %s' % (addr[0], actor, meth, arg, ans, time.time() - t0, state['last']), flush=True)
    s.sendto(('R %s %s\n' % (reqid, ans)).encode(), addr)


while True:
    data, addr = s.recvfrom(1024)
    parts = data.decode('ascii', 'ignore').strip().split(' ', 3)
    if len(parts) >= 2 and parts[0] == 'H':
        s.sendto(('A %s\n' % parts[1]).encode(), addr)
        continue
    if len(parts) < 3 or parts[0] != 'Q':
        continue
    reqid, actor = parts[1], parts[2]
    rest = parts[3].split(' ', 1) if len(parts) > 3 else ['']
    meth, arg = rest[0], (rest[1] if len(rest) > 1 else '')
    key = (addr, reqid)
    with lock:
        if key in memo:
            s.sendto(('R %s %s\n' % (reqid, memo[key])).encode(), addr)
            continue
        if key in busy:                 # resend during classification
            continue
        busy.add(key)
    threading.Thread(target=serve, args=(key, addr, reqid, actor, meth, arg), daemon=True).start()
