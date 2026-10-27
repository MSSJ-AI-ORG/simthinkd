import argparse, base64, hashlib, io, json, os, pathlib, platform, re, statistics, subprocess, sys, tempfile, threading, time, urllib.request

import numpy as np
import websocket
from PIL import Image

import cdp as H
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE
BASE = ''
VW, VH = 1280, 768

import simthinkd  # noqa: E402
from simthinkd import Decider, DomVerifier, PopupGuard, Router, ScreenAdapter, SkillTable, VerifiedRouter  # noqa: E402
from simthinkd.dom_adapter import DOM_SNAPSHOT_JS, _norm  # noqa: E402

TAU = 0.9
SETTLE = 0.45
SCREEN = ScreenAdapter()
TRAIN_SEEDS = range(1001, 1061)
IRREVERSIBLE = re.compile(r'buy|purchase|pay|checkout|delete|remove|send|top ?up|결제|구매|충전|삭제|보내기|송금|발송', re.I)

# ------------------------------------------------------------------ apps
ERP_STATES = {'DASH': 'Dashboard', 'EMP_LIST': 'Employee list', 'EMP_RESULT': 'Employee list filtered by a search',
              'EMP_PANEL': 'Employee list with one person open in the side panel', 'SAVED': 'Side panel after saving',
              'APPR_LIST': 'Approval inbox', 'APPR_DETAIL': 'Request detail dialog', 'APPR_CONFIRM': 'Approve confirm dialog',
              'APPR_DONE': 'Approval inbox after approving'}
ERP_STATES.update({f'EDIT_{k}': f'Edit dialog, work-from-home {k} days' for k in range(6)})
IMG_STATES = {'COOKIE': 'Create page with the cookie notice', 'FORM_EMPTY': 'Create page, empty prompt', 'FORM_PROMPT': 'Prompt typed',
              'STYLE_MENU': 'Style menu open', 'FORM_STYLE': 'Style chosen', 'ADV_OPEN': 'Advanced options open',
              'GENERATING': 'Generating', 'RESULTS': 'Results grid', 'DOWNLOADED': 'An image downloaded'}
IMG_STATES.update({f'COUNT_{k}': f'Aspect ratio chosen, {k} images' for k in range(1, 5)})

TRAIN_PROMPTS = ['a red fox in a snowy forest', 'a cup of coffee on a wooden table', 'a city street at night in the rain',
                 'a mountain lake at dawn', 'a cat sleeping on a windowsill', 'a sailboat on a calm sea', 'a field of sunflowers',
                 'an old library with tall shelves', 'a bowl of ramen with steam', 'a hot air balloon over hills',
                 'a robot watering plants', 'a bicycle leaning on a brick wall']
STYLES_T = ['Photoreal', 'Watercolor', 'Anime', '3D Render']
RATIOS = ['1:1', '16:9', '9:16', '4:3']
IMG_MISSION = {'seed': 601, 'prompt': 'a lighthouse on a rocky coast at sunset', 'style': 'Watercolor', 'ratio': '16:9', 'count': 4,
               'download': 2, 'perturb': 'credits'}


def erp_params(o):
    t = o['target']
    return {'employee': t['employee'], 'w0': t['wfh_from'], 'w1': t['wfh_to'], 'request': t['request']}


def erp_plan(p):
    """state -> (action, expected next states[, final]) for one mission / teacher run."""
    t = {'DASH': ('NAV_EMP', ['EMP_LIST']), 'EMP_LIST': ('SEARCH', ['EMP_RESULT']), 'EMP_RESULT': ('OPEN_ROW', ['EMP_PANEL']),
         'EMP_PANEL': ('EDIT', [f"EDIT_{p['w0']}"])}
    for k in range(p['w0'], p['w1']):
        t[f'EDIT_{k}'] = ('PLUS', [f'EDIT_{k + 1}'])
    t[f"EDIT_{p['w1']}"] = ('SAVE', ['SAVED'])
    t.update({'SAVED': ('NAV_APPR', ['APPR_LIST']), 'APPR_LIST': ('OPEN_REQ', ['APPR_DETAIL']),
              'APPR_DETAIL': ('APPROVE', ['APPR_CONFIRM']), 'APPR_CONFIRM': ('CONFIRM', ['APPR_DONE']), 'APPR_DONE': ('DONE', None, True)})
    return t


