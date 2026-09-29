#!/usr/bin/env python3
# locate.py — 実機の手首カメラで立方体の位置（卓上の x, z）を測り、見る/手前/挟む姿勢を逆運動学で出す。
# カメラは手首の上面（指の軸から 3.2 cm）にあるので、「カメラの軸を立方体へ向けて撮る → 指の軸を合わせて挟む」。
# 1) 目標 (x, z) を見る姿勢へ動かして撮る  2) 青/緑の画素の重心を卓上（立方体の上面 y=3.5 cm）へ逆射影
# 3) その点を新しい目標にして繰り返す（画像の端で切れていると重心が内側へ寄るので数回）
# 出力（最後の行）: JSON {"x":..,"z":..,"base":..,"look":[..],"pre":[..],"grasp":[..],"color":..}
import math, json, sys, time, colorsys, urllib.request, os

B = 'http://192.168.3.101'
# 寸法は geometry.json（Xinu シミュレータの CG と同じ値。set_geo で差し替わる）
H0, L, L3, LG = 0.1075, 0.08285, 0.07385, 0.06
CAM_ALONG, CAM_UP, CUBE, FOV = 0.0625, 0.032, 0.035, 60.0
GEO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geometry.json')


def set_geo(g):
    """g: geometry.json の中身（{"H": {"v": ..}, ...}）。L1 と L2 は同じ長さとして扱う（逆運動学が等長 2 リンク）"""
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



A3, DIST = 165, 0.12                     # 手の傾き（鉛直上から）、カメラから立方体までの距離
TIP_Y = 0.015                            # 挟む・置くときの指先の高さ（卓上 1.5 cm。0.8 cm では実機が卓に当たった。3 cm の立方体に 1.5 cm 掛かる）
# 実機の指は模型より長い: 模型で 2.3 cm に下げると実機は卓に当たり本体が浮いた（2026-09-27、2 回）。
# 卓に当たると本体が浮くだけで関節は指令どおり回るので、角度の読み戻しでは当たりを検出できない。
PRE_BACK = 0.035                         # 手前は挟む位置から軸に沿って 3.5 cm


