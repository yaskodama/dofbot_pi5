#!/usr/bin/env python3
# locate.py — measure a cube's position (x, z on the table) with the real robot's wrist camera, and compute look/pre-grasp/grip poses by inverse kinematics.
# The camera sits on top of the wrist (3.2 cm from the finger axis), so: "aim the camera axis at the cube and shoot -> align the finger axis and grip".
# 1) move to the pose that looks at target (x, z) and shoot  2) back-project the centroid of blue/green pixels onto the table (cube top face y=3.5 cm)
# 3) use that point as the new target and repeat (a blob cut off at the image edge pulls the centroid inward, so a few times)
# Output (last line): JSON {"x":..,"z":..,"base":..,"look":[..],"pre":[..],"grasp":[..],"color":..}
import math, json, sys, time, colorsys, urllib.request, urllib.parse, os, threading
HTTP_LOCK = threading.Lock()    # the board's HTTP handles one request at a time (color_service plugs its own lock in here)

B = 'http://192.168.3.101'
# Dimensions come from geometry.json (same values as the Xinu simulator CG; replaced by set_geo)
H0, L, L3, LG = 0.1075, 0.08285, 0.07385, 0.06
CAM_ALONG, CAM_UP, CUBE, FOV = 0.0625, 0.032, 0.030, 60.0   # CUBE: 3 cm per side (measured)
GEO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geometry.json')


def set_geo(g):
    """g: contents of geometry.json ({"H": {"v": ..}, ...}). L1 and L2 are treated as equal length (the IK is an equal-length 2-link)"""
    global H0, L, L3, LG, CAM_ALONG, CAM_UP, FOV, CUBE
    v = lambda k, d: float(g.get(k, {}).get('v', d))
    H0, L, L3, LG = v('H', H0), (v('L1', L) + v('L2', L)) / 2, v('L3', L3), v('LG', LG)
    CAM_ALONG, CAM_UP, FOV, CUBE = v('cam_along', CAM_ALONG), v('cam_up', CAM_UP), v('fov', FOV), v('cube', CUBE)


def load_geo():
    try:
        with open(GEO_FILE) as fh:
            g = json.load(fh)
        set_geo(g)
        return g
    except (OSError, ValueError):
        return None



A3, DIST = 165, 0.12                     # hand tilt (from vertical up), distance from camera to cube
TIP_Y = 0.012                            # fingertip height when gripping/placing (1.2 cm above table; at 0.8 cm it hit the table, at 1.5 cm it dropped the cube while lifting)
# The real fingers are longer than the sim model's: lowering to 2.3 cm as in the sim made the real robot hit the table and lift its body (2026-09-27, twice).
# Hitting the table only lifts the body; the joints still turn as commanded, so angle readback cannot detect the contact.
PRE_BACK = 0.035                         # pre-grasp is 3.5 cm back from the grip position along the axis