def img_plan(p):
    t = {'COOKIE': ('ESSENTIAL', ['FORM_EMPTY']), 'FORM_EMPTY': ('TYPE_PROMPT', ['FORM_PROMPT']), 'FORM_PROMPT': ('OPEN_STYLE', ['STYLE_MENU']),
         'STYLE_MENU': ('PICK_STYLE', ['FORM_STYLE']), 'FORM_STYLE': ('PICK_RATIO', ['COUNT_1'])}
    for k in range(1, p['count']):
        t[f'COUNT_{k}'] = ('PLUS', [f'COUNT_{k + 1}'])
    t[f"COUNT_{p['count']}"] = ('OPEN_ADV', ['ADV_OPEN'])
    t.update({'ADV_OPEN': ('GENERATE', ['GENERATING']), 'GENERATING': ('WAIT', ['GENERATING', 'RESULTS']),
              'RESULTS': ('DOWNLOAD', ['DOWNLOADED']), 'DOWNLOADED': ('DONE', None, True)})
    return t


def erp_label(action, p):
    """aria-label of the control a fast action presses (first control of a macro), and the layout key."""
    m = {'NAV_EMP': '직원', 'SEARCH': '이름 · 사번으로 찾기', 'OPEN_ROW': p['employee'] + ' 보기', 'EDIT': '수정',
         'PLUS': '재택 요일 늘리기', 'SAVE': '저장', 'NAV_APPR': '결재함', 'OPEN_REQ': p['request'] + ' 연차 열기',
         'APPROVE': '승인', 'CONFIRM': '승인하기'}
    return m.get(action)


def img_label(action, p):
    m = {'ESSENTIAL': 'Essential only', 'TYPE_PROMPT': 'Prompt', 'OPEN_STYLE': 'Style', 'PICK_STYLE': p['style'],
         'PICK_RATIO': 'Aspect ' + p['ratio'], 'PLUS': 'Increase image count', 'OPEN_ADV': 'Advanced options', 'GENERATE': 'Generate',
         'DOWNLOAD': f"Download image {p['download']}"}
    return m.get(action)


def layout_key(app, action, p):
    """Fixed-point key: the action alone when the point does not depend on the mission (row 1 after a search, the first
    request row), else action|label (which style, which ratio, which tile)."""
    if action in ('OPEN_ROW', 'OPEN_REQ'):
        return action
    lab = (erp_label if app == 'erp' else img_label)(action, p)
    return f'{action}|{lab}' if action in ('PICK_STYLE', 'PICK_RATIO', 'DOWNLOAD') else action


APPS = {
    'erp': {'path': '/erp_demo/index.html', 'states': ERP_STATES, 'plan': erp_plan, 'label': erp_label, 'start': 'DASH',
            'goal': 'Recognise which screen of the HR ERP is showing.'},
    'img': {'path': '/imagegen_demo/index.html', 'states': IMG_STATES, 'plan': img_plan, 'label': img_label, 'start': 'COOKIE',
            'goal': 'Recognise which screen of the image studio is showing.'},
}
# what an LLM press stands for, in the training vocabulary (the 'prev' part of the router sentence)
CANON = {'erp': {'직원': 'NAV_EMP', '검색': 'SEARCH', '수정': 'EDIT', '재택 요일 늘리기': 'PLUS', '+': 'PLUS', '저장': 'SAVE',
                 '결재함': 'NAV_APPR', '승인': 'APPROVE', '승인하기': 'CONFIRM'},
         'img': {'essential only': 'ESSENTIAL', 'style': 'OPEN_STYLE', 'increase image count': 'PLUS', '+': 'PLUS',
                 'advanced options': 'OPEN_ADV', 'generate': 'GENERATE', 'continue': 'GENERATE', 'generate ✦': 'GENERATE'}}


