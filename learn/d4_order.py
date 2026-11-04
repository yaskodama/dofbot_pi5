#!/usr/bin/env python3
# d4_order.py — the run order of Phase D-4 (protocol D_v1 addendum 11/4): θ0 / θ*6 / θ*7 interleaved on the same day.
#
#   python3 learn/d4_order.py [SEED]       writes ~/paper1_sim2real/data/d4/order.json and prints the table
#
# Block-randomized: 10 blocks, each block one placement with the three θ once each (order shuffled), each of the
# 5 inner-edge placements in 2 blocks (block order shuffled). So every θ meets every placement twice, and a drift over
# the day (light, the board warming up) falls on the three θ alike.
import sys, os, json, random

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20261117
PLACES = [('green', 'H1'), ('green', 'H2'), ('green', 'H3'), ('blue', 'P2'), ('blue', 'H2')]
THETAS = ['theta0', 'theta_star6', 'theta_star7']
OUT = os.path.expanduser('~/paper1_sim2real/data/d4/order.json')


def order(seed):
    rng = random.Random(seed)
    blocks = PLACES * 2
    rng.shuffle(blocks)
    rows = []
    for b, (col, pos) in enumerate(blocks, 1):
        ths = list(THETAS)
        rng.shuffle(ths)
        for th in ths:
            rows.append({'id': 'X%02d' % (len(rows) + 1), 'block': b, 'color': col, 'pos': pos, 'theta': th})
    return rows


def main():
    rows = order(SEED)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump({'seed': SEED, 'places': PLACES, 'thetas': THETAS, 'rows': rows}, f, ensure_ascii=False, indent=1)
    for r in rows:
        print('%s  block %2d  %-5s %-3s  %s' % (r['id'], r['block'], r['color'], r['pos'], r['theta']))
    for th in THETAS:                                   # balance check: every θ meets every placement twice
        n = {}
        for r in rows:
            if r['theta'] == th:
                n[(r['color'], r['pos'])] = n.get((r['color'], r['pos']), 0) + 1
        assert sorted(n.values()) == [2] * 5, (th, n)
    print('seed', SEED, '->', OUT)


if __name__ == '__main__':
    main()
