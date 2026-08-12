// 파이썬(App._push_user_id)이 호출하는 진입점: {value} - 저장돼 있던 아이디를 채워준다.
function renderUserIdDialog(data) {
    const input = document.getElementById("idInput");
    input.value = data.value || "";
    input.focus();
    input.select();
}

function submit() {
    const value = document.getElementById("idInput").value.trim();
    if (!value) return;
    window.pywebview.api.save_user_id(value);
}

document.getElementById("btnSave").addEventListener("click", submit);
document.getElementById("btnCancel").addEventListener("click", () => {
    window.pywebview.api.close_user_id_dialog();
});
document.getElementById("idInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
    if (e.key === "Escape") window.pywebview.api.close_user_id_dialog();
});
