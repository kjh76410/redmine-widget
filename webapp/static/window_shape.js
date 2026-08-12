// 패널/토스트/메뉴/다이얼로그 창의 둥근 모서리 바깥이 회색으로 보이는 걸 막는다.
//
// 이 창들은 전부 "body의 첫 번째 요소 하나(카드)가 창을 100% 채우고, 거기에만
// border-radius가 걸린" 구조라, 그 카드 모양대로 창을 잘라내면 모서리 바깥의
// 회색이 사라진다. 실제로 잘라내는 건 파이썬 쪽 SetWindowRgn이고(main.py의
// _set_window_shape 설명 참고), 여기서는 카드의 위치와 모서리 반지름만 재서 넘긴다.
function pushWindowShape() {
    if (!window.pywebview) return;

    const card = document.body.firstElementChild;
    if (!card) return;

    const r = card.getBoundingClientRect();
    if (r.right <= r.left || r.bottom <= r.top) return;

    const radius = parseFloat(getComputedStyle(card).borderTopLeftRadius) || 0;
    window.pywebview.api.set_window_shape(
        [[r.left, r.top, r.right, r.bottom, radius]],
        window.devicePixelRatio,
    );
}

// 카드는 width/height가 100%라 창 크기가 바뀌면 같이 바뀐다. 특히 창이 만들어진
// 직후에 pywebview가 크기를 한 번 다시 잡는데(main.py의 _create_window 설명 참고),
// 그때 다시 재지 않으면 엉뚱한 크기로 잘려버린다.
window.addEventListener("resize", pushWindowShape);

// pywebviewready가 이 스크립트보다 먼저 떠버렸을 수도 있어서 양쪽 다 대비한다.
if (window.pywebview) {
    pushWindowShape();
} else {
    window.addEventListener("pywebviewready", pushWindowShape);
}
