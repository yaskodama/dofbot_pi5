# theta.py — the real robot's learnable settings (θ) for the LLM-advice learning loop (paper ① RQ5, real-robot version).
#
# The values live in learn/theta.json. When that file is absent every setting takes its CURRENT value
# (the one the humans tuned during E0′/E0m), so E0m and every other run behave exactly as before.
# learn/run_learn.py writes theta.json for a learning episode and removes it afterwards.
#
# The LLM advisor sees each setting's description and range, never the value the humans chose.
import json, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, 'theta.json')

# name: (current value (= human-tuned), value before the human fixes (θ0, Phase A start), lo, hi, kind, description for the advisor)
SCHEMA = {
    'blue_v_min':     (0.06, 0.20, 0.03, 0.40, 'float',
                       'minimum HSV value (brightness, 0..1) for a pixel to count as blue (hue 190-260 deg, saturation >= 0.8)'),
    'tilt_step_deg':  (1, 5, 1, 10, 'int',
                       'step (deg) of the hand-tilt search when looking for a grasp pose (searched from 180 down to 130)'),
    'inner_clamp_cm': (14.1, 0.0, 0.0, 15.0, 'float',
                       'when the refined cube estimate falls closer than the nearest radius with a camera look pose (about 13.8 cm), '
                       'clamp the estimate out to this radius and go grip instead of giving up; 0 = no clamp (give up)'),
    'min_blob_frac':  (0.015, 0.015, 0.005, 0.05, 'float',
                       'minimum blob size, as a fraction of the image, for a color blob to count as a cube'),
    'green_s_min':    (0.45, 0.45, 0.30, 0.80, 'float',
                       'minimum HSV saturation for a pixel to count as green (hue 75-165 deg)'),
    'refine_gain':    (0.6, 0.6, 0.3, 1.0, 'float',
                       'fraction of the camera-based position correction applied per refinement round'),
    'refine_rounds':  (7, 7, 3, 10, 'int',
                       'maximum number of camera refinement rounds before gripping'),
}

_cache = {'mtime': None, 'vals': {}}
OVERRIDE = {}      # learn/gate.py evaluates a proposal by setting values here (never written to disk)


def _load():
    try:
        m = os.path.getmtime(FILE)
    except OSError:
        _cache['mtime'] = None; _cache['vals'] = {}
        return _cache['vals']
    if m != _cache['mtime']:
        try:
            _cache['vals'] = json.load(open(FILE))
        except (OSError, ValueError):
            _cache['vals'] = {}
        _cache['mtime'] = m
    return _cache['vals']


def get(name):
    v = OVERRIDE[name] if name in OVERRIDE else _load().get(name, SCHEMA[name][0])
    return int(v) if SCHEMA[name][4] == 'int' else float(v)


def active():
    """the settings file in force (None = all current values), with its episode tag"""
    return _load() or None


def episode():
    return _load().get('_episode')


def current():
    return {k: get(k) for k in SCHEMA}


def check_bounds(vals):
    bad = []
    for k, v in vals.items():
        if k not in SCHEMA:
            bad.append('%s: no such setting' % k); continue
        _, _, lo, hi, kind, _ = SCHEMA[k]
        if kind == 'int' and int(v) != v:
            bad.append('%s: must be an integer' % k)
        if not (lo <= v <= hi):
            bad.append('%s=%s outside [%s, %s]' % (k, v, lo, hi))
        if k == 'inner_clamp_cm' and 0 < v < 13.8:
            bad.append('inner_clamp_cm=%s: must be 0 or >= 13.8 (no look pose closer than that)' % v)
    return bad


def write(vals, episode_tag):
    d = dict(vals); d['_episode'] = episode_tag; d['_written'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    json.dump(d, open(FILE, 'w'), indent=1)


def clear():
    try:
        os.remove(FILE)
    except OSError:
        pass
