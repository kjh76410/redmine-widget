document.getElementById("itemSetCompanyApiKey").addEventListener("click", () => {
    window.pywebview.api.close_context_menu();
    window.pywebview.api.open_api_key_dialog("company");
});
document.getElementById("itemSetTeamApiKey").addEventListener("click", () => {
    window.pywebview.api.close_context_menu();
    window.pywebview.api.open_api_key_dialog("team");
});
// 이 항목들은 메뉴를 닫지 않는다 - 켜고 끈 결과(체크 표시)를 바로 보여주려는 것.
document.getElementById("itemAutostart").addEventListener("click", () => {
    window.pywebview.api.toggle_autostart();
});
document.getElementById("itemAlwaysOnTop").addEventListener("click", () => {
    window.pywebview.api.toggle_always_on_top();
});

// (창 밖을 누르면 닫히게 blur 이벤트를 써 보려 했지만 안 된다 - 이 창들은 포커스를
// 아예 받지 않아서 document.hasFocus()가 늘 false이고 focus/blur가 한 번도 안 온다.
// 대신 파이썬 쪽에서 다른 화면을 열 때 닫는다 - main.py의 open_panel 참고.)

// 파이썬(App._push_context_menu)이 호출하는 진입점: {autostart}
function renderContextMenu(data) {
    document.getElementById("autostartCheck").textContent = data.autostart ? "✓" : "";
    document.getElementById("alwaysOnTopCheck").textContent = data.always_on_top ? "✓" : "";
}