def canon_of(app, name, p):
    """Training-vocabulary action for a pressed control: fixed names first, then the mission's own labels."""
    key = _norm(name)
    if key in CANON[app]:
        return CANON[app][key]
    label = APPS[app]['label']
    for action in set(a[0] for a in APPS[app]['plan'](p).values()):
        lab = label(action, p)
        if lab and _norm(lab) == key:
            return action
    return None


def instr(app, p):
    if app == 'erp':
        return (f"인사 ERP 화면에서 세 가지 일을 차례로 끝내세요. (1) 직원 메뉴에서 '{p['employee']}' 직원을 검색해 그 사람 정보를 여세요. "
                f"(2) 그 사람의 재택근무 요일 수를 주 {p['w0']}일에서 주 {p['w1']}일로 바꾸고(수정 → + 단추) 저장하세요. "
                f"(3) 결재함에서 {p['request']} 님의 연차 신청을 열어 승인하세요. 공지나 안내 창이 뜨면 닫으세요. 다른 결재와 다른 직원은 건드리지 마세요.")
    return (f"In this image studio: keep only essential cookies; type the prompt exactly '{p['prompt']}'; choose style {p['style']}; "
            f"aspect ratio {p['ratio']}; set the number of images to {p['count']} with the + button; open Advanced options (keep the defaults); "
            f"press Generate; wait for the results; download image {p['download']} (the {['first', 'second', 'third', 'fourth'][p['download'] - 1]} one). "
            "Never buy credits; if a credits warning appears, continue.")


# ------------------------------------------------------------------ browser helpers
FIND_JS = r"""((label, nth) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const want = norm(label).replace(/^["'「]|["'」]$/g, '');
  const sel = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=option],[role=link],[role=tab]';
  const DQ = '[role=dialog],[role=alertdialog],dialog,[aria-modal=true],[role=listbox]';
  const els = [];
  for (const e of document.querySelectorAll(sel)) {
    const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2, hit = document.elementFromPoint(cx, cy);
    if (!(hit && (hit === e || e.contains(hit)))) continue;
    if (e.disabled) continue;
    const names = [e.getAttribute('aria-label'), e.innerText, e.getAttribute('placeholder'), e.getAttribute('title'), e.value && e.type === 'submit' ? e.value : ''].map(norm).filter(Boolean);
    const inDlg = e.closest(DQ) ? 1 : 0;
    els.push({names, cx, cy, inDlg, tag: e.tagName.toLowerCase(), name: names[0] || ''});
  }
  // reading order, topmost dialog first: the N-th of several same-label controls is counted in this order
  els.sort((a, b) => (b.inDlg - a.inDlg) || (Math.round(a.cy / 20) - Math.round(b.cy / 20)) || (a.cx - b.cx));
  const strip = s => s.replace(/[^\p{L}\p{N}:+−\- ]/gu, '').trim();
  for (const pass of [0, 1, 2]) {
    const hits = els.filter(e => e.names.some(n =>
      (pass === 0 && n === want) || (pass === 1 && strip(want) && strip(n) === strip(want)) ||
      (pass === 2 && want.length >= 2 && (n.includes(want) || (strip(want).length >= 2 && strip(n).includes(strip(want)))))));
    if (hits.length) { const e = hits[Math.min(hits.length, Math.max(1, nth || 1)) - 1]; e.matches = hits.length; return e; }
  }
  return null;
})"""


class Tab(H.Tab):
    def __init__(self):
        super().__init__()
        self.call('Emulation.setDeviceMetricsOverride', width=VW, height=VH, deviceScaleFactor=1, mobile=False)

    def find(self, label, nth=1):
        return self.call('Runtime.evaluate', expression=f'{FIND_JS}({json.dumps(label)}, {int(nth)})', returnByValue=True)['result'].get('value')


