// 파이썬(App.show_toast)이 호출하는 진입점: {id, heading, subject, url}
// heading은 파이썬이 완성해서 넘긴다 - 알림 종류가 둘(즐겨찾기 프로젝트의 새 이슈 /
// 나에게 할당된 일감)이라 여기서 문구를 조합하면 종류를 구분할 수 없다.
function renderToast(data) {
    document.getElementById("line1Text").textContent = data.heading;
    document.getElementById("line2").textContent = data.subject || "";
    document.getElementById("toast").addEventListener("click", () => {
        window.pywebview.api.open_toast_url(data.id, data.url);
    });
    document.getElementById("closeBtn").addEventListener("click", (event) => {
        event.stopPropagation();
        window.pywebview.api.close_toast(data.id);
    });
}
