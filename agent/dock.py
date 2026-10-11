#!/usr/bin/env python3
"""dock.py — the Mac-side dock for the mobile agent sort_agent.aipl.

  1. Sends the agent's source text to the Xinu simulator (aice-avm: POST /actor/loadsrc). The simulator compiles it
     and the agent drives the CG arm.
  2. When it is done, takes the agent's memory (pack) and sends the SAME source text to the Xinu board on the
     DOFBOT's Pi 5 (POST /cc), hands the memory back (unpack), and the agent drives the real arm.

The dock makes no decisions. It is the agent's clock and post office:
  - calls the agent's step(input) over the AIPL remote protocol (UDP/9010) on whichever host the agent is on,
  - sleeps when the agent says "wait <ms>", forwards "eye <method> <arg>" to the camera service (color_service,
    UDP/9012) and feeds the answer to the next step,
  - tells the simulator's AIPL program window which fragment ran ("PC <line> ..." to UDP/9011; the line is where
    the agent's source has the marker // [n]), and lists each move in the CG's PLAN.

usage: python3 dock.py [--only sim|real] [--no-cubes]
"""
import argparse, os, re, socket, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import udpq

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(HERE, 'sort_agent.aipl')
SERVICE = '127.0.0.1:9012'           # color_service: Camera / Plan
TRACE = ('127.0.0.1', 9011)          # aice-avm: the AIPL program window
HOSTS = {
    'sim':  {'name': 'Xinu simulator (aice-avm on the Mac)', 'load': 'http://127.0.0.1:8080/actor/loadsrc',
             'udp': '127.0.0.1:9010'},
    'real': {'name': 'Xinu on the DOFBOT Pi 5', 'load': 'http://192.168.3.101/cc',
             'udp': '192.168.3.101:9010'},
}
EYE_MS = {'locate': 200000, 'lower': 60000, 'held': 15000, 'get': 8000}

_tr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
def trace(msg):
    try:
        _tr.sendto(msg.encode(), TRACE)
    except OSError:
        pass

def log(s):
    print(time.strftime('%H:%M:%S ') + s, flush=True)