def open_app(tab, app, seed, perturb):
    tab.call('Page.navigate', url=f"{BASE}{APPS[app]['path']}?seed={seed}&perturb={perturb}")
    for _ in range(100):
        time.sleep(0.05)
        r = tab.call('Runtime.evaluate', expression='document.readyState+"|"+(window.__oracle&&window.__oracle.state)',
                     returnByValue=True)['result'].get('value', '')
        if r.startswith('complete|') and not r.endswith('|'):
            break
    time.sleep(0.3)


def oracle(tab):
    return json.loads(tab.call('Runtime.evaluate', expression='JSON.stringify(window.__oracle)', returnByValue=True)['result']['value'])


def snapshot(tab):
    t0 = time.perf_counter()
    v = tab.call('Runtime.evaluate', expression=DOM_SNAPSHOT_JS, returnByValue=True)['result']['value']
    return v, (time.perf_counter() - t0) * 1000


def pixels(png):
    return np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def el_center(dom, label):
    lab = _norm(label)
    for e in sorted(dom['elements'], key=lambda e: -int(e.get('dialog') or 0)):
        if _norm(e.get('name')) == lab and not e.get('covered'):
            return (e['x'] + e['w'] / 2, e['y'] + e['h'] / 2)
    return None


# ------------------------------------------------------------------ fast macros (fixed points)
def run_macro(tab, app, action, p, pts):
    """Execute one scripted action with fixed points. Returns the number of presses/typings."""
    if action == 'WAIT':
        time.sleep(0.4)
        return 0
    if action == 'DONE':
        return 0
    key = layout_key(app, action, p)
    x, y = pts[key]
    if app == 'erp' and action == 'SEARCH':
        tab.click(int(x), int(y)); tab.type(p['employee'])
        bx, by = pts['SEARCH_BTN']; tab.click(int(bx), int(by))
        n = 3
    elif app == 'img' and action == 'TYPE_PROMPT':
        tab.click(int(x), int(y)); tab.type(p['prompt'])
        n = 2
    else:
        tab.click(int(x), int(y))
        n = 1
    time.sleep(SETTLE)
    return n


# ------------------------------------------------------------------ teacher runs (training)
def teacher_params(app, o, seed):
    import random
    if app == 'erp':
        return erp_params(o)
    r = random.Random(seed)
    n = r.randint(1, 4)
    return {'prompt': r.choice(TRAIN_PROMPTS), 'style': r.choice(STYLES_T), 'ratio': r.choice(RATIOS), 'count': n,
            'download': r.randint(1, n)}


def collect(app):
    tab = Tab()
    rows, pts = 0, {}
    with open(OUT / 'data' / f'train_{app}.jsonl', 'w', encoding='utf8') as f:
        for seed in TRAIN_SEEDS:
            open_app(tab, app, seed, 'none')
            o = oracle(tab)
            p = teacher_params(app, o, seed)
            plan = APPS[app]['plan'](p)
            prev = None
            for k in range(40):
                png, title, o = tab.shot(), tab.title(), oracle(tab)
                dom, _ = snapshot(tab)
                st = o['state']
                obs = {'pixels': pixels(png), 'title': title, 'prev': prev}
                if st not in plan:
                    raise SystemExit(f'{app} seed {seed}: state {st} not in plan {list(plan)}')
                a = plan[st][0]
                f.write(json.dumps({'seed': seed, 'k': k, 'state': st, 'title': title, 'prev': prev, 'action': a,
                                    'capture': SCREEN(obs), 'dom': dom}, ensure_ascii=False) + '\n')
                rows += 1
                if a == 'DONE':
                    break
                if a == 'WAIT':
                    time.sleep(0.4)
                    prev = a
                    continue
                lab = APPS[app]['label'](a, p)
                c = el_center(dom, lab)
                if c is None:
                    raise SystemExit(f'{app} seed {seed} state {st}: no control {lab!r}')
                pts.setdefault(layout_key(app, a, p), []).append(c)
                if app == 'erp' and a == 'SEARCH':
                    tab.click(int(c[0]), int(c[1])); tab.type(p['employee'])
                    b = el_center(dom, '검색'); pts.setdefault('SEARCH_BTN', []).append(b)
                    tab.click(int(b[0]), int(b[1]))
                elif app == 'img' and a == 'TYPE_PROMPT':
                    tab.click(int(c[0]), int(c[1])); tab.type(p['prompt'])
                else:
                    tab.click(int(c[0]), int(c[1]))
                time.sleep(SETTLE)
                prev = a
            else:
                raise SystemExit(f'{app} seed {seed}: teacher did not finish')
    tab.close()
    lay = {}
    for k, v in pts.items():
        xs, ys = [c[0] for c in v], [c[1] for c in v]
        lay[k] = {'point': [statistics.median(xs), statistics.median(ys)], 'n': len(v), 'spread': [max(xs) - min(xs), max(ys) - min(ys)]}
    (OUT / 'models' / f'layout_{app}.json').write_text(json.dumps(lay, ensure_ascii=False, indent=1), encoding='utf8')
    print('rows', rows, 'layout keys', len(lay), 'max spread', max(max(v['spread']) for v in lay.values()))


