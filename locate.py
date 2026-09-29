#!/usr/bin/env python3
# locate.py — 実機の手首カメラで立方体の位置（卓上の x, z）を測り、見る/手前/挟む姿勢を逆運動学で出す。
# カメラは手首の上面（指の軸から 3.2 cm）にあるので、「カメラの軸を立方体へ向けて撮る → 指の軸を合わせて挟む」。
# 1) 目標 (x, z) を見る姿勢へ動かして撮る  2) 青/緑の画素の重心を卓上（立方体の上面 y=3.5 cm）へ逆射影
# 3) その点を新しい目標にして繰り返す（画像の端で切れていると重心が内側へ寄るので数回）
# 出力（最後の行）: JSON {"x":..,"z":..,"base":..,"look":[..],"pre":[..],"grasp":[..],"color":..}
import math, json, sys, time, colorsys, urllib.request, urllib.parse, os, threading
HTTP_LOCK = threading.Lock()    # 板の HTTP は一度に 1 件（color_service は自分の錠をここへ差し込む）

B = 'http://192.168.3.101'
# 寸法は geometry.json（Xinu シミュレータの CG と同じ値。set_geo で差し替わる）
H0, L, L3, LG = 0.1075, 0.08285, 0.07385, 0.06
CAM_ALONG, CAM_UP, CUBE, FOV = 0.0625, 0.032, 0.030, 60.0   # CUBE: 1 辺 3 cm（実測）
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
TIP_Y = 0.012                            # 挟む・置くときの指先の高さ（卓上 1.2 cm。0.8 cm では卓に当たり、1.5 cm では持ち上げる途中で落とした）
# 実機の指は模型より長い: 模型で 2.3 cm に下げると実機は卓に当たり本体が浮いた（2026-09-27、2 回）。
# 卓に当たると本体が浮くだけで関節は指令どおり回るので、角度の読み戻しでは当たりを検出できない。
PRE_BACK = 0.035                         # 手前は挟む位置から軸に沿って 3.5 cm



def http_get(url, timeout=5, body=None):
    """板への GET。終わったら必ず RST で切る（SO_LINGER 0）。
    urllib で時間切れになった接続を普通に閉じると、Xinu の単一スレッド HTTP がその接続の後始末を待ち続け、
    ほかの接続を一切受け付けなくなった。クライアントのプロセスを殺す（RST が出る）と 10 秒ほどで戻った（2026-09-29）"""
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
    """指の軸が立方体の中心を通り、指先が卓上 TIP_Y の 挟む姿勢と、その軸上 PRE_BACK 手前。
    手の傾きは 1° 刻みで探す（5° 刻みでは 13.6〜14.2 cm で 170° も 165° も関節の範囲を外れ、その間が抜けていた）"""
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
    if angles_fn is None:
        # 読み戻しで当たりを見ない（卓に当たっても関節は指令どおりで検出できない）なら、刻む意味は無い。
        # 0.5 cm ずつ 0.6 s 間隔で 8 回前後の指令を続けて送ると、腕の基板が止まった（2026-09-29、5 回の停止が
        # すべて「下ろす」処理の最中か直後）。1 回の指令で 2 s かけて下ろす
        s = pose_at(r, floor, a3)
        if not s:
            raise RuntimeError('no pose for tip %.3f at %.3f' % (floor, r))
        move_fn(s1, s, grip, 2000)
        time.sleep(2.3)
        log('lowered to %.1f cm in one slow move' % (floor * 100))
        return floor
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


def point_pose(r, tip_y=0.05):
    """立方体を置く位置を指先で指し示す姿勢（指先が卓上 tip_y）。作れる手の傾きを 1° 刻みで探す"""
    for a3 in range(180, 129, -1):
        s = pose_at(r, tip_y, a3)
        if s:
            return s
    return None


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


def blob(px, W, H, rot180, want=None, min_frac=0.015):
    """色の塊の重心（モデルの向きの画像座標）と色・数・外接枠。
    want: 'green' / 'blue' ならその色だけ。None なら画素の多いほうの色（緑と青が同時に写っても混ぜない）"""
    pts = {'green': [], 'blue': []}
    for y in range(H):
        for x in range(W):
            h, s, val = colorsys.rgb_to_hsv(*px[y * W + x])
            if s < 0.35 or val < 0.06:
                continue
            deg = h * 360
            # 青は彩度 0.8・明るさ 0.2 以上だけ: 卓の水色のシートは彩度 0.3〜0.7、青の立方体は 1.0（2026-09-29 実測）
            # 緑は明るさ 0.06 から: 白い紙の上ではカメラの露出が下がり、緑の立方体は明るさ 0.1 に写った（同日実測）
            k = ('green' if (75 <= deg <= 165 and s >= 0.45) else
                 'blue' if (190 <= deg <= 260 and s >= 0.8) else None)   # 青も明るさ 0.06 から（P2 の青は明るさ 0.1〜0.2 に写った）
            if k:
                pts[k].append((W - 1 - x if rot180 else x, H - 1 - y if rot180 else y))
    col = want if want in pts else max(pts, key=lambda c: len(pts[c]))
    p = pts[col]
    # 立方体（3 cm）は見る距離（13 cm 前後）で画像の 5% 以上に写る。1.5% 未満の塊は細い物（青いケーブル等）とみなす
    # （2026-09-29: 1.7〜7.7% の青い塊を追って緑の立方体の前で 3 回空振りした）
    if len(p) < max(20 if min_frac >= 0.015 else 8, int(W * H * min_frac)):
        return None
    us = [q[0] for q in p]; vs = [q[1] for q in p]
    # 画像の縦も横も 85% 以上に広がる塊は、立方体ではなく大きな面（本・箱・敷物）。
    # 2026-09-29: 左の置き場の横の緑の本を緑の立方体と判定した
    if max(us) - min(us) >= 0.85 * W and max(vs) - min(vs) >= 0.85 * H:
        return None
    return sum(us) / len(us), sum(vs) / len(vs), col, len(p), (min(us), max(us), min(vs), max(vs))


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


