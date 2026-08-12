// 파이썬(App.show_toast)이 호출하는 진입점: {id, project, subject, url}
function renderToast(data) {
    document.getElementById("line1").textContent = data.project + "  새 이슈";
    let subject = data.subject || "";
    if (subject.length > 20) subject = subject.slice(0, 19) + "…";
    document.getElementById("line2").textContent = subject;
    document.getElementById("toast").addEventListener("click", () => {
        window.pywebview.api.open_toast_url(data.id, data.url);
    });
}
