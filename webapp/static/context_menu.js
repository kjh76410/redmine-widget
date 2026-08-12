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
