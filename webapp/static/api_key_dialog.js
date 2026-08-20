// 파이썬(App._push_api_key_dialog)이 호출하는 진입점: {title, desc, value} - 전사/팀
// 레드마인 중 어느 쪽 API 키를 설정하는지에 맞는 문구와 저장돼 있던 키를 채워준다.
function renderApiKeyDialog(data) {
    document.getElementById("title").textContent = data.title || "";
    document.getElementById("desc").innerHTML = data.desc || "";
    const input = document.getElementById("keyInput");
    input.type = "password";
    input.value = data.value || "";
    document.getElementById("btnToggle").textContent = "표시";
    input.focus();
    input.select();
}

function submit() {
    const value = document.getElementById("keyInput").value.trim();
    if (!value) return;
    window.pywebview.api.save_api_key(value);
}

document.getElementById("btnToggle").addEventListener("click", () => {
    const input = document.getElementById("keyInput");
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    document.getElementById("btnToggle").textContent = showing ? "표시" : "숨김";
    input.focus();
});
document.getElementById("btnSave").addEventListener("click", submit);
document.getElementById("btnCancel").addEventListener("click", () => {
    window.pywebview.api.close_api_key_dialog();
});
document.getElementById("keyInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
    if (e.key === "Escape") window.pywebview.api.close_api_key_dialog();
});