def get(url, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                b = r.read()
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
    """カメラの軸が立方体の中心を通る姿勢。手の傾きとカメラの距離を選ぶ（腕の最下点は卓上 4 cm 以上）。
    指を 8.3 cm とすると、見られるのは土台の軸から 14〜23 cm"""
    for a3 in range(180, 109, -5):
        a = math.radians(a3); d3 = (math.sin(a), math.cos(a)); up = (-math.cos(a), math.sin(a))   # up = 手首の上面
        for dist in (0.12, 0.11, 0.13, 0.10, 0.14, 0.09, 0.15, 0.16, 0.08):
            c = (r - d3[0] * dist, CUBE / 2 - d3[1] * dist)
            s = ik(c[0] - d3[0] * CAM_ALONG - up[0] * CAM_UP, c[1] - d3[1] * CAM_ALONG - up[1] * CAM_UP, a3)
            if s and low_point(s) >= 0.04:                      # 指先も立方体（3 cm）の 1 cm 上
                return s, a3, dist
    return None, None, None


def grasp_poses(r):
    """指の軸が立方体の中心を通り、指先が卓上 TIP_Y の 挟む姿勢と、その軸上 PRE_BACK 手前"""
    for a3 in range(180, 129, -5):
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
    """指の軸が傾き a3 で (r, 立方体の中心の高さ) を通り、指先の高さが tip_y の姿勢（s2 s3 s4）"""
    a = math.radians(a3); d3 = (math.sin(a), math.cos(a))
    t = (tip_y - CUBE / 2) / d3[1]
    tip = (r + d3[0] * t, tip_y)
    return ik(tip[0] - d3[0] * (L3 + LG), tip[1] - d3[1] * (L3 + LG), a3)


def read_angles():
    """腕の角度。動いている最中は基板が "?" を返す。
    ★ Xinu の /arm read は「6 軸とも読めない」が 3 回続くと腕の基板にリセットを送り、そのリセットで基板が
      電源を入れ直すまで戻らなくなる（2026-09-28 に 4 回）。だから続けて読むのは 2 回まで、間を 1.5 s あける。
      読めなければ None（呼ぶ側は確かめを飛ばす）"""
    for i in range(2):
        w = arm_udp('read').split()
        if len(w) >= 7 and w[0] == 'angles' and '?' not in w[1:5]:
            return [int(v) if v != '?' else -1 for v in w[1:7]]
        if i == 0:
            time.sleep(1.5)
    return None


def lower(move_fn, angles_fn, s1, r, grip, top=0.05, floor=TIP_Y, step=0.005, back=0.008, tol=3, log=print):
    """指先を卓上 top から step ずつ下げる。各段で角度を読み戻し、肩・肘・手首のどれかが指令から tol° より
    ずれたら卓（か物）に当たったとみなし、back 上げて止める。当たらなければ floor で止める。
    返り値: 止まった指先の高さ（m）。angles_fn が None なら読み戻さない（模型）"""
    a3 = grasp_poses(r)[2]
    if a3 is None:
        raise RuntimeError('cannot reach %.3f' % r)
    y = top
    while not pose_at(r, y, a3) and y > floor + 1e-6:        # 高すぎて姿勢が作れない所は飛ばす
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


def cam_frame(s1, s):
    """姿勢でのカメラの位置と軸（3D、x 前 / y 上 / z 横）"""
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
    """Xinu 板から 160x120 を 1 枚 → (W, H, [(r,g,b) 0..1])"""
    time.sleep(2.2)                                                       # 腕が止まるのを待つ
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


def blob(px, W, H, rot180):
    """緑/青の画素の重心（モデルの向きの画像座標）と色・数・外接枠"""
    us, vs, cnt = [], [], {'green': 0, 'blue': 0}
    for y in range(H):
        for x in range(W):
            h, s, val = colorsys.rgb_to_hsv(*px[y * W + x])
            if s < 0.35 or val < 0.2:
                continue
            deg = h * 360
            k = 'green' if 75 <= deg <= 165 else 'blue' if 190 <= deg <= 260 else None
            if k:
                cnt[k] += 1
                us.append(W - 1 - x if rot180 else x); vs.append(H - 1 - y if rot180 else y)
    if len(us) < max(20, W * H // 400):
        return None
    return sum(us) / len(us), sum(vs) / len(vs), max(cnt, key=cnt.get), len(us), (min(us), max(us), min(vs), max(vs))


_rid = [int(time.time() * 1000) % 1000000 + 300000]


def arm_udp(cmd, board=('192.168.3.101', 9010), tries=8):
    """板の "dofbot" アクターへ AIPL の remote_call と同じ電文で送る（UDP、答えが来るまで再送）。
    HTTP の /arm/pose は窓の取得と重なると空で返り、腕が動かないまま進んでしまう"""
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


def move(s1, s, ms=1500, grip=30):
    for _ in range(3):                  # I2C の書き込みはときどき FAIL rc=-2 で返る。送り直せば通る
        ans = arm_udp('pose %d %d %d %d 90 %d %d' % (s1, s[0], s[1], s[2], grip, ms))
        if ans.startswith('ok'):
            return True
        time.sleep(0.3)
    raise RuntimeError('arm did not move: %r' % ans)


def check_pose(s1, s, tol=6):
    """腕が本当にその姿勢にいるか（角度を読み戻す）。基板はサーボが死んでいても pose に ok を返す"""
    ang = read_angles()
    if ang:
        got = ang[:4]
        want = [s1] + list(s)
        if all(abs(g - t) <= tol for g, t in zip(got, want)):
            return True
        raise RuntimeError('arm is not at the pose: want %s got %s' % (want, got))
    return None                          # 読めない（動作中など）。確かめは飛ばす —— 読み直しを重ねると基板リセットを招く


def locate(move_fn=None, shoot_fn=None, rot180=False, x=0.17, z=0.0, rounds=7, log=print):
    """move_fn(s1, [s2,s3,s4]) で腕を動かし、shoot_fn() -> (W, H, [(r,g,b) 0..1]) で撮る。
    rot180: 画像が 180° 回っているか（実機 True、CG False）"""
    move_fn = move_fn or (lambda s1, s: move(s1, s))
    shoot_fn = shoot_fn or shoot_board
    color = None
    # はじめの 1 枚に立方体が無ければ、卓上を順に見て探す（押されて動いたとき）
    starts = [(x, z)] + [(rr * math.cos(math.radians(yy)), -rr * math.sin(math.radians(yy)))
                         for rr in (0.15, 0.18, 0.21) for yy in (0, 20, -20)]
    for sx, sz in starts:
        r = math.hypot(sx, sz); s1 = round(90 + math.degrees(math.atan2(-sz, sx)))
        look = poses(r)[0]
        if not look:
            continue
        move_fn(s1, look)
        img = shoot_fn()
        if img and blob(img[2], img[0], img[1], rot180):
            x, z = sx, sz
            break
        log('scan: nothing at %.1f cm, base %d' % (r * 100, s1))
    else:
        log('scan: no cube anywhere'); return None
    for i in range(rounds):
        r = math.hypot(x, z); s1 = round(90 + math.degrees(math.atan2(-z, x)))
        look = poses(r)[0]
        if not look:
            log('round %d: (%.3f, %.3f) is out of reach' % (i, x, z)); return None
        move_fn(s1, look)
        img = shoot_fn()
        if not img:
            log('round %d: no camera frame' % i); return None
        W, H, px = img
        f = (W / 2) / math.tan(math.radians(FOV / 2))
        b = blob(px, W, H, rot180)
        if not b:
            log('round %d: no green/blue in view at base %d look %s' % (i, s1, look)); return None
        u, v, color, n, box = b
        c, d3, l, up = cam_frame(s1, look)
        ray = tuple(d3[k] + l[k] * (u - W / 2) / f + up[k] * (H / 2 - v) / f for k in range(3))
        t = (CUBE - c[1]) / ray[1]                                          # 立方体の上面と交わる所
        nx, nz = c[0] + ray[0] * t, c[2] + ray[2] * t
        log('round %d: base %d look %s -> %s n=%d at (%.0f,%.0f) -> cube (%.3f, %.3f)' % (i, s1, look, color, n, u, v, nx, nz))
        # 補正は 6 割だけ動かす（全部動かすと左右に行き過ぎて振れた。実機の画角は 60° より狭いらしい）
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
