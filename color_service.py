#!/usr/bin/env python3
# color_service.py — Mac で走る「Camera」節点（色判定）。cam_service.py と同じ電文を話す。
#
#   Q <reqid> Camera color real s1 s2 s3 s4 -> R <reqid> green|blue|none   （Xinu 板の手首カメラ /cam から 1 枚取って判定）
#   Q <reqid> Camera color sim  s1 s2 s3 s4 -> R <reqid> green|blue|none   （CG の手首カメラの画像を判定）
#     s1..s4 は「見ている」ときの腕の姿勢（サーボ角）。
#   Q <reqid> Camera locate sim|real [grip] [green|blue|any] -> R <reqid> green|blue|none
#     grip: 探す間の指（既定 30=開）。色を指定するとその色だけを探す（1 つ置いたら残りの色だけ探すため）
#     立方体を探す（locate.py）: 見る姿勢で撮る → 色の塊の重心を卓上へ逆射影 → カメラを向け直す、を収束まで。
#     腕は color_service が動かす（sim: 127.0.0.1:8080/api/arm/sim、real: 板の /arm/pose）。
#   Q <reqid> Camera lower <sim|real> here <grip> | <base> <r_cm> <grip> -> R <reqid> ok <指先の高さ cm>
#     指先を卓上 5 cm から 0.5 cm ずつ下げ、各段で角度を読み戻す。関節が指令から 3° ずれたら卓に当たった
#     とみなして 0.8 cm 上げて止める（実機）。模型は 2.3 cm まで。
#   Q <reqid> Plan push <sim|real> <命令…>   -> R <reqid> <番号>     （これから実行する命令を PLAN に積む）
#   Q <reqid> Plan done <番号> <結果…>        -> R <reqid> ok          （結果を書き戻す。ok… なら成功）
#   Q <reqid> Plan reset                      -> R <reqid> ok
#     PLAN は Xinu シミュレータの CG に重ねて表示される（GET /plan）。locate / lower の腕の動きも自分で積む。
#     窓のボタン・スライダーから送った命令も HTTP で積む（GET /plan/push?where=&cmd=, /plan/done?i=&r=, /plan/reset）。
#   Q <reqid> Camera held <sim|real>          -> R <reqid> yes | no   （挟めているか: 指の読み戻し。角度は PLAN に出る）
#   Q <reqid> Camera get <sim|real> base|look|pre|grasp|where -> R <reqid> "84" / "91 4 1" …（直前の locate の結果）
#   H <reqid>                    -> A <reqid>
#   同じ (送り主, reqid) の再送には前の答えを返す。判定中の再送には答えない（remote_call がまた送ってくる）。
#
# ★ カメラは指より上（手首リンクの上面、指の軸から 3.2 cm）に付いていて、指の間は映らない。
#   だから sort.aipl は、腕をずらしてカメラの軸を立方体に向けて撮り、そのあと指の軸を立方体に合わせて挟む。
#   判定は、姿勢から順運動学でカメラの位置と向きを出し、
#   立方体（土台の前 17 cm、卓上の 3.5 cm 立方体）が画像のどこに写るかを射影して、
#   その枠（ROI）の中だけで判定する。CG のカメラも同じ幾何・同じ画角で描いている。
#   Xinu のカメラ画像は回っていない（土台と腕を動かして立方体の写る向きを実測、2026-09-27）。
#   Linux で撮ったときは 180° 回っていた。そのときは --rot180。
#
# 判定（real も sim も同じ関数）: ROI の画素を HSV にし、彩度と明度が足りる画素のうち
#   色相 75–165° を緑、190–260° を青として数える。多い方が ROI の 30% 以上なら その色、無ければ none
#   （細いケーブルや縁の色では反応しない）。
#
# HTTP（既定 8091、CORS 可）:
#   POST /simframe?w=80&h=60   本文 = RGB 各 1 バイトの生画素。Xinu シミュレータの DOFBOT 窓が CG カメラの画像を送る
#   POST /realframe?w=160&h=120 同じ形式。窓が板から受け取った実機カメラの画像を送る（2 秒以内なら板に聞かない）
#   GET  /sim?c=green|blue     CG の立方体の色を決めて置き直させる（窓が /stat の cube を見て従う）
#   GET  /stat                 直近の判定（JSON）。シミュレータの「色の認識率」バーが読む
#   GET  /geo, POST /geo       寸法（geometry.json）。シミュレータの CG と寸法線、ここの逆運動学・逆射影が同じ値を使う
#   GET  /last                 直近の判定（1 行）
#
# 起動: python3 color_service.py [--board 192.168.3.101] [--port 9012] [--http 8091]
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
RING = collections.deque(maxlen=40)          # 最近の画像 (時刻, 'real'|'sim', (w,h,px), 模型の関節角 or None)。移動中の「ちらっと」用
state = {'last': '-', 'simframe': None, 'simframe_t': 0.0, 'realframe': None, 'realframe_t': 0.0,
         'cube': {'color': 'green', 'seq': 0},
         'stat': {'seq': 0, 'mode': '-', 'answer': '-', 'green': 0, 'blue': 0, 'need': 30, 'max_v': 0, 'why': '', 'roi': None}}


