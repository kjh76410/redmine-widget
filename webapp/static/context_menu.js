document.getElementById("itemRefreshRedmine").addEventListener("click", () => {
    window.pywebview.api.refresh_redmine();
    window.pywebview.api.close_context_menu();
});
document.getElementById("itemRefreshMyIssues").addEventListener("click", () => {
    window.pywebview.api.refresh_my_issues();
    window.pywebview.api.close_context_menu();
});
document.getElementById("itemSetUserId").addEventListener("click", () => {
    window.pywebview.api.close_context_menu();
    window.pywebview.api.open_user_id_dialog();
});
// 이 항목은 메뉴를 닫지 않는다 - 켜고 끈 결과(체크 표시)를 바로 보여주려는 것.
document.getElementById("itemAutostart").addEventListener("click", () => {
    window.pywebview.api.toggle_autostart();
});

// 파이썬(App._push_context_menu)이 호출하는 진입점: {autostart}
function renderContextMenu(data) {
    document.getElementById("autostartCheck").textContent = data.autostart ? "✓" : "";
}
