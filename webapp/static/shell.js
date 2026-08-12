const mainIcon = document.getElementById("mainIcon");
const toolbar = document.getElementById("toolbar");

let panelOpen = false;

function setPanelOpen(open) {
    panelOpen = open;
    toolbar.classList.toggle("open", open);
}

mainIcon.addEventListener("click", () => {
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

// 파이썬(백그라운드 폴링) → 여기로 "내 일감" 개수 갱신을 알려줄 때 호출
window.setMyIssuesCount = function (count) {
    const badge = document.getElementById("myIssuesBadge");
    if (count > 0) {
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.classList.add("show");
    } else {
        badge.classList.remove("show");
    }
};