# ---- 幾何: 腕とカメラの寸法は geometry.json（locate.py が読む。xinu.js の CG も /geo で同じ値を使う） ----
CUBE_X = 0.17                            # 立方体を置く所: 土台の軸から前へ 17 cm（xinu.js の CUBE.x と同じ）
NEED = 30                                # ROI の何 % が同じ色なら その色とするか


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
    """掴む所の立方体が、姿勢 pose のカメラ画像（W x H）で占める枠 (u0, v0, u1, v1)。写らなければ None"""
    cube = (CUBE_X, loc.CUBE / 2, 0.0)                         # 置く所は土台 90° の前方
    k = fk(pose); n3 = unit(cross(k['l'], k['d3']))          # カメラの「上」= 手首の上面の向き
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


HTTP_LOCK = threading.Lock()                 # 板の HTTP は一度に 1 件。係からの問い合わせを 1 本の列に並べる
loc.HTTP_LOCK = HTTP_LOCK                    # locate.py（予備の取り込み・アクターの載せ直し）も同じ列


def get(url, tries=6):
    for _ in range(tries):             # 板の HTTP は一度に 1 本。空や時間切れがあるので取り直す
        try:
            with HTTP_LOCK:            # 同時に 2 本出すと板の受け付けが追いつかず、HTTP 全体が止まった（2026-09-29）
                with urllib.request.urlopen(url, timeout=5) as r:
                    b = r.read()
            if b:
                return b
        except Exception:
            pass
        time.sleep(0.5)
    return b''


def grab_real():
    """実機の 1 枚。シミュレータの窓が板から受け取って送ってくる画像（/realframe）が新しければそれを使う
    （板の HTTP は一度に 1 本なので、窓と取り合わない）。無ければ板から 80x60 を直接取る"""
    # 問い合わせより後に届いた 1 枚を待つ（腕が止まる前の古い 1 枚で判定しない）
    asked, fresh = time.time(), False
    while time.time() - asked < 5:
        with lock:
            f, t = state['realframe'], state['realframe_t']
        if f is not None and t >= asked + 0.3:
            return f, ''
        fresh = fresh or (f is not None and time.time() - t < 2)     # 窓は開いている
        if not fresh and time.time() - asked > 1:
            break                                                    # 窓が無い → 板に直接聞く
        time.sleep(0.05)
    return grab_board()


def fetch_board_frame(W=160):
    """板の /cam から 1 枚（待たない）。off=0 で写し取らせてから続きを取る。→ (w, h, [(r,g,b) 0..1]) か None"""
    base = 'http://%s' % a.board
    t_cap = time.time()                              # 板が 1 枚を写し取る（off=0）のはこの頃
    hdr = get('%s/cam?w=%d&t=%d' % (base, W, time.time() * 1000), tries=2).decode('ascii', 'ignore').split()
    if len(hdr) >= 6 and hdr[5] == 'idle':           # 板の再起動後はカメラが止まっている → 配信を始めさせる
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
    return dw, dh, px


def glimpses_between(kind, t0, t1, prev, target, ms):
    """腕が prev から target へ（ms かけて）動いている間 [t0, t1] に取れた画像と、そのときの姿勢。
    模型は画像に添えた実際の関節角、実機は時刻で按分した見積もり"""
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
    """板のカメラを取り込み続ける（板へつなぐのはこの 1 本だけ）。
    以前はシミュレータの窓（Chrome）が板の :80 へ直接取りに行き、Chrome が要求なしの接続を張ったまま
    Xinu の単一スレッド HTTP を止めることが繰り返し起きた。窓は /realframe.bin をここから読む。"""
    while True:
        try:
            f = fetch_board_frame(160)
        except Exception:
            f = None
        if f:
            with lock:
                state['realframe'], state['realframe_t'] = f, time.time()
        time.sleep(0.8 if f else 3.0)                # 0.3 s では板の HTTP を詰まらせた


