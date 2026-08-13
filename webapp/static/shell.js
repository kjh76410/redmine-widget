const mainIcon = document.getElementById("mainIcon");
const toolbar = document.getElementById("toolbar");

let panelOpen = false;
const TOOLBAR_TRANSITION_MS = 160; // shell.css의 #toolbar transition 시간과 맞춤

// ── 창 모양(리전) 알려주기 ────────────────────────────────
// 파이썬이 SetWindowRgn으로 창을 "버튼들 모양"으로 잘라내야 아이콘 뒤/사이가 진짜
// 투명해진다(main.py의 _set_window_shape 설명 참고). CSS 좌표를 파이썬에 두 벌로
// 적어두면 금방 어긋나니, 실제로 그려진 위치를 여기서 재서 넘긴다.
function measureRects(elements) {
    return elements
        .map((el) => {
            const r = el.getBoundingClientRect();
            const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
            return [r.left, r.top, r.right, r.bottom, radius];
        })
        .filter((r) => r[2] > r[0] && r[3] > r[1]);
}

function shapeOf(open) {
    // 툴바가 닫혀 있어도 .tool-btn의 getBoundingClientRect()는 (부모의 overflow:hidden과
    // 무관하게) 원래 크기를 그대로 돌려준다 - 그래서 "안 보이는 상태"를 크기로
    // 걸러낼 수 없고, 닫힘 모양에는 아예 메인 아이콘만 넣는다.
    const els = [mainIcon];
    if (open) {
        els.push(...document.querySelectorAll(".tool-btn"));
        els.push(...document.querySelectorAll(".badge.show"));
    }
    return measureRects(els);
}

function pushShapes() {
    if (!window.pywebview) return;

    // 열림 모양은 툴바를 잠깐 펼쳐 봐야 잴 수 있다. .no-anim으로 transition을 꺼두고
    // 재고 되돌려야, 이 측정 때문에 실제 펼침 애니메이션이 씹히지 않는다.
    const wasOpen = toolbar.classList.contains("open");
    toolbar.classList.add("no-anim");

    toolbar.classList.remove("open");
    void toolbar.offsetWidth;
    const closed = shapeOf(false);

    toolbar.classList.add("open");
    void toolbar.offsetWidth;
    const open = shapeOf(true);

    toolbar.classList.toggle("open", wasOpen);
    void toolbar.offsetWidth;
    toolbar.classList.remove("no-anim");

    const dpr = window.devicePixelRatio;
    window.pywebview.api.set_shell_shape("closed", closed, dpr);
    window.pywebview.api.set_shell_shape("open", open, dpr);
}

// pywebviewready가 이 스크립트보다 먼저 떠버렸을 수도 있어서 양쪽 다 대비한다
// (모양을 한 번도 안 보내면 창이 안 잘려서 아이콘 모서리가 각지게 보인다).
if (window.pywebview) {
    pushShapes();
} else {
    window.addEventListener("pywebviewready", pushShapes);
}

function setPanelOpen(open) {
    panelOpen = open;
    if (open) {
        // 펼치기 전에 먼저 창 자체를 넓혀야, 펼쳐지는 아이콘들이 아직 좁은 창
        // 폭에 잘리지 않는다.
        window.pywebview.api.set_toolbar_open(true);
        toolbar.classList.add("open");
    } else {
        toolbar.classList.remove("open");
        // 접히는 애니메이션이 끝난 뒤에 창을 좁혀야 중간에 잘려 보이지 않는다.
        setTimeout(() => window.pywebview.api.set_toolbar_open(false), TOOLBAR_TRANSITION_MS);
    }
}

mainIcon.addEventListener("click", () => {
    window.pywebview.api.close_panel();  // 열려있는 카드(트리/일감/버전별 연결된 일감)를 닫는다
    window.pywebview.api.close_context_menu();  // 열려있는 우클릭 메뉴도 같이 닫는다
    setPanelOpen(!panelOpen);
});

document.querySelectorAll(".tool-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        const kind = btn.dataset.panel;
        window.pywebview.api.open_panel(kind);
    });
});

mainIcon.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    window.pywebview.api.open_context_menu();
});

// 파이썬(백그라운드 폴링) → 여기로 "할당된 일감" 개수 갱신을 알려줄 때 호출
window.setMyIssuesCount = function (count) {
    const badge = document.getElementById("myIssuesBadge");
    const before = badge.classList.contains("show") ? badge.textContent : "";
    if (count > 0) {
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.classList.add("show");
    } else {
        badge.classList.remove("show");
    }
    const after = badge.classList.contains("show") ? badge.textContent : "";
    // 배지는 버튼 밖으로 삐져나오니 창 모양에도 반영해야 잘리지 않는다. 폴링이 같은
    // 개수를 계속 알려줄 때마다 다시 잴 필요는 없다 - 실제로 바뀐 경우에만 다시 잰다
    // (재는 동안 툴바를 잠깐 여닫기 때문에, 하필 펼침 애니메이션 중이면 그게 끊긴다).
    if (after !== before) pushShapes();
};
