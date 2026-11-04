# openai_advisor.py — Phase D-5 (c): the advisor prompt of run_learn.ask_advisor sent to an OpenAI model instead of Claude.
# The key comes from OPENAI_API_KEY, or else from ~/.openai_key (never printed). Model and settings are recorded per call.
import os

MODEL = os.environ.get('D5_OPENAI_MODEL', 'gpt-6.1-sol')
MAX_OUT = 16000                                   # reasoning tokens count against this; the answer itself is ~2k


def _key():
    k = os.environ.get('OPENAI_API_KEY', '').strip()
    if not k:
        with open(os.path.expanduser('~/.openai_key')) as f:
            k = f.read().strip()
    return k


def call(prompt):
    from openai import OpenAI
    c = OpenAI(api_key=_key())
    r = c.chat.completions.create(model=MODEL, max_completion_tokens=MAX_OUT,
                                  messages=[{'role': 'user', 'content': prompt}])
    u = r.usage
    return r.choices[0].message.content or '', {
        'model': r.model, 'in': u.prompt_tokens, 'out': u.completion_tokens,
        'reasoning': getattr(u.completion_tokens_details, 'reasoning_tokens', None),
        'finish': r.choices[0].finish_reason}
