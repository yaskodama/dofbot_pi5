"""AIPL remote wire protocol (UDP/9010, one ASCII line): Q <reqid> <actor> <method> <arg> -> R <reqid> <value>.
Retransmits every 200 ms with the SAME reqid; both the board and the simulator answer a reqid at most once."""
import socket, time, random, itertools
_ids = itertools.count(int(time.time() * 10) % 9000000 + 1000000)   # start away from earlier runs (peers cache answers per reqid)

def call(hostport, actor, meth, arg='', ms=3000):
    host, port = hostport.split(':')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.2)
    rid = next(_ids)
    msg = ('Q %d %s %s %s' % (rid, actor, meth, arg)).encode()
    pre = 'R %d ' % rid
    t0 = time.time()
    try:
        while time.time() - t0 < ms / 1000:
            s.sendto(msg, (host, int(port)))
            end = time.time() + 0.2
            while time.time() < end:
                try:
                    d, _ = s.recvfrom(4096)
                except socket.timeout:
                    break
                d = d.decode('utf-8', 'replace').rstrip('\n')
                if d.startswith(pre):
                    return d[len(pre):]
                if d == pre.rstrip():
                    return ''
        return None
    finally:
        s.close()
