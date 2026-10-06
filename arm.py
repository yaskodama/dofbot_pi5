# Common part streamed from the Mac over SSH: Arm_Lib (bus 1), 0.3 s between commands, reads are retried, photo goes to /tmp/cam.jpg
import sys, time, cv2
sys.path.insert(0, '/home/pi/colcon_ws/src/Arm_Lib')
from Arm_Lib import Arm_Device
A = Arm_Device(i2c_bus=1); time.sleep(0.3)
def rd(i):  # None -> retry handled below
    for t in range(3):
        v = A.Arm_serial_servo_read(i)
        if v is not None: return v
        time.sleep(0.3)
    return None
def angles(): return [rd(i) for i in range(1, 7)]
def move(p, ms):
    A.Arm_serial_servo_write6_array(list(p), ms); time.sleep(0.3); time.sleep(ms/1000 + 0.4)
def move1(i, a, ms):
    A.Arm_serial_servo_write(i, a, ms); time.sleep(0.3); time.sleep(ms/1000 + 0.4)
def shot(path='/tmp/cam.jpg'):
    cap = cv2.VideoCapture('/dev/video0', cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok = False
    for i in range(10): ok, f = cap.read()
    cap.release()
    if ok: cv2.imwrite(path, f)
    return ok

# ---- Planar IK (URDF: shoulder height 0.1075, upper arm 0.08285, forearm 0.08285, wrist -> servo-5 center 0.07385, grasp point a further LG)
import math
H, L, L3, LG = 0.1075, 0.08285, 0.07385, 0.06
def fk(s2, s3, s4):
    A1 = math.radians(90 - s2); A2 = A1 + math.radians(90 - s3); A3 = A2 + math.radians(90 - s4)
    x = L*math.sin(A1) + L*math.sin(A2) + L3*math.sin(A3); z = H + L*math.cos(A1) + L*math.cos(A2) + L3*math.cos(A3)
    return (x, z, x + LG*math.sin(A3), z + LG*math.cos(A3))   # (P5x, P5z, gripx, gripz)
def ik(gx, gz, tilt=10):
    """Grasp point (forward gx m, height gz m), hand tilt tilt° (forward from vertical) -> (s2,s3,s4)"""
    A3 = math.radians(180 - tilt)
    px, pz = gx - LG*math.sin(A3), gz - LG*math.cos(A3)
    wx, wz = px - L3*math.sin(A3), pz - L3*math.cos(A3) - H
    d = math.hypot(wx, wz)
    if d > 2*L: raise ValueError('reach %.3f' % d)
    half = math.acos(d / (2*L)); dirn = math.atan2(wx, wz)
    A1 = dirn - half; A2 = dirn + half
    s2 = 90 - math.degrees(A1); s3 = 90 - math.degrees(A2 - A1); s4 = 90 - math.degrees(A3 - A2)
    return [round(s2), round(s3), round(s4)]
def goto(s1, gx, gz, tilt=10, s5=90, s6=30, ms=1000):
    p = [s1] + ik(gx, gz, tilt) + [s5, s6]; move(p, ms); return p