def grab_board():
    """Xinu 板から 80x60 を 1 枚。RGB565 小端 → (w, h, [(r,g,b) 0..1])"""
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
            elif 190 <= deg <= 260 and s >= 0.8:             # 水色のシート（彩度 0.3〜0.7）を青と数えない
                blue += 1
    ans = 'none'
    if max(green, blue) * 100 >= NEED * n:
        ans = 'green' if green >= blue else 'blue'
    return ans, 100.0 * green / n, 100.0 * blue / n, vmax


# ---- PLAN: 実行する命令の列（sort.aipl の Dancer.go と、locate / lower の腕の動き） ----
def plan_push(where, cmd, depth=0):
    with lock:
        pl = state.setdefault('plan', {'seq': 0, 'items': []})
        pl['seq'] += 1
        for it in pl['items']:
            if it['state'] == 'run' and it['depth'] >= depth:
                it['state'] = 'ok?'                 # 答えを書き戻さずに次へ進んだもの
        pl['items'].append({'i': pl['seq'], 'where': where, 'cmd': cmd, 'state': 'run', 'result': '', 'depth': depth, 't': time.time()})
        del pl['items'][:-200]
        return pl['seq']


def plan_done(i, result):
    with lock:
        for it in state.get('plan', {}).get('items', []):
            if it['i'] == i:
                it['state'] = ('ok' if result.startswith(('ok', 'angles', 'green', 'blue'))
                               else 'none' if result.strip() == 'none' else 'fail')   # none: 見つからない（確かめでは「挟めた」）
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
    """時刻 after より後に届いた 1 枚（窓が送る simframe / realframe）"""
    t0 = time.time()
    while time.time() - t0 < wait:
        with lock:
            f, t = state[which], state[which + '_t']
        if f is not None and t >= after:
            return f
        time.sleep(0.05)
    return None


