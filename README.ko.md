<p align="center"><a href="README.md">English</a> | <b>한국어</b> | <a href="README.ja.md">日本語</a></p>

<!-- source-sha256: 0506029bad0e1f64ea71749be6ffc0705a5deee1a2863130495f72af8eaba790 -->

<p align="center"><img src="assets/banner_v2.png" alt="SimThink D: 클라우드 판단을 대신하는 로컬 백업" width="100%"></p>

<p align="center">
  <a href="https://pypi.org/project/simthinkd/"><img src="https://img.shields.io/pypi/v/simthinkd" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License: Apache 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <a href="https://github.com/MSSJ-AI-ORG/simthinkd/actions/workflows/test.yml"><img src="https://github.com/MSSJ-AI-ORG/simthinkd/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://colab.research.google.com/github/MSSJ-AI-ORG/simthinkd/blob/main/notebooks/quickstart.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open in Colab"></a>
  <a href="https://arxiv.org/abs/2610.04810"><img src="https://img.shields.io/badge/arXiv-2610.04810-b31b1b.svg" alt="arXiv:2610.04810"></a>
</p>

<p align="center"><b>네트워크가 끊겨도 판단은 현장에서.</b></p>

<!-- source: README.md (English is the reference). Keep numbers and links identical; update this file when README.md changes. -->

SimThink D는 네트워크가 끊겼을 때 대신 판단하는 작은 CPU 모델입니다.
파라미터는 265,665개이고, CPU 코어 하나에서 판단 한 번에 약 2 ms가 걸립니다.

공장 시뮬레이션에서 인터넷을 15초 동안 끊었습니다.
로컬 백업은 부품 63개 중 59개를 맞게 판정했고, 늦은 판단은 하나도 없었습니다.

<p align="center"><a href="assets/factory_fallback.mp4"><img src="assets/factory_twin.gif" alt="공장 시뮬레이션: 인터넷을 15초 끊자 공장 PC의 SimThink D가 그 사이 판단을 맡습니다" width="100%"></a></p>

<p align="center"><a href="https://mssj-ai-org.github.io/simthinkd/">소개 페이지</a> · <a href="https://mssj-ai-org.github.io/simthinkd/#demo">브라우저에서 해 보기</a> · <a href="assets/factory_fallback.mp4">영상 보기(72초)</a> · <a href="examples/factory_twin/">공장 코드</a> · <a href="docs/PAPER.md">논문</a></p>

```bash
pip install simthinkd
```

네트워크가 끊기면 무엇이 다음 판단을 내리나요?

## 이 문서에서 쓰는 말

- **틱(tick)**: 게임이나 제어 루프의 한 단계. Doom은 초당 35틱으로 돌아가므로 한 틱은 28.6 ms입니다.
- **판단기(decider)**: 작은 모델. 상황을 적은 짧은 문장을 받아 행동 하나를 돌려줍니다.
- **교사(teacher)**: 사용자가 정한 규칙을 일반 함수로 구현한 것. 판단기는 교사를 따라 하며 배웁니다.
- **인지(perception)**: 게임의 원시 상태 데이터를 짧은 문장으로 바꾸는 여러분의 코드.

## 설치

```bash
pip install simthinkd
```

판단만 하려면 이것으로 충분합니다. NumPy만 있으면 됩니다. 판단기를 직접 학습시키려면 `train` 옵션으로 학습용 의존성을 함께 설치합니다(PyTorch가 함께 설치되며, CPU 버전이면 됩니다).

```bash
pip install "simthinkd[train]"
```

## 바로 써 보기

```python
from simthinkd import Decider

d = Decider("doom-defend")
print(d.decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"))
# TURN_LEFT (100%, 1.1 ms)
```

호출 한 번이 판단 한 번입니다. 짧은 문장이 들어가고, 행동 하나와 해당 행동의 확률, 판단에 걸린 시간을 반환합니다. 첫 호출은 모델을 불러오느라 느립니다. 그다음부터는 한 번에 약 1 ms입니다.

패키지에는 판단기 두 개가 들어 있습니다. `doom-defend`(가운데 서서 싸우기)와 `doom-corridor`(복도를 따라 싸우며 나아가기)입니다.

## 한 번에 여러 판단