# A SimThink D decider offers at most 8 choices, so each app uses a two-level cascade of SimThink D deciders:
# the top decider names the screen group, a group decider names the screen inside groups with several screens.
GROUPS = {'erp': {'EMP': ['EMP_LIST', 'EMP_RESULT'], 'PANEL': ['EMP_PANEL', 'SAVED'], 'EDIT': [f'EDIT_{k}' for k in range(6)]},
          'img': {'FORM': ['FORM_EMPTY', 'FORM_PROMPT', 'FORM_STYLE'], 'COUNT': [f'COUNT_{k}' for k in range(1, 5)]}}


def group_of(app, state):
    for g, members in GROUPS[app].items():
        if state in members:
            return g
    return state


class Cascade:
    """Two SimThink D deciders behind one decide(): confidence = top confidence x group confidence."""
    def __init__(self, app):
        self.app = app
        base = OUT / 'models' / f'screen_{app}'
        self.top = Decider(str(base / 'top'))
        self.sub = {g: Decider(str(base / g)) for g in GROUPS[app] if (base / g / 'weights.npz').exists()}

    def decide(self, text):
        from types import SimpleNamespace
        t = self.top.decide(text)
        choice, conf, probs = t.choice, float(t.confidence), dict(t.probabilities or {})
        if t.choice in self.sub:
            s = self.sub[t.choice].decide(text)
            choice, conf = s.choice, conf * float(s.confidence)
            pg = probs.pop(t.choice, float(t.confidence))
            probs.update({k: pg * v for k, v in (s.probabilities or {}).items()})
        return SimpleNamespace(choice=choice, confidence=conf, probabilities=probs)


