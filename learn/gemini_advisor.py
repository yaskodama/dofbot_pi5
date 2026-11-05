# gemini_advisor.py — Phase D-2/D-5 (c), a third model family (protocol D_v1 addendum 11/5 16:00): the advisor prompt of
# run_learn.ask_advisor sent to a Google Gemini model. The key comes from GEMINI_API_KEY (never printed). REST, no SDK.
import os, json, urllib.request

MODEL = os.environ.get('D5_GEMINI_MODEL', 'gemini-3.1-pro-preview')
MAX_OUT = 16000                                   # thinking tokens count against this; the answer itself is ~2k


def call(prompt):
    body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': MAX_OUT}}
    req = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent' % MODEL,
                                 data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': os.environ['GEMINI_API_KEY']})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    c = r['candidates'][0]
    text = ''.join(p.get('text', '') for p in c.get('content', {}).get('parts', []) if not p.get('thought'))
    u = r.get('usageMetadata', {})
    return text, {'model': r.get('modelVersion', MODEL), 'in': u.get('promptTokenCount'), 'out': u.get('candidatesTokenCount'),
                  'reasoning': u.get('thoughtsTokenCount'), 'finish': c.get('finishReason')}
