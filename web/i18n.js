/*
 * Page languages: English (the reference, written in index.html), Korean and Japanese.
 * Every element with data-i18n="key" is translated from the tables below. The language comes from, in order:
 * ?lang=xx in the address, the visitor's earlier choice, the browser language (ko / ja), otherwise English.
 * Keep numbers and links the same as the English text; tools/check_translations.py checks this.
 */
(function () {
  var T = {
    "ko": {
      "_title": "SimThink D: 실시간을 따라가는 작은 판단 모델",
      "_desc": "SimThink D는 상황을 적은 짧은 문장 하나를 읽고, CPU 코어 하나에서 약 2 ms에 행동을 고릅니다. 오픈소스, Apache 2.0.",
      "_copy": "복사", "_copied": "복사됨", "_copyfail": "선택해서 복사하세요",
      "nav.demo": "데모", "nav.fit": "어디에 맞나", "nav.factory": "공장", "nav.paper": "논문",
      "hero.pill": "v0.2.1 · 오픈소스, Apache 2.0",
      "hero.h1": "실시간을 따라가는 <em>작은</em> 판단 모델.",
      "hero.sub": "상황을 적은 짧은 문장 하나를 읽고, CPU 코어 하나에서 약 2&nbsp;ms에 행동을 고릅니다. <strong>GPU는 필요 없습니다. 학습할 때도요.</strong>",
      "hero.try": "브라우저에서 해 보기",
      "hero.next": "이어서 빠른 시작 따라 하기 →",
      "timing.kicker": "마감 안에 들어갑니다",
      "timing.h2": "세상이 넘어가기 전에 판단합니다.",
      "timing.lead": "게임도 기계도 기다려 주지 않습니다. 막대 하나가 주어진 시간이고, 주황색 부분이 SimThink D가 쓴 시간입니다.",
      "timing.row1": "<b>Doom</b>, 초당 35틱에서 한 틱",
      "timing.row1v": "28.6 ms 중 1.9 ms",
      "timing.row2": "<b>검사 컨베이어</b>, 부품이 분류기에 닿기 전",
      "timing.row2v": "400 ms 중 20 ms",
      "timing.legendA": "SimThink D 판단 시간(중앙값)",
      "timing.legendB": "주어진 시간",
      "timing.note": "테스트에 사용한 PC에서 잰 중앙값입니다. 컨베이어 실행에서는 판단기를 HTTP로 부릅니다. 여러분의 숫자는 다를 테니 직접 재 보세요: <code>simthinkd bench</code> · <a href=\"https://github.com/MSSJ-AI-ORG/simthinkd/blob/main/docs/REPRODUCE.md\">재현 방법</a>",
      "factory.kicker": "시뮬레이션 검사 라인에서",
      "factory.h2": "인터넷이 끊겨도 라인은 계속 돌았습니다.",
      "factory.lead": "클라우드 서비스가 먼저 판단합니다. 0.33초 안에 답이 오지 않으면 공장 PC의 SimThink D가 판단합니다. 그리고 네트워크를 15초 동안 끊었습니다.",
      "factory.s1": "끊긴 동안 맞게 판정한 부품",
      "factory.s2": "전체 실행에서 맞게 처리한 부품",
      "factory.s3": "늦은 판단",
      "factory.note": "시뮬레이션 라인이고, 판단기가 이 라인의 규칙을 배웠으므로 홈그라운드 이점이 있습니다. 시뮬레이터는 <a href=\"https://github.com/MSSJ-AI-ORG/simthinkd/tree/main/examples/factory_twin\">examples/factory_twin</a>에 있습니다.",
      "demo.kicker": "라이브 데모",
      "demo.h2": "여기서 바로 해 보세요.",
      "demo.lead": "논문의 Doom 판단기 두 개가 이 페이지에서 순수 JavaScript로 돌아갑니다. 상황을 바꾸고 Decide를 누르세요(데모 화면은 영어입니다).",
      "features.kicker": "얻는 것",
      "features.h2": "작고, 빠르고, 직접 가지고 쓰기 쉽습니다.",
      "features.c1h": "CPU 코어 하나", "features.c1p": "파라미터 265,665개로 판단 한 번에 약 2 ms. GPU도 네트워크도 필요 없습니다.",
      "features.c2h": "몇 초 만에 학습", "features.c2p": "규칙을 일반 함수로 구현하면 됩니다. README의 예제 작업은 CPU에서 약 8초에 학습됩니다.",
      "features.c3h": "NumPy만", "features.c3p": "판단에는 NumPy만 있으면 됩니다. 학습에는 PyTorch가 더해지며, CPU 버전이면 됩니다.",
      "features.c4h": "기존 환경에 바로 연결", "features.c4p": "HTTP 서버, MCP 서버, LangChain 도구가 패키지에 들어 있습니다.",
      "features.c5h": "내 모델 재 보기", "features.c5p": "<code>simthinkd bench</code>는 Doom 기록 상태 1,050개를 다시 돌려, 판단기가 한 틱 안에 판단을 마치는지 알려 줍니다.",
      "features.c6h": "확인할 수 있음", "features.c6p": "패키지에 든 판단기 두 개는 논문에서 평가한 바로 그것입니다. SHA-256 해시가 공개되어 있어 직접 확인할 수 있습니다.",
      "fit.kicker": "어디에 맞나",
      "fit.h2": "큰 시스템의 한 부분일 때 가장 좋습니다.",
      "fit.lead": "상황이 짧은 한 줄에 들어가고, 답이 작고(최대 8개 행동 중 하나, 또는 숫자 하나), 답이 빠르거나 싸거나 오프라인이어야 할 때 쓰세요.",
      "fit.c1h": "1차 필터", "fit.c1p": "SimThink D가 모든 경우에 먼저 답합니다. 모델의 신뢰도가 낮은 경우만 큰 모델이나 사람에게 넘어갑니다.",
      "fit.c2h": "로컬 백업", "fit.c2p": "클라우드 모델이 먼저 답합니다. 늦거나 네트워크가 끊기면 로컬 컴퓨터의 SimThink D가 대신 답합니다.",
      "fit.c3h": "게임 캐릭터", "fit.c3p": "틱마다의 순간 움직임은 SimThink D가, 드문 계획이나 대화는 큰 모델이 맡습니다.",
      "fit.c4h": "위험도·우선순위 점수", "fit.c4p": "<code>fit_score</code>는 항목마다 숫자 하나를 밀리초보다 훨씬 짧은 시간 안에 반환합니다. <code>examples/risk_score.py</code>를 보세요.",
      "fit.c5h": "이미 가진 규칙", "fit.c5p": "예시로 규칙을 배운 뒤 약 2 ms에 실행합니다.",
      "fit.c6h": "맞지 않는 일", "fit.c6p": "긴 글 평가, 입력 줄에 없는 정보가 필요한 판단, 자유 형식의 답변.",
      "code.kicker": "빠른 시작",
      "code.h2": "호출 한 번이 판단 한 번입니다.",
      "code.colab": "Colab에서 열기", "code.readme": "README 읽기",
      "paper.kicker": "논문",
      "paper.h2": "판단 시간과 판단 품질을 나눠서 쟀습니다.",
      "paper.doi1": "논문 프리프린트(DOI)", "paper.doi2": "소프트웨어(DOI)", "paper.repro": "재현할 수 있는 것",
      "footer.disc": "질문과 아이디어: GitHub Discussions"
    },
    "ja": {
      "_title": "SimThink D: リアルタイムに追いつく小さな判断モデル",
      "_desc": "SimThink D は状況を表す短い文を 1 つ読み、CPU コア 1 つで約 2 ms で行動を選びます。オープンソース、Apache 2.0。",
      "_copy": "コピー", "_copied": "コピーしました", "_copyfail": "選択してコピーしてください",
      "nav.demo": "デモ", "nav.fit": "向いている場面", "nav.factory": "工場", "nav.paper": "論文",
      "hero.pill": "v0.2.1 · オープンソース、Apache 2.0",
      "hero.h1": "リアルタイムに追いつく<em>小さな</em>判断モデル。",
      "hero.sub": "状況を表す短い文を 1 つ読み、CPU コア 1&nbsp;つで約 2&nbsp;ms で行動を選びます。<strong>GPU は不要です。学習のときも。</strong>",
      "hero.try": "ブラウザで試す",
      "hero.next": "続けてクイックスタートへ →",
      "timing.kicker": "締め切りに収まる",
      "timing.h2": "世界が先へ進む前に判断する。",
      "timing.lead": "ゲームも機械も待ってくれません。各バーが使える時間で、オレンジの部分が SimThink D の使った時間です。",
      "timing.row1": "<b>Doom</b>、毎秒 35 ティックでの 1 ティック",
      "timing.row1v": "28.6 ms のうち 1.9 ms",
      "timing.row2": "<b>検査コンベヤー</b>、部品が振り分け装置に届く前",
      "timing.row2v": "400 ms のうち 20 ms",
      "timing.legendA": "SimThink D の判断時間（中央値）",
      "timing.legendB": "使える時間",
      "timing.note": "比較に利用できたのは CPU 環境のみでした。コンベヤーの実行では判断器を HTTP で呼び出しています。数値は環境によって変わるので、ご自身で測ってください: <code>simthinkd bench</code> · <a href=\"https://github.com/MSSJ-AI-ORG/simthinkd/blob/main/docs/REPRODUCE.md\">再現方法</a>",
      "factory.kicker": "シミュレーションの検査ラインで",
      "factory.h2": "インターネットが切れても、ラインは止まらなかった。",
      "factory.lead": "まずクラウドサービスが判断します。0.33 秒以内に答えが返らなければ、工場 PC の SimThink D が判断します。そのうえでネットワークを 15 秒間切断しました。",
      "factory.s1": "切断中に正しく判定した部品",
      "factory.s2": "実行全体で正しく処理した部品",
      "factory.s3": "遅れた判断",
      "factory.note": "シミュレーションのラインであり、判断器はこのライン自身のルールを学んでいるので、ホームの利があります。シミュレーターは <a href=\"https://github.com/MSSJ-AI-ORG/simthinkd/tree/main/examples/factory_twin\">examples/factory_twin</a> にあります。",
      "demo.kicker": "ライブデモ",
      "demo.h2": "ここで試せます。",
      "demo.lead": "論文の Doom 判断器 2 つが、このページの中で素の JavaScript で動きます。状況を変えて Decide を押してください（デモ画面は英語です）。",
      "features.kicker": "できること",
      "features.h2": "小さく、速く、手元で扱いやすい。",
      "features.c1h": "CPU コア 1 つ", "features.c1p": "パラメータ 265,665 個で、1 回の判断に約 2 ms。GPU もネットワークも要りません。",
      "features.c2h": "数秒で学習", "features.c2p": "ルールを通常の関数として実装するだけです。README の例題は CPU で約 8 秒で学習できます。",
      "features.c3h": "NumPy だけ", "features.c3p": "判断に必要なのは NumPy だけです。学習には PyTorch が加わり、CPU 版で構いません。",
      "features.c4h": "既存の環境につながる", "features.c4p": "HTTP サーバー、MCP サーバー、LangChain のツールがパッケージに含まれています。",
      "features.c5h": "自分のモデルを測る", "features.c5p": "<code>simthinkd bench</code> は記録済みの Doom の状態 1,050 個を順に入力し、判断器が 1 ティック以内に答えるかを教えてくれます。",
      "features.c6h": "確かめられる", "features.c6p": "同梱の判断器 2 つは、論文で評価したものそのものです。SHA-256 ハッシュを公開しているので確かめられます。",
      "fit.kicker": "向いている場面",
      "fit.h2": "大規模なシステムの一部として組み込むほうが一番。",
      "fit.lead": "状況が短い 1 行に収まり、答えが小さく（最大 8 個の行動から 1 つ、または数値 1 つ）、速く、安く、またはオフラインで答える必要があるときに使ってください。",
      "fit.c1h": "一次フィルター", "fit.c1p": "SimThink D がすべてのケースに先に答えます。信頼度の低いケースだけを大規模モデルや人に回します。",
      "fit.c2h": "ローカルのバックアップ", "fit.c2p": "クラウドのモデルが先に答えます。遅れたりネットワークが落ちたりしたら、手元のマシンの SimThink D が代わりに答えます。",
      "fit.c3h": "ゲームのキャラクター", "fit.c3p": "ティックごとのその場の動きは SimThink D、まれな計画や会話は大規模モデルが担当します。",
      "fit.c4h": "リスク・優先度のスコア", "fit.c4p": "<code>fit_score</code> は項目ごとに数値を 1 つ、1 ミリ秒を大きく下回る時間で返します。<code>examples/risk_score.py</code> を見てください。",
      "fit.c5h": "すでにあるルール", "fit.c5p": "例からルールを学び、約 2 ms で実行します。",
      "fit.c6h": "向かない用途", "fit.c6p": "長い文章の評価、入力した 1 行だけでは決まらない答え、自由形式の出力。",
      "code.kicker": "クイックスタート",
      "code.h2": "1 回の呼び出しが 1 回の判断。",
      "code.colab": "Colab で開く", "code.readme": "README を読む",
      "paper.kicker": "論文",
      "paper.h2": "判断時間と判断の質を、分けて測る。",
      "paper.doi1": "論文プレプリント（DOI）", "paper.doi2": "ソフトウェア（DOI）", "paper.repro": "再現できるもの",
      "footer.disc": "質問やアイデア: GitHub Discussions"
    }
  };
  var EN = {};
  var els = document.querySelectorAll("[data-i18n]");
  for (var i = 0; i < els.length; i++) EN[els[i].getAttribute("data-i18n")] = els[i].innerHTML;
  EN._title = document.title;
  var md = document.querySelector('meta[name="description"]');
  EN._desc = md ? md.getAttribute("content") : "";
  EN._copy = "Copy"; EN._copied = "Copied"; EN._copyfail = "Select and copy";

  function pick() {
    var q = (location.search.match(/[?&]lang=(en|ko|ja)\b/) || [])[1];
    if (q) return q;
    try { var s = localStorage.getItem("simthinkd-lang"); if (s === "en" || s === "ko" || s === "ja") return s; } catch (e) { /* no storage */ }
    var n = (navigator.languages && navigator.languages[0]) || navigator.language || "en";
    n = n.toLowerCase();
    if (n.indexOf("ko") === 0) return "ko";
    if (n.indexOf("ja") === 0) return "ja";
    return "en";
  }

  window.simthinkdText = function (key) {
    var lang = document.documentElement.getAttribute("lang") || "en";
    return (T[lang] && T[lang][key]) || EN[key];
  };

  function apply(lang) {
    var t = T[lang] || {};
    for (var i = 0; i < els.length; i++) {
      var k = els[i].getAttribute("data-i18n");
      els[i].innerHTML = t[k] || EN[k];
    }
    document.title = t._title || EN._title;
    if (md) md.setAttribute("content", t._desc || EN._desc);
    document.documentElement.setAttribute("lang", lang);
    var cb = document.getElementById("copy");
    if (cb) cb.textContent = t._copy || EN._copy;
    var bs = document.querySelectorAll(".lang button");
    for (var j = 0; j < bs.length; j++) bs[j].setAttribute("aria-pressed", bs[j].getAttribute("data-lang") === lang ? "true" : "false");
  }

  var bs = document.querySelectorAll(".lang button");
  for (var j = 0; j < bs.length; j++) {
    bs[j].addEventListener("click", function () {
      var l = this.getAttribute("data-lang");
      try { localStorage.setItem("simthinkd-lang", l); } catch (e) { /* no storage */ }
      apply(l);
    });
  }
  apply(pick());
})();
