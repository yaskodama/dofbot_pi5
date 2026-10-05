#!/usr/bin/env python3
# cam_service.py — the "Camera" node running on the camera-duty Pi 5 (Linux).
#
# 1) Speaks the same messages as AIPL remote_call / gather (UDP/9010, one ASCII line).
#   Q <reqid> Camera find  <arg>   -> R <reqid> <n> <id> <cx> <cy> <deg> ...   (AprilTag 36h11; "0" if none)
#   Q <reqid> Camera shot  <arg>   -> R <reqid> <path>                         (saved to /tmp/cam_<reqid>.jpg)
#   Q <reqid> Camera mean  <arg>   -> R <reqid> <mean brightness>
#   H <reqid>                      -> A <reqid>                                 (reply to neighbors())
#   Anything else gets "err". A resend with the same (sender, reqid) gets the previous answer unchanged.
# 2) Serves the latest frame over HTTP/8090 (the Xinu simulator window shows it continuously in an <img>).
#   GET /snap.jpg   latest JPEG        GET /find   tag detection (text, same as UDP find)
#
# A single resident thread keeps capturing; UDP and HTTP only read the "latest frame".
# Start: python3 cam_service.py [--dev /dev/video0] [--port 9010] [--http 8090]
import socket, sys, time, cv2, argparse, threading, math
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ap = argparse.ArgumentParser()
ap.add_argument('--dev', default='/dev/video0')
ap.add_argument('--port', type=int, default=9010)
ap.add_argument('--http', type=int, default=8090)
a = ap.parse_args()

cap = cv2.VideoCapture(a.dev, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
                              cv2.aruco.DetectorParameters())

latest = {'frame': None, 'jpg': None, 't': 0.0, 'n': 0}
lock = threading.Lock()

def capture_loop():
    while True:
        ok, f = cap.read()
        if not ok:
            time.sleep(0.05); continue
        ok2, buf = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 80])
        with lock:
            latest['frame'] = f
            if ok2: latest['jpg'] = buf.tobytes()
            latest['t'] = time.time(); latest['n'] += 1

threading.Thread(target=capture_loop, daemon=True).start()

def frame():
    with lock:
        return None if latest['frame'] is None else latest['frame'].copy()

def find():
    f = frame()
    if f is None: return 'err'
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = det.detectMarkers(g)
    if ids is None or len(ids) == 0: return '0'
    out = [str(len(ids))]
    for c, i in zip(corners, ids.flatten()):
        p = c[0]
        cx, cy = p[:, 0].mean(), p[:, 1].mean()
        deg = math.degrees(math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0]))
        out += [str(int(i)), str(int(cx)), str(int(cy)), str(int(round(deg)))]
    return ' '.join(out)

def shot(reqid):
    f = frame()
    if f is None: return 'err'
    path = '/tmp/cam_%s.jpg' % reqid
    cv2.imwrite(path, f)
    return path

def mean():
    f = frame()
    return 'err' if f is None else str(int(f.mean()))

class H(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/snap.jpg':
            with lock: j = latest['jpg']
            if j is None: self._send(503, 'text/plain', b'no frame\n')
            else: self._send(200, 'image/jpeg', j)
        elif p == '/find':
            self._send(200, 'text/plain', (find() + '\n').encode())
        elif p == '/':
            with lock: n, t = latest['n'], latest['t']
            self._send(200, 'text/plain', ('cam_service %s frames=%d age=%.2fs\n' % (a.dev, n, time.time() - t)).encode())
        else:
            self._send(404, 'text/plain', b'no such path\n')

def http_loop():
    ThreadingHTTPServer(('', a.http), H).serve_forever()
threading.Thread(target=http_loop, daemon=True).start()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('', a.port))
memo = {}          # (addr, reqid) -> answer
print('cam_service: %s on UDP/%d, HTTP/%d' % (a.dev, a.port, a.http), flush=True)
while True:
    data, addr = s.recvfrom(1024)
    line = data.decode('ascii', 'ignore').strip()
    parts = line.split(' ', 3)
    if len(parts) >= 2 and parts[0] == 'H':
        s.sendto(('A %s\n' % parts[1]).encode(), addr); continue
    if len(parts) < 3 or parts[0] != 'Q': continue
    reqid, actor, meth = parts[1], parts[2], (parts[3].split(' ', 1)[0] if len(parts) > 3 else '')
    key = (addr[0], reqid)
    if key in memo:
        ans = memo[key]
    else:
        t0 = time.time()
        if actor != 'Camera': ans = 'err'
        elif meth == 'find': ans = find()
        elif meth == 'shot': ans = shot(reqid)
        elif meth == 'mean': ans = mean()
        else: ans = 'err'
        memo[key] = ans
        if len(memo) > 512: memo.pop(next(iter(memo)))
        print('%s %s.%s -> %s (%.2fs)' % (addr[0], actor, meth, ans, time.time() - t0), flush=True)
    s.sendto(('R %s %s\n' % (reqid, ans)).encode(), addr)
