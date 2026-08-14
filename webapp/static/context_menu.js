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

// (창 밖을 누르면 닫히게 blur 이벤트를 써 보려 했지만 안 된다 - 이 창들은 포커스를
// 아예 받지 않아서 document.hasFocus()가 늘 false이고 focus/blur가 한 번도 안 온다.
// 대신 파이썬 쪽에서 다른 화면을 열 때 닫는다 - main.py의 open_panel 참고.)

// 파이썬(App._push_context_menu)이 호출하는 진입점: {autostart}
function renderContextMenu(data) {
    document.getElementById("autostartCheck").textContent = data.autostart ? "✓" : "";
}
