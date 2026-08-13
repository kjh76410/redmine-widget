// 파이썬(App.show_toast)이 호출하는 진입점: {id, project, subject, url}
function renderToast(data) {
    document.getElementById("line1Text").textContent = data.project + "  새 이슈";
    document.getElementById("line2").textContent = data.subject || "";
    document.getElementById("toast").addEventListener("click", () => {
        window.pywebview.api.open_toast_url(data.id, data.url);
    });
    document.getElementById("closeBtn").addEventListener("click", (event) => {
        event.stopPropagation();
        window.pywebview.api.close_toast(data.id);
    });
}
