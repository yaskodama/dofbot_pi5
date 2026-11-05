#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# material_ja.py — a Japanese reading copy of each advisor material (data/argue/forms/EP_material.txt -> EP_material_ja.txt)
# for the human advisor (protocol D_v1 addendum 11/5 16:30). The advisors still get the English text; this copy is for
# reading only and the English one is authoritative.
# Log lines (timestamps, the locator service, agent steps, code) are copied unchanged; only the prose lines are translated,
# line by line, by the model, with the instruction to translate and add nothing. Translations are cached per line.
#
#   python3 learn/material_ja.py [EP ...]       default: every EP_material.txt in the forms folder
import sys, os, re, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import argue_form as F

MODEL = 'claude-opus-5-5'
CACHE = os.path.join(F.OUT, 'material_ja_cache.json')
LOG = re.compile(r'^\s*(\d\d:\d\d:\d\d|127\.0\.0\.1|locate\(|->|\[\d+\]|```|[{}\]\[])')
ASK = """Translate each English line below into natural Japanese, for an expert roboticist reading the material.
Rules: translate only, add or drop nothing, no explanation. Keep setting names, Prolog terms, episode ids, numbers, units
and anything in backticks or quotes exactly as written. Keep leading '- ', '## ' and indentation. A line that is only code
or terms stays unchanged.
Input: a JSON array of strings. Answer with ONE JSON array of the same length (one translation per line), nothing else.

"""


def translate(lines):
    import anthropic
    c = anthropic.Anthropic()
    with c.messages.stream(model=MODEL, max_tokens=32000,
                           messages=[{'role': 'user', 'content': ASK + json.dumps(lines, ensure_ascii=False)}]) as s:
        msg = s.get_final_message()
    text = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
    out = json.loads(re.search(r'\[.*\]', text, re.S).group(0))
    if len(out) != len(lines):
        raise ValueError('got %d lines for %d' % (len(out), len(lines)))
    return out


def main():
    eps = sys.argv[1:] or sorted(os.path.basename(p)[:-len('_material.txt')] for p in glob.glob(os.path.join(F.OUT, '*_material.txt')))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    texts = {ep: open(os.path.join(F.OUT, ep + '_material.txt')).read().splitlines() for ep in eps}
    todo = sorted({l for ls in texts.values() for l in ls if l.strip() and not LOG.match(l) and l not in cache})
    print('%d lines to translate' % len(todo), flush=True)
    for i in range(0, len(todo), 60):
        part = todo[i:i + 60]
        cache.update(zip(part, translate(part)))
        json.dump(cache, open(CACHE, 'w'), ensure_ascii=False, indent=0)
        print('  %d/%d' % (min(i + 60, len(todo)), len(todo)), flush=True)
    for ep, ls in texts.items():
        head = ('（日本語の読み用の写し。助言者（LLM）に渡すのは英語の原文 %s_material.txt で、食い違えば原文が正。'
                'ログの行は訳さずそのまま。）\n\n' % ep)
        open(os.path.join(F.OUT, ep + '_material_ja.txt'), 'w').write(head + '\n'.join(cache.get(l, l) for l in ls) + '\n')
        print(ep)


if __name__ == '__main__':
    main()
