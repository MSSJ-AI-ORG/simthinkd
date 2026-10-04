<p align="center"><a href="README.md">English</a> | <b>한국어</b> | <a href="README.ja.md">日本語</a></p>

<!-- source-sha256: 4c3db07479e4f5b27969fe65c4fb775ee385a00c966258e58164d0d748da5c6f -->

<p align="center"><img src="assets/banner_v2.png" alt="SimThink D: 클라우드 판단을 대신하는 로컬 백업" width="100%"></p>

<p align="center">
  <a href="https://pypi.org/project/simthinkd/"><img src="https://img.shields.io/pypi/v/simthinkd" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License: Apache 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <a href="https://github.com/MSSJ-AI-ORG/simthinkd/actions/workflows/test.yml"><img src="https://github.com/MSSJ-AI-ORG/simthinkd/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://colab.research.google.com/github/MSSJ-AI-ORG/simthinkd/blob/main/notebooks/quickstart.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open in Colab"></a>
  <a href="https://doi.org/10.5281/zenodo.23111615"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.23111615.svg" alt="DOI"></a>
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

워크스테이션 CPU 하나(6스레드)와 Doom 상태 1,050개를 썼고, 이어서 같은 시드로 실제 게임 10판을 돌렸습니다. "놓친 틱"은 판단기가 답하기 전에 지나가 버린 틱입니다.

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

- 소프트웨어: [doi:10.5281/zenodo.23111615](https://doi.org/10.5281/zenodo.23111615)
- 논문(프리프린트): Shin, Lee, Jeong and Kwon, "Separating Decision Time from Decision Quality in the Real-Time Gap of Distilled Deciders: Evidence from a Game and a Conveyor Simulator", [doi:10.5281/zenodo.23111659](https://doi.org/10.5281/zenodo.23111659)

패키지에 든 판단기 두 개는 논문에서 평가한 바로 그 판단기입니다(SHA-256 동일). 이 저장소에서 다시 돌릴 수 있는 것과 아직 공개하지 않은 것은 [docs/REPRODUCE.md](docs/REPRODUCE.md)에 정리되어 있습니다.

## 기여

버그 보고와 작은 풀 리퀘스트를 환영합니다. [CONTRIBUTING.md](CONTRIBUTING.md)를 보세요.

## 출처

비교에는 Convai Innovations의 [Laya](https://github.com/NandhaKishorM/laya)(Apache 2.0)를 수정 없이 작은 어댑터를 통해 실행했습니다. Doom 장면은 [ViZDoom](https://github.com/Farama-Foundation/ViZDoom)에서 왔습니다. [NOTICE](NOTICE)를 보세요.

## 라이선스

Apache 2.0. [LICENSE](LICENSE)를 보세요.