한 번의 호출에 같은 상황에 대한 질문을 여러 개 실을 수 있고, 한 묶음에 여러 상황을 실을 수 있습니다. 하나씩 물었을 때와 같은 답이 나옵니다.

```python
from simthinkd import Decider

d = Decider("doom-defend")
states = ["seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25",
          "seen: Demon right a30 d5 | enemies 1 | sway right | gun ready | ammo25"]
answers = d.predict_batch([d.request(s) for s in states])   # many situations in one pass
print([a["operation"]["choice"] for a in answers])
# ['TURN_LEFT', 'TURN_RIGHT']
```

`simthinkd bench --batch` 로 내 컴퓨터에서 시간이 어디에 쓰이는지 볼 수 있습니다. 자세한 내용과 한계: [docs/PARALLEL.md](docs/PARALLEL.md).

## 몇 초 만에 직접 학습하기

새 작업에는 두 가지가 필요합니다. 인지 단계와 교사입니다. 아래 `toy` 모듈은 공장 컨베이어의 검사대를 흉내 낸 작은 예제입니다. 예제와 행동을 여러분의 것으로 바꿔 넣으면 됩니다.

```python
import simthinkd
from simthinkd import toy

d = simthinkd.fit(toy.examples(3000), toy.ACTIONS, goal=toy.GOAL, out="inspection")
print(d.decide("part: defect dent | severity severe | image clear | belt normal | rework queue long"))
# REJECT (100%, 1.2 ms)
```

테스트에 사용한 PC의 CPU에서 학습에 약 8초가 걸렸습니다. 새로 만든 판단기는 처음 보는 상태 500개 중 500개에서 교사와 같은 답을 냈습니다.

## 고르는 대신 점수 매기기

행동이 아니라 숫자가 필요할 때가 있습니다. 위험도, 우선순위, 예상 대기 시간 같은 것입니다. `fit_score`는 같은 작은 신경망이 숫자 하나를 돌려주도록 학습합니다. (상황 문장, 숫자) 짝을 넣으면 됩니다.

```python
import random
import simthinkd
from simthinkd import toy

SEVERITY = {"minor": 20, "moderate": 45, "severe": 75}

def risk(s):  # your own rule or records give the number
    value = 0 if s["defect"] == "none" else SEVERITY[s["severity"]]
    value += 10 if s["image"] == "blurry" else 0
    value += 8 if s["belt"] == "fast" else 0
    value += 5 if s["defect"] != "none" and s["queue"] == "long" else 0
    return float(min(100, value))

rng = random.Random(7)
examples = [(text, risk(state)) for state, text in (toy.observe(rng) for _ in range(3000))]
s = simthinkd.fit_score(examples, goal="Rate how risky this part is, 0 to 100.", out="risk", low=0, high=100, quiet=True)
print(s.score("part: defect dent | severity severe | image clear | belt fast | rework queue long"))
# 87.99 (0.22 ms)
```

전체 스크립트는 [examples/risk_score.py](examples/risk_score.py)에 있습니다. 테스트에 사용한 PC에서 이렇게 학습한 모델의 위험도 점수는 학습에 사용하지 않은 부품 400개에서 정답과 평균 0.13점(0~100 척도)의 차이를 보였습니다. 가능한 모든 부품 쌍에서 위험도 순서를 정확히 예측했습니다.

## 어디에 맞나

SimThink D는 아래 세 조건을 모두 충족하는 작업에 적합합니다.

1. **상황이 짧은 한 줄에 들어간다.** "seen: Demon left a30 d5 | enemies 1"처럼 항목 몇 개면 됩니다. 긴 글은 아닙니다.
2. **출력이 단순하다.** 최대 8개 행동 중 하나, 또는 숫자 하나.
3. **빠른 응답, 낮은 처리 비용 또는 오프라인 작동이 필요하다.** 게임 틱마다, 라인의 부품마다, 제어 단계마다, 또는 네트워크가 끊겼을 때.

