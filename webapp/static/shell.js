const mainIcon = document.getElementById("mainIcon");

let panelOpen = false;

// 툴바 아이콘들은 늘 그려져 있고, 파이썬이 셸 창 너비를 늘렸다 줄이면서 그것들을
// 드러냈다 감춘다(main.py의 set_toolbar_open 설명 참고) - 그래서 여기선 알려주기만 하면 된다.
function setPanelOpen(open) {
    panelOpen = open;
    window.pywebview.api.set_toolbar_open(open);
}

// ── 메인 아이콘을 끌어서 위젯 옮기기 ──────────────
// 창이 커서를 따라 같이 움직이니 창 기준 좌표(clientX)로는 이동량을 잴 수 없다.
// 화면 기준 좌표(screenX)로 "누른 지점에서 얼마나 갔는지"만 본다.
const DRAG_THRESHOLD = 4;  // 이만큼도 안 움직였으면 드래그가 아니라 그냥 클릭

let dragStart = null;   // 누른 순간의 화면 좌표
let dragged = false;    // 이번 누름이 드래그로 번졌는지
let pendingDelta = null;

// pointermove는 초당 수십~수백 번 오는데 그때마다 창을 옮기면 버벅인다. 화면 갱신
// 주기에 한 번씩만 실제로 넘긴다.
function queueDrag(dx, dy) {
    const first = pendingDelta === null;
    pendingDelta = [dx, dy];
    if (first) requestAnimationFrame(flushDrag);
}

function flushDrag() {
    if (pendingDelta === null) return;
    const [dx, dy] = pendingDelta;
    pendingDelta = null;
    window.pywebview.api.drag_icon(dx, dy);
}

mainIcon.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;  // 우클릭은 메뉴 담당
    dragStart = { x: e.screenX, y: e.screenY };
    dragged = false;
    mainIcon.setPointerCapture(e.pointerId);  // 커서가 창 밖으로 나가도 계속 받는다
});

mainIcon.addEventListener("pointermove", (e) => {
    if (!dragStart) return;
    const dx = e.screenX - dragStart.x;
    const dy = e.screenY - dragStart.y;
    if (!dragged) {
        if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
        dragged = true;
        window.pywebview.api.begin_icon_drag();
    }
    // 파이썬은 물리 픽셀로 창을 옮긴다 - screenX/Y는 CSS 픽셀이라 배율을 곱해서 넘긴다.
    const dpr = window.devicePixelRatio;
    queueDrag(Math.round(dx * dpr), Math.round(dy * dpr));
});

function endDrag() {
    if (!dragStart) return;
    dragStart = null;
    if (dragged) {
        flushDrag();  // 마지막 위치가 아직 안 넘어갔을 수 있다
        window.pywebview.api.end_icon_drag();
    }
    // dragged는 여기서 되돌리지 않는다 - 바로 뒤에 click이 오는데, 그걸 보고
    // "방금 옮긴 것"인지 판단해야 한다. 다음 pointerdown에서 초기화된다.
}

mainIcon.addEventListener("pointerup", endDrag);
mainIcon.addEventListener("pointercancel", endDrag);

mainIcon.addEventListener("click", () => {
    if (dragged) return;  // 방금 끌어서 옮긴 것 - 툴바를 여닫지 않는다
    // 메인 아이콘을 누르면 열려 있던 건 다 닫는다 - 카드(트리/일감/버전별 연결된 일감),
    // 우클릭 메뉴, 아이디 설정 창까지.
    window.pywebview.api.close_panel();
    window.pywebview.api.close_context_menu();
    window.pywebview.api.close_user_id_dialog();
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

// 파이썬(App._push_shell_labels)이 프로젝트 트리 버튼 두 개의 툴팁을 넣어줄 때 호출.
// {company, team} - 트리 창 제목과 같은 문구라 파이썬 SECTION_LABEL 한 곳에서 온다.
window.setToolbarLabels = function (labels) {
    document.querySelector('[data-panel="company_tree"]').title = labels.company;
    document.querySelector('[data-panel="team_tree"]').title = labels.team;
};

// 파이썬(백그라운드 폴링) → 여기로 "할당된 일감" 개수 갱신을 알려줄 때 호출
window.setMyIssuesCount = function (count) {
    const badge = document.getElementById("myIssuesBadge");
    if (count > 0) {
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.classList.add("show");
    } else {
        badge.classList.remove("show");
    }
};