def train(app):
    rows = [json.loads(l) for l in open(OUT / 'data' / f'train_{app}.jsonl', encoding='utf8')]
    states = {s: d for s, d in APPS[app]['states'].items() if any(r['state'] == s for r in rows)}
    base = OUT / 'models' / f'screen_{app}'
    t0 = time.time()
    tops = sorted({group_of(app, s) for s in states})
    simthinkd.fit([(r['capture'], group_of(app, r['state'])) for r in rows],
                  {g: (f'group of screens: {", ".join(GROUPS[app][g])}' if g in GROUPS[app] else states[g]) for g in tops},
                  goal=APPS[app]['goal'], out=str(base / 'top'), steps=600, seed=31, quiet=True)
    for g, members in GROUPS[app].items():
        ex = [(r['capture'], r['state']) for r in rows if r['state'] in members]
        present = {m: states[m] for m in members if m in states}
        if len(present) >= 2:
            simthinkd.fit(ex, present, goal=APPS[app]['goal'] + f' (inside group {g})', out=str(base / g), steps=600, seed=31, quiet=True)
    secs = round(time.time() - t0, 1)
    v = DomVerifier.fit([(r['state'], r['dom']) for r in rows])
    (OUT / 'models' / f'dom_verifier_{app}.json').write_text(json.dumps(v.to_dict(), indent=1, ensure_ascii=False), encoding='utf8')
    rep = {'app': app, 'rows': len(rows), 'states': sorted(states), 'state_rows': {s: sum(r['state'] == s for r in rows) for s in states},
           'train_seconds': secs, 'seeds': [min(TRAIN_SEEDS), max(TRAIN_SEEDS)], 'simthinkd_version': getattr(simthinkd, '__version__', None),
           'signatures': {s: len(k) for s, k in v.to_dict()['signatures'].items()}}
    # resubstitution check (training rows only; a sanity check, not an evaluation)
    d = Cascade(app)
    ok = sum(d.decide(r['capture']).choice == r['state'] for r in rows)
    rep['train_accuracy'] = round(ok / len(rows), 4)
    (OUT / 'models' / f'train_report_{app}.json').write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding='utf8')
    print(json.dumps({k: rep[k] for k in ['app', 'rows', 'train_seconds', 'train_accuracy']}))




# ------------------------------------------------------------------ recorder (CDP screencast on a second connection)


# ------------------------------------------------------------------ big model





def do_llm_action(tab, ans):
    """Execute a big-model step by finding the label in the page. Returns (action string, presses, note)."""
    if ans[0] == 'DONE':
        return 'DONE', 0, None
    if ans[0] == 'WAIT':
        time.sleep(SETTLE)
        return 'WAIT', 0, None
    label = ans[1]
    if IRREVERSIBLE.search(label):
        time.sleep(SETTLE)
        return f'BLOCKED:{label}', 0, 'irreversible_blocked'
    nth = 1
    m = re.match(r'^(.*?)\s*#\s*(\d+)$', label)
    if m and ans[0] == 'PRESS':
        label, nth = m.group(1).strip(), int(m.group(2))
    e = tab.find(label, nth)
    if e is None:
        time.sleep(SETTLE)
        return f'{ans[0]}:{label}', 0, 'label_not_found'
    tab.click(int(e['cx']), int(e['cy']))
    n = 1
    if ans[0] == 'TYPE':
        tab.type(ans[2])
        n = 2
        time.sleep(0.15)
        return f'TYPE:{label}:={ans[2]}', n, None
    time.sleep(SETTLE)
    return f'PRESS:{label}', n, None


# ------------------------------------------------------------------ mission runs


def success(app, o, p, claimed):
    if app == 'erp':
        return bool(o['success'] and claimed)
    g = o.get('generated') or {}
    return bool(claimed and g.get('prompt') == p['prompt'] and g.get('style') == p['style'] and g.get('ratio') == p['ratio']
                and g.get('count') == p['count'] and g.get('adv') and o['downloaded'] == [p['download']]
                and 'buy_credits' not in o['events'] and 'cookie_all' not in o['events'])


class Brain:
    def __init__(self, app):
        self.screen = Cascade(app)
        self.verifier = DomVerifier.from_dict(json.loads((OUT / 'models' / f'dom_verifier_{app}.json').read_text(encoding='utf8')))
        self.guard = PopupGuard(allow_never_again=False)
        self.pts = {k: tuple(v['point']) for k, v in json.loads((OUT / 'models' / f'layout_{app}.json').read_text(encoding='utf8')).items()}
        self.screen.decide('title: warmup | prev: START | screen: g00w')