def do_locate(mode, grip=30, want=None):
    """grip: 探す間の指（30 開 / 135 閉）。持ち上げたあとの確かめでは閉じたまま動かす（開くと落とす）"""
    if mode == 'sim':
        goal = {}
        def move_fn(s1, s):
            k = plan_push('sim', 'pose %d %d %d %d 90 %d 2500  (look)' % (s1, s[0], s[1], s[2], grip), 1)
            urllib.request.urlopen('http://127.0.0.1:8080/api/arm/sim?cmd=pose+%d+%d+%d+%d+90+%d+2500' % (s1, s[0], s[1], s[2], grip), timeout=5).read()
            goal['a'] = [s1] + list(s)
            time.sleep(2.8); plan_done(k, 'ok')
        def shoot_fn():
            # 模型がその姿勢に着いてから撮った画像だけを使う（窓が隠れて模型が止まっていると古い画像が届く）
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
                loc.move(s1, s, 2500, grip); time.sleep(2.8); loc.check_pose(s1, s)   # ゆっくり（1.5 s では振りが速すぎた）
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
    except Exception as ex:                                  # 腕が動かなかった等
        lines.append('locate stopped: %s' % ex); res = None
    for ln in lines:
        print('  locate(%s) %s' % (mode, ln), flush=True)
    if res and mode == 'real':                   # 実機は計算より 1° 左を掴みに行く → 土台を補正（geometry.json）
        g = state.get('geo') or {}
        res['base'] = int(round(res['base'] + float(g.get('real_base_offset', {}).get('v', 0))))
    with lock:
        state.setdefault('loc', {})[mode] = res
    if not res:
        put_stat(mode, 'none', 0, 0, 0, (lines[-1] if lines else 'locate failed'))
        return 'none'
    # 認識率バー: 最後の 1 枚で、立方体が写っている枠（重心のまわり、立方体の大きさ）を判定する
    img = shoot_fn()
    if img:
        W, H, px = img
        f = (W / 2) / math.tan(math.radians(loc.FOV / 2))
        half = f * loc.CUBE / 2 / 0.12
        b = loc.blob(px, W, H, mode == 'real' and a.rot180, res['color'])   # 見つけた立方体の色だけ（隣の立方体を混ぜない）
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
    """lower <sim|real> here <grip>          … locate で見つけた立方体の所へ段階的に降ろす
       lower <sim|real> <base> <r_cm> <grip>  … 置き場へ段階的に降ろす
       答え: "ok <止まった指先の高さ cm>" / "err ..."
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
        angles_fn = None     # 卓に当たると本体が浮くだけで角度は指令どおり → 読み戻しでは検出できない。読むと基板リセットを招く
    lines = []
    try:
        y = loc.lower(move_fn, angles_fn, s1, r, grip, log=lines.append)
    except Exception as ex:
        lines.append('lower stopped: %s' % ex); y = None
    for ln in lines:
        print('  lower(%s) %s' % (mode, ln), flush=True)
    return 'ok %.1f' % (y * 100) if y is not None else 'err'     # 理由は上の print（AIPL は "err" と比べる）


def do_held(mode):
    """挟めているか。実機: 135 で閉じた指（サーボ6）の読み戻しが held_max 以下なら物に当たって止まっている。
    模型: CG の立方体が手に付いているか（窓が送る cube_at.held）"""
    if mode == 'sim':
        with lock:
            ca = state.get('cube_at') or {}
        return 'yes' if ca.get('held') else 'no'
    g = state.get('geo') or {}
    lim = float(g.get('held_max', {}).get('v', 141))
    a6 = []
    time.sleep(0.8)                              # 腕が止まってから読む（読めない読みを重ねると基板リセットを招く）
    ang = loc.read_angles()
    if ang and ang[5] >= 0:
        a6.append(ang[5])
    if not a6:
        return 'err'
    v = sorted(a6)[len(a6) // 2]
    print('  held(real) servo6 = %s (limit %d)' % (a6, lim), flush=True)
    state['held_v'] = v
    # 閉じ切れずに止まったら「挟めた」。指令 145 で空なら 144〜145、3 cm の立方体を挟むと指がたわんで 139（2026-09-29 実測）。
    # 以前の 125〜134（無負荷の指の開きから決めた）では挟めているのに「挟めていない」とし、振り付けが指を開いて落としていた。
    # 開いた指（例: 40）は数えない
    return 'yes' if 120 <= v <= lim else 'no'


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
        if p == '/geo':                                     # シミュレータの「寸法」から保存
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
                    if which == 'simframe' and 'a' in kv:         # この画像を撮ったときの模型の関節角
                        try:
                            state['simframe_a'] = [int(v) for v in kv['a'].split(',')]
                        except ValueError:
                            state['simframe_a'] = None
                        RING.append((time.time(), 'sim', (w, h, px), state['simframe_a']))
                    if which == 'simframe' and 'cx' in kv:        # CG の立方体がいまどこにあるか（掴まれているか）
                        state['cube_at'] = {k2: float(kv[k2]) for k2 in ('cx', 'cy', 'cz', 'held') if k2 in kv}
            self._send('ok\n')
        else:
            self._send('no such path\n')

    def do_GET(self):
        p, _, q = self.path.partition('?')
        if p == '/sim':
            c = dict(x.split('=', 1) for x in q.split('&') if '=' in x).get('c', '')
            with lock:
                if c in ('green', 'blue', 'both'):          # both: 緑と青を並べて置く
                    state['cube'] = {'color': c, 'seq': state['cube']['seq'] + 1}
                cube = dict(state['cube'])
            self._send('CG cube = %s (placed again, #%d)\n' % (cube['color'], cube['seq']))
        elif p in ('/plan/push', '/plan/done', '/plan/reset'):   # Xinu シミュレータの窓から送った命令も同じ PLAN に積む
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
        elif p == '/realframe.bin':                     # 実機カメラの最新 1 枚（RGB 各 1 バイト）。窓が描く
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
                        w[2] if len(w) > 2 and w[2] in ('green', 'blue') else None)   # 探す色（無ければ多いほう）
        plan_done(k, ans)
    elif meth == 'lower':
        k = plan_push(w[0] if w else 'real', 'lower ' + ' '.join(w[1:]))
        ans = do_lower(arg)
        plan_done(k, ans)
    elif meth == 'get':
        ans = get_loc(arg)
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
        if key in busy:                 # 判定中の再送
            continue
        busy.add(key)
    threading.Thread(target=serve, args=(key, addr, reqid, actor, meth, arg), daemon=True).start()