def reload_actor():
    """板の腕のアクター（dofbot_arm.aipl）を POST /cc で載せ直す。
    ときどきアクターが空の答えしか返さなくなる（原因不明、2026-09-28〜29 に 3 回）。載せ直すと戻る"""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aipl', 'dofbot_arm.aipl')
    try:
        with HTTP_LOCK:
            http_get(B + '/cc', 30, body=open(src, 'rb').read())     # POST。終わったら RST で切る
    except Exception:
        pass
    time.sleep(1.5)


def move(s1, s, ms=1500, grip=30):
    ans = ''
    for i in range(4):                  # I2C の書き込みはときどき FAIL rc=-2 で返る。送り直せば通る
        ans = arm_udp('pose %d %d %d %d 90 %d %d' % (s1, s[0], s[1], s[2], grip, ms))
        if ans.startswith('ok'):
            return True
        if ans == '' and i == 1:        # 空の答え = アクターが死んでいる → 載せ直す
            reload_actor()
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


# ---- 範囲をもれなく一巡して、卓上の立方体の一覧を作る ------------------------------------------------
# 手の届く帯（土台の軸から 14〜23 cm、正面から ±45°）を、カメラの写る範囲（見る距離 13 cm で横 15 cm・奥 11 cm）が
# 重なるように 2 列 × 4 か所に分け、決まった順（蛇行）に全部撮る。各画像の緑と青の塊を卓上へ逆射影して一覧にする。
# 以前は毎回同じ所から探し始めて最初に見えた物を追ったため、2 個目や少し外れた所の立方体を見落とした。
SURVEY = [(0.16, yy) for yy in (-40, -13, 13, 40)] + [(0.21, yy) for yy in (40, 13, -13, -40)]
PLACES = [(0.17, 150), (0.17, 30)]            # 置き場（ここに置いた立方体は数えない）
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
    """8 か所を順に撮り、見つかった立方体の一覧 [{'color','x','z','n','views'}] を返す（画素の多い順）。
    glimpse_fn(t0, t1, prev, target) -> [((w, h, px), pose4)]: 腕が prev から target へ動いている間に取れた画像と、
    そのときの姿勢（見積もり）。移動中に「ちらっと」写った立方体を記録し、一巡で探している色が見つからなければ
    その位置へ戻って見直す"""
    found, glimpses = [], []
    prev = None
    seen_uv = []                                   # (色, u, v, 土台) 画像のどこに写ったか
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
            for d in found:                                  # 3 cm 以内は同じ立方体
                if d['color'] == col and math.hypot(d['x'] - x, d['z'] - z) < 0.03:
                    w = d['n'] + b[3]
                    d['x'], d['z'] = (d['x'] * d['n'] + x * b[3]) / w, (d['z'] * d['n'] + z * b[3]) / w
                    d['n'], d['views'] = w, d['views'] + 1
                    break
            else:
                found.append({'color': col, 'x': x, 'z': z, 'n': b[3], 'views': 1})
            seen.append('%s(%d px at %.1fcm)' % (col, b[3], rr * 100))
        log('survey %.0f cm base %d: %s' % (r * 100, s1, ', '.join(seen) or 'nothing'))
    # 向きを変えても画像の同じ所（±8 px）に 3 か所以上で写った塊は、卓上の物ではなくカメラと一緒に動く物
    # （指に引っかかった立方体など）。2026-09-29: 緑が 4 つの向きで同じ 20.2 cm に「見つかった」
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
    # 探している色が一巡で見つからず、移動中にちらっと写っていたら、その位置へ戻って見直す
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
    """move_fn(s1, [s2,s3,s4]) で腕を動かし、shoot_fn() -> (W, H, [(r,g,b) 0..1]) で撮る。
    rot180: 画像が 180° 回っているか（実機 True、CG False）"""
    move_fn = move_fn or (lambda s1, s: move(s1, s))
    shoot_fn = shoot_fn or shoot_board
    color = None
    # まず範囲をもれなく一巡して一覧を作り、探している色の立方体を選ぶ（無ければ none）
    cands = [d for d in survey(move_fn, shoot_fn, rot180, log, glimpse_fn, want) if want in (None, d['color'])]
    if not cands:
        log('survey: no %s cube in reach' % (want or 'green/blue')); return None
    x, z, want = cands[0]['x'], cands[0]['z'], cands[0]['color']
    for i in range(rounds):
        r = math.hypot(x, z); s1 = round(90 + math.degrees(math.atan2(-z, x)))
        look = poses(r)[0]
        if not look and r < 0.141:
            # 内側の端: 見る姿勢が作れない所まで詰まったら、作れるいちばん手前（14.1 cm）にとどめて挟みに行く
            # （2026-09-29: 15 cm の P2 で推定が 13.6 cm になり、見つけているのにあきらめた。挟む姿勢は 13 cm でも作れる）
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