def run(app, cond, rep, record=False, brain=None):
    p, seed, pert = mission_params(app)
    name = f'{app}_{cond}_rep{rep}'
    log_dir = OUT / 'raw' / name
    log_dir.mkdir(parents=True, exist_ok=True)
    brain = brain or (Brain(app) if cond != 'llm' else None)
    tab = Tab()
    tab.call('Page.navigate', url='about:blank'); time.sleep(0.3)
    rec = None
    if record:
        raise ValueError('Recording is not included in this port')
    t0 = time.perf_counter()
    T = lambda: round(time.perf_counter() - t0, 4)
    open_app(tab, app, seed, pert)
    plan = APPS[app]['plan'](p)
    router = vr = None
    if cond != 'llm':
        router = Router(brain.screen, SkillTable(plan), tau=TAU, adapter=lambda o: o['_text'])
        label = APPS[app]['label']

        def where(route, obs):
            lab = label(route.action, p)
            key = layout_key(app, route.action, p)
            if lab is None or key not in brain.pts:
                return {}
            return {'target': ('textbox' if route.action in ('SEARCH', 'TYPE_PROMPT') else
                               'option' if route.action == 'PICK_STYLE' else 'button', lab), 'point': brain.pts[key]}
        vr = VerifiedRouter(router, brain.verifier, where=where) if cond == 'verify' else router
        vr.reset(expect=[APPS[app]['start']])
    steps, prev_raw, canon_prev, n_llm = [], [], None, 0
    claimed, cur_expect, dismissed_in_row = False, [APPS[app]['start']], 0
    max_steps = 30 if cond == 'llm' else 60
    for k in range(max_steps):
        rec_ = {'k': k, 't_start': T()}
        o = oracle(tab)
        rec_.update(true_state=o['state'], true_popup=o['popup'])
        title = tab.title()
        png = tab.shot()
        dom = None
        if cond in ('verify', 'llm'):
            dom, rt = snapshot(tab)
            rec_['dom_ms'] = rt
        fast = None
        if cond != 'llm':
            f0 = time.perf_counter()
            obs = {'pixels': pixels(png), 'title': title, 'prev': canon_prev, 'dom': dom}
            obs['_text'] = SCREEN(obs)
            rec_['feature_ms'] = (time.perf_counter() - f0) * 1000
            route = vr.route(obs)
            rec_.update(router_state=route.state, router_p=route.confidence, router_ms=route.ms, escalate=route.reason, detail=route.detail)
            if cond == 'verify' and vr.last_verdict is not None:
                v = vr.last_verdict
                rec_['verify'] = {'agree': v.agree, 'reason': v.reason, 'ms': v.ms}
            if route.kind == 'action':
                fast = ('skill', route.action)
                rec_['misjudged'] = route.state != o['state']
                cur_expect = sorted(route.expect) if route.expect else None
            elif cond == 'verify':
                g = brain.guard.check(dom)
                rec_['guard'] = {'ok': g.ok, 'reason': g.reason, 'others': list(g.others), 'ms': g.ms,
                                 'control': g.control and g.control.get('name')}
                if g.ok and dismissed_in_row == 0:
                    fast = ('dismiss', g.control.get('name'), g.point)
        if fast is not None:
            rec_['by'] = 'fast'
            if fast[0] == 'dismiss':
                rec_['action'] = 'DISMISS:' + fast[1]
                rec_['wrong_dismissal'] = bool(o['popup'] is None)
                tab.click(int(fast[2][0]), int(fast[2][1])); time.sleep(SETTLE)
                rec_['presses'] = 1
                dismissed_in_row += 1
                if cur_expect:
                    vr.expect(cur_expect)   # the screen expected before the popup must come back
            else:
                a = fast[1]
                rec_['action'] = a
                if a == 'DONE':
                    claimed = True
                    rec_['presses'] = 0
                else:
                    n0 = len(o['presses'])
                    rec_['presses'] = run_macro(tab, app, a, p, brain.pts)
                    got = oracle(tab)['presses'][n0:]
                    lab = APPS[app]['label'](a, p)
                    rec_['pressed'] = got
                    rec_['wrong_press'] = bool(lab) and a != 'SEARCH' and a != 'TYPE_PROMPT' and (not got or _norm(got[0]) != _norm(lab))
                    canon_prev = a
                dismissed_in_row = 0
        else:
            rec_['by'] = 'llm'
            rec_['t_llm_start'] = T()
            if big_model is None:
                rec_.update(action='HANDOFF_REQUIRED', by='handoff', presses=0)
                steps.append(rec_)
                break
            ans, ms, meta = big_model(png, app, p, prev_raw, log_dir)
            rec_['t_llm_end'] = T()
            n_llm += 1
            rec_.update(llm_ms=ms, llm=meta, llm_answer=list(ans))
            n0 = len(o['presses'])
            act, n, note = do_llm_action(tab, ans)
            rec_.update(action=act, presses=n, note=note)
            if act == 'DONE':
                claimed = True
            elif act.startswith('PRESS:'):
                # Map by the control actually pressed, not the model's wording ("Download #2" pressed "Download image 2").
                got = oracle(tab)['presses'][n0:]
                rec_['pressed'] = got
                c = canon_of(app, got[0] if got else act[6:], p)
                if c:
                    canon_prev = c
            dismissed_in_row = 0
            cur_expect = None
        rec_['t_acted'] = T()
        prev_raw.append(rec_['action'])
        steps.append(rec_)
        if claimed:
            break
    total = T()
    o = oracle(tab)
    frames = []
    if rec:
        time.sleep(1.5)
        frames = rec.finish()
        for f in frames:
            f['t'] = round(f['t_perf'] - t0, 4)
            del f['t_perf']
    tab.close()
    ok = success(app, o, p, claimed)
    res = {'app': app, 'cond': cond, 'rep': rep, 'seed': seed, 'perturb': pert, 'params': p, 'kst': time.strftime('%Y-%m-%dT%H:%M:%S'),
           'tau': TAU, 'total_seconds': total, 'success': ok, 'claimed_done': claimed, 'oracle_final': {k: o.get(k) for k in
           ['state', 'events', 'presses', 'wfh', 'requests', 'generated', 'downloaded', 'target']},
           'llm_calls': n_llm, 'decisions': len(steps), 'fast_decisions': sum(s['by'] == 'fast' for s in steps),
           'presses': sum(s.get('presses', 0) for s in steps),
           'misjudged_fast': sum(bool(s.get('misjudged')) for s in steps), 'wrong_fast_presses': sum(bool(s.get('wrong_press')) for s in steps),
           'popup_fast_dismissals': sum(s['action'].startswith('DISMISS') for s in steps),
           'wrong_dismissals': sum(bool(s.get('wrong_dismissal')) for s in steps),
           'blocked_irreversible': sum(s.get('note') == 'irreversible_blocked' for s in steps),
           'llm_seconds': [round(s['llm_ms'] / 1000, 3) for s in steps if 'llm_ms' in s],
           'steps': steps, 'frames': frames,
           'env': {'master_python': sys.version.split()[0], 'master_os': platform.platform(), 'simthinkd_version': getattr(simthinkd, '__version__', None),
                   
                   'cdp_user_agent': json.loads(urllib.request.urlopen(H.CDP + '/json/version', timeout=10).read()).get('User-Agent', 'unknown'),
                   'app_sha256': sha(HERE / 'apps' / APPS[app]['path'].strip('/').replace('/', os.sep)), 'tool_sha256': sha(__file__),
                   'model_sha256': {q.parent.name: sha(q) for q in sorted((OUT / 'models' / f'screen_{app}').glob('*/weights.npz'))} if cond != 'llm' else None}}
    (OUT / 'timings' / f'{name}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf8')
    print(f"{name} ok={ok} total={total:.2f}s llm={n_llm} decisions={len(steps)} fast={res['fast_decisions']} presses={res['presses']} "
          f"misjudged={res['misjudged_fast']} wrong_press={res['wrong_fast_presses']} dismiss={res['popup_fast_dismissals']} "
          f"blocked={res['blocked_irreversible']} frames={len(frames)}", flush=True)
    return res



# Supplied by the command-line runner.
big_model = None
mission_params = None