def http_get(url, timeout=5, body=None):
    """GET to the board. Always close with RST when done (SO_LINGER 0).
    Closing a timed-out urllib connection normally left Xinu's single-threaded HTTP waiting forever to clean up that connection,
    and it stopped accepting any other connection. Killing the client process (which sends RST) recovered it in about 10 s (2026-09-29)"""
    import socket as _s, struct as _st
    u = urllib.parse.urlsplit(url)
    host, port = u.hostname, u.port or 80
    path = u.path + ('?' + u.query if u.query else '')
    sk = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    sk.setsockopt(_s.SOL_SOCKET, _s.SO_LINGER, _st.pack('ii', 1, 0))
    sk.settimeout(timeout)
    data = b''
    try:
        sk.connect((host, port))
        if body is None:
            sk.sendall(('GET %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, host)).encode())
        else:
            sk.sendall(('POST %s HTTP/1.0\r\nHost: %s\r\nContent-Length: %d\r\n\r\n' % (path, host, len(body))).encode() + body)
        while True:
            chunk = sk.recv(65536)
            if not chunk:
                break
            data += chunk
            head, sep, body = data.partition(b'\r\n\r\n')
            if sep:
                m = [l for l in head.split(b'\r\n') if l.lower().startswith(b'content-length:')]
                if m and len(body) >= int(m[0].split(b':')[1]):
                    break
    finally:
        sk.close()                      # SO_LINGER 0 → RST
    head, sep, body = data.partition(b'\r\n\r\n')
    if not sep or not head.startswith(b'HTTP/') or b' 200 ' not in head.split(b'\r\n')[0] + b' ':
        raise IOError('bad response')
    return body

def get(url, tries=6):
    for _ in range(tries):
        try:
            with HTTP_LOCK:
                b = http_get(url, 8)
            if b:
                return b
        except Exception:
            pass
        time.sleep(0.4)
    return b''


def ik(r, y, a3):
    dy = y - H0; d = math.hypot(r, dy)
    if d > 2 * L - 1e-4 or d < 0.02:
        return None
    base = math.atan2(dy, r); off = math.acos(d / (2 * L))
    A1 = 90 - math.degrees(base + off); A2 = 90 - math.degrees(base - off)
    s = [round(90 - A1), round(90 - (A2 - A1)), round(90 - (a3 - A2))]
    return s if all(0 <= v <= 180 for v in s) else None


def low_point(s):
    r_ = math.radians
    A1 = r_(90 - s[0]); A2 = A1 + r_(90 - s[1]); A3r = A2 + r_(90 - s[2])
    y2 = H0 + L * math.cos(A1); y3 = y2 + L * math.cos(A2); y5 = y3 + L3 * math.cos(A3r)
    return min(y2, y3, y5, y5 + LG * math.cos(A3r))


def look_pose(r):
    """Pose whose camera axis passes through the cube center. Chooses hand tilt and camera distance (lowest point of the arm >= 4 cm above table).
    With 8.3 cm fingers, the visible range is 14-23 cm from the base axis"""
    for a3 in range(180, 109, -5):
        a = math.radians(a3); d3 = (math.sin(a), math.cos(a)); up = (-math.cos(a), math.sin(a))   # up = top face of the wrist
        for dist in (0.12, 0.11, 0.13, 0.10, 0.14, 0.09, 0.15, 0.16, 0.08):
            c = (r - d3[0] * dist, CUBE / 2 - d3[1] * dist)
            s = ik(c[0] - d3[0] * CAM_ALONG - up[0] * CAM_UP, c[1] - d3[1] * CAM_ALONG - up[1] * CAM_UP, a3)
            if s and low_point(s) >= 0.04:                      # fingertips also 1 cm above the cube (3 cm)
                return s, a3, dist
    return None, None, None


def grasp_poses(r):
    """Grip pose whose finger axis passes through the cube center with the fingertip at TIP_Y above the table, plus the point PRE_BACK back along that axis.
    Hand tilt is searched in 1° steps (with 5° steps, at 13.6-14.2 cm both 170° and 165° were out of joint range and the gap in between was missed)"""
    for a3 in range(180, 129, -1):
        a = math.radians(a3); d3 = (math.sin(a), math.cos(a))
        t = (TIP_Y - CUBE / 2) / d3[1]
        tip = (r + d3[0] * t, TIP_Y)
        P3 = (tip[0] - d3[0] * (L3 + LG), tip[1] - d3[1] * (L3 + LG))
        g = ik(P3[0], P3[1], a3)
        p = ik(P3[0] - d3[0] * PRE_BACK, P3[1] - d3[1] * PRE_BACK, a3)
        if g and p:
            return p, g, a3
    return None, None, None


def poses(r):
    look, _, _ = look_pose(r)
    pre, grasp, _ = grasp_poses(r)
    return look, pre, grasp


def pose_at(r, tip_y, a3):
    """Pose (s2 s3 s4) whose finger axis at tilt a3 passes through (r, cube center height) with fingertip height tip_y"""
    a = math.radians(a3); d3 = (math.sin(a), math.cos(a))
    t = (tip_y - CUBE / 2) / d3[1]
    tip = (r + d3[0] * t, tip_y)
    return ik(tip[0] - d3[0] * (L3 + LG), tip[1] - d3[1] * (L3 + LG), a3)


def read_angles():
    """Arm angles. While moving, the board returns "?".
    ★ Xinu's /arm read sends a reset to the arm board after 3 consecutive "none of the 6 axes readable", and that reset leaves the board
        dead until power-cycled (4 times on 2026-09-28). So read at most 2 times in a row, 1.5 s apart.
        Returns None if unreadable (the caller skips the check)"""
    for i in range(2):
        w = arm_udp('read').split()
        if len(w) >= 7 and w[0] == 'angles' and '?' not in w[1:5]:
            return [int(v) if v != '?' else -1 for v in w[1:7]]
        if i == 0:
            time.sleep(1.5)
    return None


def lower(move_fn, angles_fn, s1, r, grip, top=0.05, floor=TIP_Y, step=0.005, back=0.008, tol=3, log=print):
    """Lower the fingertip from top above the table in steps of step. At each step read back the angles; if shoulder, elbow or wrist
    deviates from the command by more than tol°, treat it as hitting the table (or an object), raise by back and stop. If nothing is hit, stop at floor.
    Returns: fingertip height where it stopped (m). If angles_fn is None, no readback (sim model)"""
    a3 = grasp_poses(r)[2]
    if a3 is None:
        raise RuntimeError('cannot reach %.3f' % r)
    if angles_fn is None:
        # If readback is not used to detect contact (hitting the table leaves joints as commanded, so it can't be detected), stepping is pointless.
        # Sending ~8 commands in a row, 0.5 cm each at 0.6 s intervals, stalled the arm board (2026-09-29; all 5 stalls happened
        # during or right after a "lower"). Lower in one command over 2 s
        s = pose_at(r, floor, a3)
        if not s:
            raise RuntimeError('no pose for tip %.3f at %.3f' % (floor, r))
        move_fn(s1, s, grip, 2000)
        time.sleep(2.3)
        log('lowered to %.1f cm in one slow move' % (floor * 100))
        return floor
    y = top
    while not pose_at(r, y, a3) and y > floor + 1e-6:        # skip heights too high to form a pose
        y = max(floor, y - step)
    while True:
        s = pose_at(r, y, a3)
        if not s:
            raise RuntimeError('no pose for tip %.3f at %.3f' % (y, r))
        move_fn(s1, s, grip, 500)
        if angles_fn:
            time.sleep(0.8)
            got = angles_fn()
            if got is None:
                raise RuntimeError('arm angles cannot be read')
            dev = max(abs(g - t) for g, t in zip(got[1:4], s))
            if dev > tol:
                log('contact at tip %.1f cm (joint off by %d deg) -> back to %.1f cm' % (y * 100, dev, (y + back) * 100))
                y = y + back
                move_fn(s1, pose_at(r, y, a3), grip, 500); time.sleep(0.6)
                return y
        else:
            time.sleep(0.6)
        if y <= floor + 1e-6:
            log('reached %.1f cm without contact' % (y * 100))
            return y
        y = max(floor, y - step)


def point_pose(r, tip_y=0.05):
    """Pose pointing with the fingertip at where the cube will be placed (fingertip tip_y above table). Searches feasible hand tilts in 1° steps"""
    for a3 in range(180, 129, -1):
        s = pose_at(r, tip_y, a3)
        if s:
            return s
    return None


def cam_frame(s1, s):
    """Camera position and axis for a pose (3D, x forward / y up / z sideways)"""
    r_ = math.radians
    A1 = r_(90 - s[0]); A2 = A1 + r_(90 - s[1]); A3r = A2 + r_(90 - s[2]); yaw = r_(s1 - 90)
    f = (math.cos(yaw), 0, -math.sin(yaw)); l = (math.sin(yaw), 0, math.cos(yaw))
    d = lambda A: (f[0] * math.sin(A), math.cos(A), f[2] * math.sin(A))
    P2 = tuple(p + q * L for p, q in zip((0, H0, 0), d(A1))); P3 = tuple(p + q * L for p, q in zip(P2, d(A2)))
    d3 = d(A3r)
    up = (-(d3[1] * l[2] - d3[2] * l[1]), -(d3[2] * l[0] - d3[0] * l[2]), -(d3[0] * l[1] - d3[1] * l[0]))  # cross(l, d3)
    n = math.sqrt(sum(x * x for x in up)); up = tuple(x / n for x in up)
    c = tuple(P3[i] + d3[i] * CAM_ALONG + up[i] * CAM_UP for i in range(3))
    return c, d3, l, up


def shoot_board():
    """One 160x120 frame from the Xinu board -> (W, H, [(r,g,b) 0..1])"""
    time.sleep(2.2)                                                       # wait for the arm to stop
    hdr = get('%s/cam?w=160&t=%d' % (B, time.time() * 1000)).decode('ascii', 'ignore').split()
    if len(hdr) < 6 or hdr[5] != 'streaming':
        return None
    buf = b''
    while len(buf) < 38400:
        p = get('%s/cam?w=160&off=%d&t=%d' % (B, len(buf), time.time() * 1000))
        if not p:
            return None
        buf += p
    px = []
    for k in range(160 * 120):
        v = buf[2 * k] | buf[2 * k + 1] << 8
        px.append((((v >> 11) & 31) / 31, ((v >> 5) & 63) / 63, (v & 31) / 31))
    return 160, 120, px


def blob(px, W, H, rot180, want=None, min_frac=0.015):
    """Color blob centroid (image coords in model orientation), color, count, bounding box.
    want: 'green' / 'blue' for that color only. None picks the color with more pixels (never mixes green and blue when both are visible)"""
    pts = {'green': [], 'blue': []}
    for y in range(H):
        for x in range(W):
            h, s, val = colorsys.rgb_to_hsv(*px[y * W + x])
            if s < 0.35 or val < 0.06:
                continue
            deg = h * 360
            # blue only with saturation >= 0.8 and value >= 0.2: the light-blue sheet on the table is saturation 0.3-0.7, the blue cube 1.0 (measured 2026-09-29)
            # green from value 0.06: on white paper the camera exposure drops and the green cube showed at value 0.1 (measured same day)
            k = ('green' if (75 <= deg <= 165 and s >= 0.45) else
                 'blue' if (190 <= deg <= 260 and s >= 0.8) else None)   # blue also from value 0.06 (blue at P2 showed at value 0.1-0.2)
            if k:
                pts[k].append((W - 1 - x if rot180 else x, H - 1 - y if rot180 else y))
    col = want if want in pts else max(pts, key=lambda c: len(pts[c]))
    p = pts[col]
    # The cube (3 cm) covers >= 5% of the image at viewing distance (~13 cm). Blobs under 1.5% are treated as thin objects (blue cables etc.)
    # (2026-09-29: chased 1.7-7.7% blue blobs and whiffed 3 times in front of the green cube)
    if len(p) < max(20 if min_frac >= 0.015 else 8, int(W * H * min_frac)):
        return None
    us = [q[0] for q in p]; vs = [q[1] for q in p]
    # A blob spanning >= 85% of the image both vertically and horizontally is a large surface (book, box, mat), not a cube.
    # 2026-09-29: a green book beside the left drop-off spot was judged to be the green cube
    if max(us) - min(us) >= 0.85 * W and max(vs) - min(vs) >= 0.85 * H:
        return None
    return sum(us) / len(us), sum(vs) / len(vs), col, len(p), (min(us), max(us), min(vs), max(vs))


_rid = [int(time.time() * 1000) % 1000000 + 300000]


def arm_udp(cmd, board=('192.168.3.101', 9010), tries=8):
    """Send to the board's "dofbot" actor using the same message as AIPL remote_call (UDP, resent until an answer arrives).
    HTTP /arm/pose returns empty when it overlaps with the window's fetch, and things proceed with the arm not moving"""
    import socket
    _rid[0] += 1
    q = ('Q %d dofbot cmd %s\n' % (_rid[0], cmd)).encode()
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sk.settimeout(0.6)
    try:
        for _ in range(tries):
            sk.sendto(q, board)
            try:
                while True:
                    data = sk.recvfrom(512)[0].decode('ascii', 'ignore').strip()
                    if data.startswith('R %d ' % _rid[0]):
                        return data.split(' ', 2)[2]
            except socket.timeout:
                continue
    finally:
        sk.close()
    return ''


def reload_actor():
    """Reload the board's arm actor (dofbot_arm.aipl) via POST /cc.
    Occasionally the actor starts returning only empty answers (cause unknown, 3 times on 2026-09-28..29). Reloading fixes it"""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aipl', 'dofbot_arm.aipl')
    try:
        with HTTP_LOCK:
            http_get(B + '/cc', 30, body=open(src, 'rb').read())     # POST. Close with RST when done
    except Exception:
        pass
    time.sleep(1.5)


def move(s1, s, ms=1500, grip=30):
    ans = ''
    for i in range(4):                  # I2C writes sometimes return FAIL rc=-2; resending gets through
        ans = arm_udp('pose %d %d %d %d 90 %d %d' % (s1, s[0], s[1], s[2], grip, ms))
        if ans.startswith('ok'):
            return True
        if ans == '' and i == 1:        # empty answer = actor is dead -> reload it
            reload_actor()
        time.sleep(0.3)
    raise RuntimeError('arm did not move: %r' % ans)


def check_pose(s1, s, tol=6):
    """Is the arm really in that pose (read back angles)? The board returns ok to pose even if a servo is dead"""
    ang = read_angles()
    if ang:
        got = ang[:4]
        want = [s1] + list(s)
        if all(abs(g - t) <= tol for g, t in zip(got, want)):
            return True
        raise RuntimeError('arm is not at the pose: want %s got %s' % (want, got))
    return None                          # unreadable (e.g. while moving). Skip the check — repeated rereads invite an arm-board reset


# ---- Sweep the whole range once and build a list of cubes on the table ------------------------------------------------
# The reachable band (14-23 cm from the base axis, ±45° from front) is split into 2 rows x 4 spots so that the camera footprints (15 cm wide x 11 cm deep at 13 cm viewing distance)
# overlap, and all are shot in a fixed (serpentine) order. Green and blue blobs in each image are back-projected onto the table and listed.
# Previously each search started from the same spot and chased the first thing seen, so a second cube or one slightly off was missed.
SURVEY = [(0.16, yy) for yy in (-40, -13, 13, 40)] + [(0.21, yy) for yy in (40, 13, -13, -40)]
PLACES = [(0.17, 150), (0.17, 30)]            # drop-off spots (cubes placed here are not counted)
REACH = (0.135, 0.235)


def world_of(u, v, s1, look, W, H):
    c, d3, l, up = cam_frame(s1, look)
    f = (W / 2) / math.tan(math.radians(FOV / 2))
    ray = tuple(d3[k] + l[k] * (u - W / 2) / f + up[k] * (H / 2 - v) / f for k in range(3))
    t = (CUBE - c[1]) / ray[1]
    return c[0] + ray[0] * t, c[2] + ray[2] * t


def near_place(x, z, tol=0.045):
    for r, b in PLACES:
        yaw = math.radians(b - 90)
        if math.hypot(x - r * math.cos(yaw), z + r * math.sin(yaw)) < tol:
            return True
    return False


def survey(move_fn, shoot_fn, rot180=False, log=print, glimpse_fn=None, want=None):
    """Shoot the 8 spots in order and return the list of found cubes [{'color','x','z','n','views'}] (most pixels first).
    glimpse_fn(t0, t1, prev, target) -> [((w, h, px), pose4)]: images captured while the arm moved from prev to target, and
    the (estimated) pose at that time. Cubes "glimpsed" during moves are recorded; if the wanted color isn't found in one sweep,
    go back to that position and look again"""
    found, glimpses = [], []
    prev = None
    seen_uv = []                                   # (color, u, v, base) where in the image it appeared
    for r, yy in SURVEY:
        s1 = 90 + yy
        look = poses(r)[0]
        if not look:
            continue
        t0 = time.time()
        move_fn(s1, look)
        if glimpse_fn and prev:
            for (gw, gh, gpx), pose in glimpse_fn(t0, time.time(), prev, [s1] + list(look)):
                for col in ('green', 'blue'):
                    gb = blob(gpx, gw, gh, rot180, col, min_frac=0.003)
                    if not gb:
                        continue
                    gx, gz = world_of(gb[0], gb[1], pose[0], pose[1:4], gw, gh)
                    if near_place(gx, gz) or not (0.10 <= math.hypot(gx, gz) <= 0.27):
                        continue
                    glimpses.append({'color': col, 'x': gx, 'z': gz, 'n': gb[3]})
        prev = [s1] + list(look)
        img = shoot_fn()
        if not img:
            log('survey: no frame at %.0f cm, base %d' % (r * 100, s1)); continue
        W, H, px = img
        seen = []
        for col in ('green', 'blue'):
            b = blob(px, W, H, rot180, col)
            if not b:
                continue
            x, z = world_of(b[0], b[1], s1, look, W, H)
            rr = math.hypot(x, z)
            seen_uv.append((col, b[0], b[1], s1))
            if near_place(x, z) or not (REACH[0] <= rr <= REACH[1]):
                seen.append('%s(skip %.1fcm)' % (col, rr * 100)); continue
            for d in found:                                  # within 3 cm = same cube
                if d['color'] == col and math.hypot(d['x'] - x, d['z'] - z) < 0.03:
                    w = d['n'] + b[3]
                    d['x'], d['z'] = (d['x'] * d['n'] + x * b[3]) / w, (d['z'] * d['n'] + z * b[3]) / w
                    d['n'], d['views'] = w, d['views'] + 1
                    break
            else:
                found.append({'color': col, 'x': x, 'z': z, 'n': b[3], 'views': 1})
            seen.append('%s(%d px at %.1fcm)' % (col, b[3], rr * 100))
        log('survey %.0f cm base %d: %s' % (r * 100, s1, ', '.join(seen) or 'nothing'))
    # A blob that appears at the same image spot (±8 px) from 3 or more directions is not on the table but moves with the camera
    # (e.g. a cube caught on the fingers). 2026-09-29: green was "found" at the same 20.2 cm in 4 directions
    moving = []
    for col, u, v, b1 in seen_uv:
        same = {bb for cc, uu, vv, bb in seen_uv if cc == col and abs(uu - u) <= 8 and abs(vv - v) <= 8}
        if len(same) >= 3 and (col, round(u), round(v)) not in moving:
            moving.append((col, round(u), round(v)))
    if moving:
        log('survey: %s moves with the camera (in the hand?) — ignored' % moving)
        def moves_with_camera(d):
            return any(c == d['color'] for c, _, _ in moving)
        found = [d for d in found if not moves_with_camera(d)]
    # If the wanted color wasn't found in one sweep but was glimpsed during a move, go back to that position and look again
    have = {d['color'] for d in found}
    for g in sorted(glimpses, key=lambda d: -d['n']):
        if g['color'] in have or (want and g['color'] != want):
            continue
        rr = min(max(math.hypot(g['x'], g['z']), 0.16), 0.21)
        s1 = round(90 + math.degrees(math.atan2(-g['z'], g['x'])))
        look = poses(rr)[0]
        if not look:
            continue
        log('glimpse: %s at %.1f cm, base %d — go back and look' % (g['color'], math.hypot(g['x'], g['z']) * 100, s1))
        move_fn(s1, look)
        img = shoot_fn()
        b = blob(img[2], img[0], img[1], rot180, g['color']) if img else None
        if b:
            x, z = world_of(b[0], b[1], s1, look, img[0], img[1])
            if not near_place(x, z) and REACH[0] <= math.hypot(x, z) <= REACH[1]:
                found.append({'color': g['color'], 'x': x, 'z': z, 'n': b[3], 'views': 1})
                have.add(g['color'])
                log('glimpse confirmed: %s at %.1f cm' % (g['color'], math.hypot(x, z) * 100))
    found.sort(key=lambda d: -d['n'])
    log('survey result: %s (glimpses %d)' % (['%s %.1fcm base %d' % (d['color'], math.hypot(d['x'], d['z']) * 100,
                                  round(90 + math.degrees(math.atan2(-d['z'], d['x'])))) for d in found], len(glimpses)))
    return found


def locate(move_fn=None, shoot_fn=None, rot180=False, x=0.17, z=0.0, rounds=7, log=print, want=None, glimpse_fn=None):
    """Move the arm with move_fn(s1, [s2,s3,s4]) and shoot with shoot_fn() -> (W, H, [(r,g,b) 0..1]).
    rot180: whether the image is rotated 180° (real robot True, CG False)"""
    move_fn = move_fn or (lambda s1, s: move(s1, s))
    shoot_fn = shoot_fn or shoot_board
    color = None
    # First sweep the whole range to build the list, then pick a cube of the wanted color (none if absent)
    cands = [d for d in survey(move_fn, shoot_fn, rot180, log, glimpse_fn, want) if want in (None, d['color'])]
    if not cands:
        log('survey: no %s cube in reach' % (want or 'green/blue')); return None
    x, z, want = cands[0]['x'], cands[0]['z'], cands[0]['color']
    for i in range(rounds):
        r = math.hypot(x, z); s1 = round(90 + math.degrees(math.atan2(-z, x)))
        look = poses(r)[0]
        if not look and r < 0.141:
            # Inner edge: if it closes in to where no look pose is feasible, hold at the nearest feasible (14.1 cm) and go grip
            # (2026-09-29: at P2 (15 cm) the estimate became 13.6 cm and it gave up despite having found it. A grip pose is feasible even at 13 cm)
            k = 0.141 / max(r, 1e-6); x, z = x * k, z * k
            log('round %d: at the inner edge (%.1f cm) — clamp to 14.1 cm and stop refining' % (i, r * 100)); break
        if not look:
            log('round %d: (%.3f, %.3f) is out of reach' % (i, x, z)); return None
        move_fn(s1, look)
        img = shoot_fn()
        if not img:
            log('round %d: no camera frame' % i); return None
        W, H, px = img
        f = (W / 2) / math.tan(math.radians(FOV / 2))
        b = blob(px, W, H, rot180, want)
        if not b:
            log('round %d: no %s in view at base %d — keep the surveyed position' % (i, want or 'green/blue', s1)); break
        u, v, color, n, box = b
        c, d3, l, up = cam_frame(s1, look)
        ray = tuple(d3[k] + l[k] * (u - W / 2) / f + up[k] * (H / 2 - v) / f for k in range(3))
        t = (CUBE - c[1]) / ray[1]                                          # intersection with the cube's top face
        nx, nz = c[0] + ray[0] * t, c[2] + ray[2] * t
        log('round %d: base %d look %s -> %s n=%d at (%.0f,%.0f) -> cube (%.3f, %.3f)' % (i, s1, look, color, n, u, v, nx, nz))
        # apply only 60% of the correction (applying all of it overshot left/right and oscillated; the real camera's FOV seems narrower than 60°)
        moved = math.hypot(nx - x, nz - z)
        x, z = x + 0.6 * (nx - x), z + 0.6 * (nz - z)
        if moved < 0.006:
            break
    r = math.hypot(x, z); s1 = round(90 + math.degrees(math.atan2(-z, x)))
    look, pre, grasp = poses(r)
    if not (pre and grasp):
        log('cube at (%.3f, %.3f) cannot be grasped' % (x, z)); return None
    return {'x': round(x, 4), 'z': round(z, 4), 'r': round(r, 4), 'base': s1, 'look': look, 'pre': pre, 'grasp': grasp, 'color': color}


if __name__ == '__main__':
    load_geo()
    res = locate()
    move(90, [90, 90, 90])
    print(json.dumps(res))