def post(url, data, timeout=30):
    req = urllib.request.Request(url, data=data, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace').strip()

def camera_ready():
    """The real camera must be streaming before the agent starts searching. After a load the board's camera has been
    seen idle (2026-10-11), and the camera service's own restart did not get through. Start it here; stop if it won't."""
    get = lambda p, t=8: urllib.request.urlopen('http://192.168.3.101' + p, timeout=t).read().decode('utf-8', 'replace')
    for attempt in range(3):
        try:
            st = get('/cam?w=160').split()
        except OSError:
            st = []
        if len(st) >= 6 and st[5] == 'streaming':
            log('   camera on the Pi 5: streaming')
            return
        try:
            r = get('/cam/start?frame=3&fps=10', 20).strip().splitlines()
        except OSError as ex:
            r = ['error %s' % ex]
        log('   camera on the Pi 5: %s -> start: %s' % (' '.join(st[5:6]) or 'no answer', r[-1] if r else ''))
        time.sleep(2)
    raise SystemExit('the Pi 5 camera does not stream (power-cycle the board, then run again)')

def fragment_lines(src):
    """marker // [n] -> line number (1-based) of that fragment in the agent's source"""
    out = {}
    for i, line in enumerate(src.splitlines(), 1):
        m = re.search(r'//\s*\[(\d+)\]', line)
        if m:
            out.setdefault(int(m.group(1)), i)
    return out

def visit(mode, src, carried):
    h = HOSTS[mode]
    lines = fragment_lines(src)
    where = 'sim' if mode == 'sim' else 'real'
    log('== migrate -> %s : POST %s (%d bytes of source)' % (h['name'], h['load'], len(src)))
    # The Xinu board's HTTP is single-threaded and the camera service polls it, so a POST can arrive mangled
    # (seen 2026-10-11: "=> 0" but the old program stayed). Check that the agent answers; send again if not.
    for attempt in range(1, 4):
        try:
            r = post(h['load'], src.encode())
        except OSError as ex:
            r = 'error %s' % ex
        log('   host says: %s' % (r.splitlines()[-1] if r else '(nothing)'))
        ver = udpq.call(h['udp'], 'agent', 'status', '', 5000)
        if ver is not None and ver.startswith('st='):
            break
        log('   the agent does not answer there yet (%r) - send it again (%d)' % (ver, attempt))
        time.sleep(2)
    else:
        raise SystemExit('the agent does not answer on %s' % h['udp'])
    if mode == 'real':
        camera_ready()
    if carried:
        log('   hand over memory: unpack(%r) -> %s' % (carried, udpq.call(h['udp'], 'agent', 'unpack', carried, 5000)))
    trace('SRC ' + AGENT)
    actor = 'SortAgent@' + ('simulator' if mode == 'sim' else 'pi5')
    inp, n_steps, t0 = '', 0, time.time()
    while True:
        out = udpq.call(h['udp'], 'agent', 'step', inp, 8000)
        n_steps += 1
        if out is None:
            raise SystemExit('step %d: no answer from the agent on %s' % (n_steps, h['udp']))
        parts = out.split(';', 3) + ['', '', '']
        tag, verb, arg, note = parts[0], parts[1], parts[2], parts[3]
        try:
            ln = lines.get(int(tag), 0)
        except ValueError:
            ln = 0
        trace('PC %d 1 %s %s' % (ln, actor, AGENT))
        inp = ''
        if verb == 'wait':
            i = udpq.call(SERVICE, 'Plan', 'push', '%s agent[%s] %s' % (where, tag, note[:70]), 2000)
            log('   [%s] line %d  %s  (wait %s ms)' % (tag, ln, note, arg))
            time.sleep(int(arg) / 1000.0)
            if i:
                udpq.call(SERVICE, 'Plan', 'done', '%s %s' % (i, note if note.startswith('ok') else 'ok ' + note), 2000)
        elif verb == 'eye':
            meth, _, earg = arg.partition(';')
            # the camera service takes "<mode> <arg>"; the agent's note field carries <arg> when it has one
            earg = note if not earg else earg
            q = (mode + ' ' + earg).strip()
            i = udpq.call(SERVICE, 'Plan', 'push', '%s agent[%s] eye.%s %s' % (where, tag, meth, earg), 2000)
            res = udpq.call(SERVICE, 'Camera', meth, q, EYE_MS.get(meth, 10000))
            if res is None:
                res = 'none' if meth == 'locate' else 'err'
            log('   [%s] line %d  eye.%s(%s) = %s' % (tag, ln, meth, q, res))
            if i:
                udpq.call(SERVICE, 'Plan', 'done', '%s %s' % (i, res), 2000)
            inp = res
        elif verb == 'next':
            log('   [%s] line %d  %s' % (tag, ln, note))
        elif verb == 'done':
            log('   [%s] line %d  done: placed %s, %d steps, %.0f s' % (tag, ln, arg, n_steps, time.time() - t0))
            log('   travel log: %s' % note)
            break
        else:
            raise SystemExit('step %d: unexpected answer %r' % (n_steps, out))
    trail = udpq.call(h['udp'], 'agent', 'pack', '', 5000) or ''
    return int(arg or 0), trail

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=['sim', 'real'])
    ap.add_argument('--no-cubes', action='store_true', help='do not re-place the CG cubes before the simulator run')
    ap.add_argument('--carry', default='', help='memory to hand to the agent on its first host (e.g. from an earlier visit)')
    a = ap.parse_args()
    src = open(AGENT).read()
    udpq.call(SERVICE, 'Plan', 'reset', '', 2000)
    order = [a.only] if a.only else ['sim', 'real']
    carried, res = a.carry, {}
    for mode in order:
        if mode == 'sim' and not a.no_cubes:
            log('CG: ' + urllib.request.urlopen('http://127.0.0.1:8091/sim?c=both', timeout=5).read().decode().strip())
        res[mode], carried = visit(mode, src, carried)
    if 'real' in order:
        # leave the board as we found it: its usual arm actor
        r = post(HOSTS['real']['load'], open(os.path.join(HERE, '..', 'aipl', 'dofbot_arm.aipl'), 'rb').read())
        log('== the agent leaves the Pi 5; board arm actor restored (%s)' % r.splitlines()[-1])
    log('== result: ' + ', '.join('%s placed %d' % (k, v) for k, v in res.items()))
    log('== the agent carried: %s' % carried)

if __name__ == '__main__':
    main()