| 쓰임 | 맞는 이유 | 여기서 해 보기 |
|---|---|---|
| 게임 캐릭터 | 틱마다 판단 한 번, 초당 35틱 | Doom 판단기 두 개, `simthinkd bench` |
| 공장 PC의 백업 판단기 | 클라우드 서비스가 늦거나 끊겼을 때 대신 판단 | [examples/factory_twin](examples/factory_twin/) |
| 위험도·우선순위 점수 | 항목마다 숫자 하나를 밀리초보다 훨씬 짧은 시간 안에 반환 | [examples/risk_score.py](examples/risk_score.py) |
| 이미 가진 규칙 | 예시로 규칙을 배운 뒤 약 2 ms에 실행 | [직접 학습하기](#몇-초-만에-직접-학습하기) |
| 이미 가진 규칙 | 예시로 규칙을 배운 뒤 약 2 ms에 실행 | [직접 학습하기](#몇-초-만에-직접-학습하기) |

### 큰 모델과 함께 쓰기

SimThink D는 대개 더 큰 시스템의 일부로 사용할 때 가장 효과적입니다. 두 가지 방식이 있습니다.

| 방식 | 동작 | 여기서 해 보기 |
|---|---|---|
| **1차 필터** | SimThink D가 모든 경우에 먼저 답합니다. 모델의 신뢰도가 사용자가 설정한 임계값보다 낮으면 그 경우만 큰 모델이나 사람에게 넘깁니다. 쉬운 경우는 싸고 빠르게 끝나고, 어려운 경우는 큰 모델이 처리합니다. | `python examples/factory_twin/run.py --arm CASCADE --tau 0.9` |
| **로컬 백업** | 큰 모델이나 클라우드 서비스가 먼저 답합니다. 답이 늦거나 네트워크가 끊기면, 로컬 컴퓨터의 SimThink D가 대신 답합니다. | 위의 공장 영상, [examples/factory_twin](examples/factory_twin/) |

게임 캐릭터(NPC)는 1차 필터에 딱 맞는 경우입니다. 순간순간의 움직임은 SimThink D가 틱마다 처리하고, 계획이나 대화처럼 드물고 느려도 되는 선택만 큰 모델에 묻습니다.

이런 일에는 맞지 않습니다.

- **긴 글 평가**: 에세이나 보고서 같은 것. 에세이 단락으로 해 본 우리 시험에서는 단순한 단어 수 모델이 더 나았습니다.
- **입력한 한 줄에 없는 정보가 필요한 판단**: 판단이 그 줄에 없는 이력 등 정보에 달려 있다면, 그 정보를 줄에 넣거나 다른 도구를 쓰세요.
- **자유 형식의 답변**: 목록에서 고르거나 숫자 하나를 돌려줄 뿐, 글을 쓰지는 않습니다.

## 빠른 처리와 큰 모델 사이에서 작업 나누기

0.4.0의 새 기능(라우터 키트)입니다. `Router`는 큰 모델 앞에서 SimThink D가 먼저 판단하도록 합니다. 판단기가 현재 상태를 식별하면 스킬 테이블이 그 상태에 해당하는 스크립트 행동을 알려 주고, 라우터는 그 행동을 실행하거나 처리를 넘깁니다.

```python
from simthinkd import Decider, Router, SkillTable, ScreenAdapter

skills = SkillTable({"LOGIN":   ("FILL_LOGIN", ["PROFILE"]),        # state: (action, expected next states)
                     "PROFILE": ("SUBMIT", ["ERROR", "DONE"]),
                     "ERROR":   ("CLOSE", ["PROFILE"]),
                     "DONE":    ("STOP", None, True)})               # final: the task ends here
router = Router(Decider("models/screen"), skills, tau=0.9, adapter=ScreenAdapter())
router.reset(expect=["LOGIN"])
route = router.route({"pixels": screenshot, "title": "Sign in", "prev": None})
if route.handoff:
    action = ask_large_model(screenshot)     # route.reason says why
else:
    action = route.action                    # about 2 ms
```

다음 세 가지 이유 중 하나에 해당하면 처리를 넘깁니다.

| 이유 | 조건 |
|---|---|
| `low_confidence` | 판단기의 신뢰도가 `tau`보다 낮음 |
| `unknown_state` | 해당 상태의 스킬이 테이블에 없음 |
| `no_progress` | 현재 상태가 직전의 빠른 처리 행동으로 예상한 다음 상태에 해당하지 않음 |

세 번째 검사가 가장 중요합니다. 작은 모델은 처음 보는 화면에서 확신을 갖고 틀릴 수 있습니다. 그 행동이 예상과 다른 결과로 이어지거나 아무 변화도 일으키지 않으면, 바로 다음 라우팅에서 처리를 넘깁니다. `SkillTable.from_transitions`는 교사의 실행 기록에서 예상되는 다음 상태를 배웁니다.

- `HandoffMonitor()`는 최근 10회의 라우팅을 살펴봅니다. 그중 절반에서 처리를 넘겼거나 진행이 없는 경우가 3회이면 작동합니다.
- `relearn(router, teacher, observations, base_examples)`는 그런 경우를 교사(큰 모델이나 사람)에게 묻습니다. 이어서 판단기를 다시 학습시키고, 실행 중인 라우터의 판단기를 교체한 뒤 로그에 한 줄을 추가합니다.
- 어댑터는 서로 다른 입력을 판단기가 읽는 문장으로 바꿉니다. `ScreenAdapter`는 스크린샷의 색상 격자·창 제목·이전 행동을, `PipelineAdapter`는 요청 항목과 게이트 판정을, `VectorAdapter`는 로봇 관측 벡터의 일부를 사용합니다. 판단기는 그대로이고 입력만 달라집니다.

[examples/router_screen](examples/router_screen/)은 네트워크 없이 작은 모의 화면 작업에서 이 과정을 모두 실행합니다. 변경할 수 없도록 고정한 사전등록 문서와 직접 실험할 때 쓸 템플릿도 포함되어 있습니다. 조건을 고정한 실행에서는 의도적으로 잘못된 행동 12개 중 12개를 다음 화면에서 잡아냈습니다. 화면 디자인을 바꾼 뒤에는 교사 라벨 101개와 3.7초의 학습으로, 처리를 넘기는 비율이 라우팅 58회 중 41회에서 96회 중 0회로 내려갔습니다. 자세한 내용: [docs/ROUTER.md](docs/ROUTER.md).

## 화면 조작하기

0.5.0에 새로 추가된 화면 도구 모음(screen kit)입니다. 잘못 클릭하면 시간이 들거나 되돌릴 수 없는 실제 화면에서 라우터를 사용할 때 필요한 보호 기능을 제공합니다.

```python
from simthinkd import NoClickBands, open_or_press, ExpectAfter, RuleFirst, PageTextCheck

bands = NoClickBands(top=96, bottom_from=700)            # fixed header and footer of the site
kind, where = open_or_press(element, allow=lambda href: "/item/" in href)
if kind == "open":
    browser.goto(where)                                    # a link: open it, do not wait for a click
elif bands.allows(where):
    browser.click(*where)
ok, state, ms = ExpectAfter(read_state, timeout=5.0).wait({"CART"})
if not ok:
    action = ask_large_model(screenshot)                   # the step went nowhere: hand over
```

- `NoClickBands`는 페이지를 가리는 고정 머리글과 바닥글을 클릭하지 않도록 합니다.
- `open_or_press`는 카드를 클릭한 뒤 새 탭을 기다리는 대신 링크 주소를 직접 엽니다.
- `ExpectAfter`는 행동 후 정해진 시간 안에 예상한 화면이 나타나는지 확인합니다.
- `RuleFirst`는 확실한 규칙이 있는 경우 규칙을 사용하고, 그렇지 않은 경우에만 판단기에 묻습니다.
- `PageTextCheck`는 스크린샷 대신 페이지의 텍스트로 성공 여부를 판단합니다.
- 이번 버전에 함께 포함된 `DomVerifier`와 `PopupGuard`는 확신을 갖고 빠른 행동을 실행하기 전에 페이지 구조를 확인하며, 결정을 요구하는 팝업은 닫지 않습니다.

자체 모의 HR ERP에서 큰 모델만 사용했을 때는 임무당 평균 118.3초가 걸렸고 큰 모델을 매번 14회 호출했습니다. 앞에 SimThink D를 두었을 때는 7.2초가 걸렸고 호출은 0회였습니다(각각 3회 중 3회 성공, 로컬 헤드리스 Chrome). 모의 이미지 스튜디오에서는 큰 모델만 사용했을 때 126.6초가 걸렸고 매번 14회 호출했습니다. 앞에 SimThink D를 두었을 때는 18.7초가 걸렸고 호출은 1회였습니다. 그 1회는 결정이 필요한 크레딧 팝업으로, 항상 큰 모델에 넘깁니다(각각 3회 중 3회 성공, 검토 반영 뒤). 그 전에 조건을 고정해 실행했을 때는 24.3초에 호출이 1회 또는 2회였습니다. 바뀌는 중간에 잡힌 화면이 함께 넘어간 경우가 있었기 때문입니다. 처음 조건을 고정해 실행했을 때는 이 임무 중 하나가 실패했습니다. 원인은 벤치마크 실행기에 있었으며 수정했습니다(CHANGELOG 참조).
`benchmarks/screen`으로 두 앱을 다시 실행할 수 있으며, 명령 하나로 큰 모델을 연결합니다. 사용 설명서:
[docs/SCREEN.md](docs/SCREEN.md).

## 내 모델의 판단 시간 측정하기

여러분의 모델은 한 틱 안에 판단을 마치나요? `simthinkd bench`는 패키지에 들어 있는 Doom 기록 상태 1,050개를 다시 돌리며, 요청을 하나씩 보내 판단마다 시간을 잽니다.

```bash
simthinkd bench
simthinkd bench --url http://127.0.0.1:8000/v1/systemone --name my-model --tick-hz 35
```

두 번째 줄은 [판단 요청](docs/PROTOCOL.md)을 받는 서버라면 무엇이든 잽니다.

## 같은 CPU, 같은 상태

<p align="center">
  <img src="assets/side_by_side.gif" alt="같은 Doom 게임, 같은 시드, 같은 CPU. 왼쪽: SimThink D는 틱마다 답한다. 오른쪽: 공개된 그대로 쓴 421M 파라미터 범용 판단 모델은 생각하는 동안 틱 대부분을 놓친다." width="100%" />
</p>

<p align="center"><sub>같은 게임, 같은 시드, 같은 6코어 CPU. 왼쪽: SimThink D, 판단 한 번에 1.9 ms, 420틱 중 1틱을 놓침. 오른쪽: Laya, 421M 파라미터 공개 판단 모델을 이 게임으로 학습하지 않고 공개된 그대로 사용. 판단 한 번에 약 360 ms가 걸리고 420틱 중 390틱을 놓칩니다. 어두운 장면은 판단기가 답하기 전에 게임이 다음으로 넘어간 순간입니다.</sub></p>

**먼저 읽어 주세요.** Laya는 범용 모델이고 이 게임으로 학습하지 않았습니다. 공개된 속도인 질문당 약 33 ms는 GPU 기준입니다. 우리에게는 CPU만 있었습니다. 그래서 이 표는 실시간 루프 안에서의 시간을 비교합니다. 전체 품질을 비교하는 것이 아닙니다.

워크스테이션 CPU 하나(6스레드)와 Doom 상태 1,050개를 썼고, 이어서 같은 시드로 실제 게임 10번을 돌렸습니다. "놓친 틱"은 판단기가 답하기 전에 지나가 버린 틱입니다.

| 판단기 | 파라미터 | 판단 시간 중앙값 | 한 틱(28.6 ms) 안에 끝난 판단 | 실제 게임에서 놓친 틱 |
|---|---|---|---|---|
| SimThink D | 265,665 | 1.8 ms | 100% | 0.1% |
| Laya, 공개된 그대로 | 약 421M | 365 ms | 0% | 84.2% |

SimThink D는 교사가 아는 것만 압니다. 추론하지 않고, 긴 글을 읽지 않으며, 학습 없이 새 행동을 다루지 못합니다. 이 비교를 직접 돌려 보려면 [benchmarks/](benchmarks/)를 보세요.

## 내 환경에서 쓰기

| 어디서 | 방법 |
|---|---|
| 어떤 언어, 어떤 엔진이든 | `simthinkd serve doom-defend --port 11890` 뒤 [판단 요청](docs/PROTOCOL.md)을 `/v1/systemone`으로 POST |
| Unity / C# | [docs/INTEGRATION_UNITY.md](docs/INTEGRATION_UNITY.md): 기다리는 동안에도 게임이 멈추지 않는 클라이언트 루프 |
| 브라우저 | [web/](web/): 같은 모델을 서버 없이 순수 JavaScript로 |
| Java / JVM 게임·엔진 | [java/](java/): 같은 모델을 순수 Java 8로 프로그램 안에서 실행. 가중치는 `tools/export_java_weights.py` 로 내보내고, 파이썬과 똑같이 고르는지 시험으로 확인 |
| 공장 라인(시뮬레이터) | [examples/factory_twin/](examples/factory_twin/): 부품마다 400 ms 이내에 판정을 내려야 하는 검사 컨베이어 |
| Gradio | [space/](space/): 로컬이나 Hugging Face Spaces에서 돌리는 작은 웹 데모 |
| MCP(Claude Desktop, Cursor 등) | `pip install "simthinkd[mcp]"` 뒤 `python -m simthinkd.integrations.mcp_server` |
| LangChain / LangGraph | `from simthinkd.integrations.langchain_tool import simthinkd_tool` |

## 동작 원리

- **입력**: 상황 문장, 목표, 각 행동의 설명을 해싱으로 생성한 특징으로 바꿉니다. 단어, 단어 쌍, 세 글자 조각입니다. 사전 학습된 언어 모델은 들어 있지 않습니다.
- **모델**: 작은 두 층짜리 신경망이 제시된 행동마다 점수를 매깁니다. 모든 행동을 한꺼번에 보고, 보정된 확률을 냅니다.
- **학습**: 무작위 가중치에서 시작해 교사의 선택을 보고 배웁니다. 가장 좋은 체크포인트는 학습에 쓰지 않은 자료로 고릅니다.
- **왜 중요한가**: 35 Hz 게임에서 판단에 28.6 ms보다 오래 걸리면 틱을 놓치게 됩니다. 우리 논문은 판단 시간의 비용과 판단 품질을 나눠서 봅니다([docs/PAPER.md](docs/PAPER.md)).

## 한계

- 판단 한 번에 행동은 최대 8개.
- 텍스트 입력만 지원합니다. 숫자는 "d5"나 "ammo25"처럼 짧은 단어나 구간으로 바꿔 넣으세요.
- 판단기는 교사를 따라 합니다. 판단 성능은 교사 규칙의 수준에 제한됩니다.
- 확률은 해당 판단기의 학습 대상 작업에 대해서만 보정되어 있습니다.
- 점수 모델은 숫자 하나만 돌려줍니다. 오차 범위는 반환하지 않습니다.

## 더 보기

- [논문 그림](docs/FIGURES.md)
- [재현할 수 있는 것](docs/REPRODUCE.md)
- [판단 요청 형식](docs/PROTOCOL.md)
- [링크드인의 공장 영상](https://www.linkedin.com/feed/update/urn:li:activity:7510142949981057024/)

## 인용

SimThink D를 쓰신다면 [CITATION.cff](CITATION.cff)로 인용해 주세요. GitHub에 "Cite this repository" 버튼이 나옵니다.

- 논문: Shin, Lee, Jeong and Kwon, "Separating Decision Time from Decision Quality in the Real-Time Gap of Distilled Deciders: Evidence from a Game and a Conveyor Simulator", [arXiv:2610.04810](https://arxiv.org/abs/2610.04810)

패키지에 든 판단기 두 개는 논문에서 평가한 바로 그 판단기입니다(SHA-256 동일). 이 저장소에서 다시 돌릴 수 있는 것과 아직 공개하지 않은 것은 [docs/REPRODUCE.md](docs/REPRODUCE.md)에 정리되어 있습니다.

## 기여

버그 보고와 작은 풀 리퀘스트를 환영합니다. [CONTRIBUTING.md](CONTRIBUTING.md)를 보세요.

## 출처

비교에는 Convai Innovations의 [Laya](https://github.com/NandhaKishorM/laya)(Apache 2.0)를 수정 없이 작은 어댑터를 통해 실행했습니다. Doom 장면은 [ViZDoom](https://github.com/Farama-Foundation/ViZDoom)에서 왔습니다. [NOTICE](NOTICE)를 보세요.

## 라이선스

Apache 2.0. [LICENSE](LICENSE)를 보세요.
