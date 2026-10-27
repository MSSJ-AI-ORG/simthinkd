import hashlib
import importlib.util
from pathlib import Path
import sys
import json
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('screen_bench_run', HERE / 'run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
import engine


def test_apps():
    for name in ('erp_demo','imagegen_demo'):
        text = (HERE / 'apps' / name / 'index.html').read_text(encoding='utf-8')
        assert 'window.__oracle' in text
    assert list((HERE / 'apps/imagegen_demo/img').glob('*'))


@pytest.mark.parametrize('app,seed', [('erp',502),('erp',501),('erp',1234),('img',601)])
def test_mission_plan_and_oracle(app, seed):
    p = bench.mission(app, seed)
    assert p == bench.mission(app, seed)
    plan = engine.APPS[app]['plan'](p)
    assert plan == engine.APPS[app]['plan'](bench.mission(app, seed))
    oracle = {'success':True} if app == 'erp' else {'generated':{**p,'adv':True},'downloaded':[2],'events':[]}
    assert engine.success(app, oracle, p, True)
    assert not engine.success(app, oracle, p, False)
    if app == 'img':
        oracle['downloaded'] = [1]
    else:
        oracle['success'] = False
    assert not engine.success(app, oracle, p, True)


def test_known_seed():
    assert bench.mission('erp',502) == dict(employee='황유나', w0=2,w1=4,request='한서연')


def test_summary_hash_and_order():
    rows = [dict(app='erp',cond='decider',seed=502,rep=i,total_seconds=float(i),success=i==1,llm_calls=0) for i in (1,2)]
    a = bench.canonical(bench.build_summary(rows)).encode()
    b = bench.canonical(bench.build_summary(list(reversed(rows)))).encode()
    assert hashlib.sha256(a).digest() == hashlib.sha256(b).digest()
    assert bench.build_summary(rows)['groups']['erp/decider'] == dict(runs=2,successes=1,mean_seconds=1.5,llm_calls=0)


def test_llm_skip_without_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(bench,'find_chrome',lambda *_: pytest.fail('Chrome must not be used'))
    assert bench.main(['--app','erp','--cond','llm','--seed','502','--out',str(tmp_path)]) == 0
    assert 'skipped' in (tmp_path/'SUMMARY.json').read_text()


def test_seed_overlap_rejected(tmp_path):
    with pytest.raises(SystemExit):
        bench.main(['--app','erp','--cond','decider','--seed','1001','--out',str(tmp_path)])


def test_existing_results_preserved(tmp_path):
    (tmp_path/'SUMMARY.json').write_text('original')
    with pytest.raises(SystemExit):
        bench.main(['--app','erp','--cond','llm','--seed','502','--out',str(tmp_path)])
    assert (tmp_path/'SUMMARY.json').read_text() == 'original'


def test_model_bridge_json_roundtrip(tmp_path):
    helper = tmp_path/'bridge.py'
    helper.write_text("import json,sys\np=json.load(sys.stdin)\nassert p['schema']=='screen-bench-action/1'\nassert p['mission']\nprint(json.dumps({'action':'PRESS','label':'Download #2'}))\n")
    call = bench.model_adapter(json.dumps([sys.executable,str(helper)]))
    answer, elapsed, meta = call(b'fixture-not-a-real-image','img',bench.mission('img',601),[],tmp_path)
    assert answer == ('PRESS','Download #2')
    assert elapsed >= 0 and meta['error'] is None


def test_model_bridge_rejects_invalid_action(tmp_path):
    helper = tmp_path/'invalid.py'
    helper.write_text("print('{\"action\":\"UNKNOWN\"}')\n")
    call = bench.model_adapter(json.dumps([sys.executable,str(helper)]))
    with pytest.raises(ValueError,match='Invalid LLM action'):
        call(b'fixture','img',bench.mission('img',601),[],tmp_path)


def test_image_side_effects_rejected():
    p = bench.mission('img',601)
    for event in ('buy_credits','cookie_all'):
        assert not engine.success('img',{'generated':{**p,'adv':True},'downloaded':[2],'events':[event]},p,True)



def test_llm_press_maps_by_pressed_control():
    # r1 img decider rep 2: the model said "Download #2", the page pressed "Download image 2";
    # leaving it unmapped made the router download the same image again.
    p = bench.mission('img', 1)
    assert engine.canon_of('img', 'Download image 2', p) == 'DOWNLOAD'
    assert engine.canon_of('img', 'Watercolor', p) == 'PICK_STYLE'
    assert engine.canon_of('img', 'Buy credits', p) is None


def test_model_press_checked_on_the_resolved_control():
    # review 0.5.0 F1: "credits" resolved to "Buy credits" and was clicked
    class Tab:
        clicks = []
        def find(self, label, nth):
            return {'name': 'buy credits', 'names': ['buy credits'], 'cx': 10, 'cy': 20}
        def click(self, *xy):
            self.clicks.append(xy)
    t = Tab()
    act, n, note = engine.do_llm_action(t, ('PRESS', 'credits'))
    assert note == 'irreversible_blocked' and n == 0 and not t.clicks
