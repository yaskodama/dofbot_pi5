from arm import *
S1, S5 = 99, 105
def dev(cmd):
    a = angles(); a = [cmd[i] if a[i] is None else a[i] for i in range(6)]; return max(abs(a[i]-cmd[i]) for i in range(4)), a
def attempt(x):
    ap = [S1]+ik(x,0.045,15)+[S5,30]
    move(ap, 900)
    for z in (0.03, 0.015):
        p = [S1]+ik(x,z,10)+[S5,30]
        move(p, 700); d, a = dev(p)
        if d >= 4:
            print(f"x={x:.3f} z={z}: obstacle dev={d} read={a}"); move(ap, 700); return None
    move1(6, 135, 700); a = angles(); g = a[5]
    print(f"x={x:.3f}: grip read={g} pose={a}")
    if g < 126:
        return p
    move1(6, 30, 500); move(ap, 700); return None
for x in (0.155, 0.165, 0.145, 0.175):
    r = attempt(x)
    if r: print("HELD at", r); break
else:
    print("not held")
