"""
pywebview로 새로 만드는 위젯 셸 - 메인 아이콘 + 퀵 툴바 + 전사/팀 레드마인 프로젝트
트리(즐겨찾기 추가·해제 포함) + 내 일감/즐겨찾기 프로젝트 2단 창(검색/유형 필터/
스크롤 더 불러오기 포함) + 버전별 해결 일감 3단 창 + 로그인 아이디 설정 창 + 새 이슈
토스트 알림까지 구현했다. 패널은 전부 self.panel 슬롯 하나를 재사용해서 위젯 아이콘
바로 위, 같은 자리에만 뜬다(따로 팝업 안 튐). config.py/redmine_api.py는 기존
Tkinter 버전과 그대로 공유한다(순수 데이터 계층이라 프레임워크에 안 묶여 있음).
"""

import base64
import ctypes
import functools
import json
import math
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import redmine_api

STATIC_DIR = Path(__file__).resolve().parent / "static"
ICONS_DIR = STATIC_DIR / "assets" / "icons"


def _dpi_scale():
    """이 화면의 실제 배율(100%->1.0, 110%->약 1.104 ...). pywebview(WinForms)는
    창을 만들거나 resize()/move()할 때마다 GetDpiForWindow() 배율을 내부적으로
    한 번 더 곱해서 물리 픽셀로 바꾸는데, 우리 프로세스는 SetProcessDPIAware만
    호출한 "시스템 DPI 인식" 상태라 애초에 좌표를 그대로 물리 픽셀로 받는다 -
    즉 이 곱셈이 불필요한데 적용돼서, 100%가 아닌 배율(예: 110%)에서는 창이
    요청한 자리보다 배율만큼 아래로 밀려 작업표시줄 밑에 깔리거나 크기가
    어긋난다. 우리가 넘기는 값을 미리 이 배율로 나눠서 상쇄시켜야 한다."""
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except (AttributeError, OSError):
        return 1.0


_DPI_SCALE = _dpi_scale()


def _apply_geometry(win, width=None, height=None, x=None, y=None, scale_size=True):
    """win.resize()/win.move()를 _DPI_SCALE로 나눠서 호출하는 공통 로직. pywebview가
    내부적으로 다시 그 배율을 곱해서 물리 픽셀로 바꾸기 때문에(_dpi_scale() 설명 참고),
    미리 나눠서 넘겨야 실제 화면 좌표/크기가 우리가 의도한 물리 픽셀 값과 정확히 맞는다.
    위치(x, y)는 화면/작업표시줄 기준 실제 물리 좌표에 맞춰야 하니 항상 나눈다.
    크기(width, height)는 scale_size=False로 끄면 안 나누고 그대로 넘기는데, 메인
    아이콘 창(shell)이 이렇게 쓴다 - CSS는 56px 같은 원본 픽셀 그대로 그려지는데
    물리 창 크기를 그보다 작게(DPI 배율로 나눠서) 만들면 Chromium이 계산하는
    뷰포트가 CSS보다 작아져서 아이콘 아래쪽이 잘려 보인다(반대로 CSS 쪽 px 값을
    줄이거나 zoom을 걸어 맞추면 이번엔 투명 창에서 칠해진 내용이 없는 부분이
    회색으로 보이는 별개의 버그가 있어서 그 방법은 못 쓴다). 안 나누고 그대로
    넘기면 pywebview가 내부적으로 곱하는 배율만큼 창이 커져서(예: 56 -> 62)
    Chromium 뷰포트가 정확히 CSS 크기(56)와 맞아떨어진다 - 대신 화면에 보이는
    실제 크기가 물리 픽셀 기준으로 배율만큼(예: 10%) 커지는데, 그 몫은 위치
    계산(App.__init__의 icon_y 등)에서 미리 반영해서 작업표시줄과 안 겹치게
    한다. 패널/토스트/메뉴 같은 나머지 창들은 내용이 %/flex로 꽉 차게 그려져서
    이 문제가 없으니 그대로 scale_size=True(기본값)로 나눠서 물리 크기를 정확히
    맞춘다."""
    if width is not None and height is not None:
        if scale_size:
            win.resize(round(width / _DPI_SCALE), round(height / _DPI_SCALE))
        else:
            win.resize(width, height)
    if x is not None and y is not None:
        win.move(round(x / _DPI_SCALE), round(y / _DPI_SCALE))


# 창별 배경색 - 각 CSS에서 창을 꽉 채우는 카드(#panel/#win/#toast, 셸은 버튼)의
# background와 같은 값이어야 한다. 아래 _set_window_shape 설명 참고: 창을 카드 모양대로
# 잘라내도 (1) 페이지가 그려지기 전 한순간과 (2) 둥근 모서리 안티에일리어싱 가장자리는
# 이 색이 깔리기 때문에, 카드 색과 같아야 티가 안 난다.
CARD_BG = {
    "shell.html": "#152340",
    "panel.html": "#152340",
    "issues_panel.html": "#ECEAF2",
    "resolved_panel.html": "#F3F1FA",
    "toast.html": "#233149",
    "context_menu.html": "#152340",
    "user_id_dialog.html": "#152340",
}

_RGN_OR = 2  # CombineRgn 모드


def _set_window_shape(win, rects, dpr):
    """창을 rects(실제로 그려지는 사각형들) 모양으로 도려내서, 그 바깥을 진짜 투명하게
    만든다. 이 프로젝트의 모든 창이 이 방식으로 투명 처리된다 - 셸은 버튼들 모양으로,
    나머지 창(패널/토스트/메뉴/다이얼로그)은 둥근 카드 하나 모양으로.

    아이콘 뒤/사이나 패널 둥근 모서리 바깥이 회색으로 보였던 이유: pywebview는
    transparent=True면 WebView2의 DefaultBackgroundColor만 투명으로 바꿔주고
    (edgechromium.py), 정작 그 WebView2를 담고 있는 WinForms Form의 BackColor는
    기본값(SystemColors.Control = 밝은 회색) 그대로 둔다. 그래서 웹 쪽이 투명한
    부분에서는 바탕화면이 아니라 Form의 회색이 비쳐 보인다(pywebview 6.2.1에는
    AllowTransparency/TransparencyKey를 세팅하는 코드가 아예 없다).

    Form에 TransparencyKey를 걸면 보이기는 제대로 뚫리는데, 그러면 창 전체가
    레이어드 윈도우가 되면서 클릭이 통째로 뒤(바탕화면)로 새어나가 아이콘을 눌러도
    아무 반응이 없다 - 실제로 WindowFromPoint가 아이콘 한가운데에서도 바탕화면
    SysListView32를 돌려주는 걸 확인했다. 그래서 그 방법은 쓸 수 없다.

    대신 SetWindowRgn으로 창의 "모양" 자체를 잘라낸다. 리전 밖은 아예 창이 없는 것과
    같아서 그리지도, 클릭을 먹지도 않는다(빈 곳을 누르면 그대로 뒤 창으로 넘어간다).
    리전 안쪽은 평범한 불투명 창이라 클릭이 정상 동작한다. 다만 리전 경계는 GDI라
    안티에일리어싱이 없어서, 둥근 모서리를 아주 확대해 보면 살짝 계단처럼 보인다.

    rects는 JS가 getBoundingClientRect()로 잰 CSS 픽셀 좌표 [left, top, right,
    bottom, 모서리반지름]이고, dpr(devicePixelRatio)을 곱해서 물리 픽셀로 바꾼다.
    CSS 값을 파이썬에 하드코딩하지 않으려고 JS에서 재서 넘겨받는다."""
    hwnd = _window_hwnd(win)
    if not hwnd:
        return

    combined = ctypes.windll.gdi32.CreateRectRgn(0, 0, 0, 0)
    for left, top, right, bottom, radius in rects:
        x0, y0 = math.floor(left * dpr), math.floor(top * dpr)
        x1, y1 = math.ceil(right * dpr), math.ceil(bottom * dpr)
        d = max(0, round(radius * dpr)) * 2  # CreateRoundRectRgn은 반지름이 아니라 지름을 받는다
        if d:
            piece = ctypes.windll.gdi32.CreateRoundRectRgn(x0, y0, x1, y1, d, d)
        else:
            piece = ctypes.windll.gdi32.CreateRectRgn(x0, y0, x1, y1)
        ctypes.windll.gdi32.CombineRgn(combined, combined, piece, _RGN_OR)
        ctypes.windll.gdi32.DeleteObject(piece)

    # SetWindowRgn이 성공하면 리전 소유권을 OS가 가져가므로 여기서 지우면 안 된다.
    if not ctypes.windll.user32.SetWindowRgn(hwnd, combined, True):
        ctypes.windll.gdi32.DeleteObject(combined)


def _window_hwnd(win):
    """pywebview 창의 진짜 Win32 핸들. 창이 아직 안 만들어졌으면 None."""
    from webview.platforms.winforms import BrowserView

    form = BrowserView.instances.get(win.uid)
    return int(form.Handle.ToInt64()) if form is not None else None


def _create_window(title, _scale_size=True, **kwargs):
    """webview.create_window()의 얇은 래퍼. frameless+transparent 창을 만들면 pywebview가
    Windows에서 창 생성 시점에 크기를 요청한 것과 전혀 다른 비율로(가로는 부풀고
    세로는 찌그러들어, 예: 56x56 요청 -> 115x18) 잡는 버그가 있다 - 이게 바로
    "아이콘이 잘려 보이는" 원인이었다(Tkinter는 이 문제가 없었음). loaded 이벤트에서
    요청했던 크기/위치로 다시 한 번 강제로 맞춘다(resize/move). _scale_size는
    _apply_geometry의 scale_size로 그대로 전달된다.
    (before_show 이벤트에서 고치면 더 일찍 고칠 수 있어 보이지만, 그 시점엔 아직
    WebView2 컨트롤 초기화가 안 끝나 있어서 resize/move 호출이 핸들을 깨뜨리고
    창 생성 자체가 실패하는 경우가 있었다 - loaded까지 기다려야 안전하다.)"""
    win = webview.create_window(title, **kwargs)
    width, height = kwargs.get("width"), kwargs.get("height")
    x, y = kwargs.get("x"), kwargs.get("y")

    # Api는 창마다 새로 만들어 넘기니, 어느 창에서 온 호출인지 알 수 있게 짝지어 둔다
    # (Api.set_window_shape이 이걸 쓴다). 창 객체는 지금 막 생겼으니 여기서만 붙일 수 있다.
    api = kwargs.get("js_api")
    if api is not None:
        api._window = win

    win.events.loaded += lambda: _apply_geometry(win, width, height, x, y, _scale_size)
    return win


@functools.lru_cache(maxsize=None)
def _icon_data_uri(filename):
    data = (ICONS_DIR / filename).read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


_ICON_REF_RE = re.compile(r"assets/icons/([\w.-]+\.png)")


@functools.lru_cache(maxsize=None)
def bundle_html(template_name):
    """<link rel="stylesheet">/<script src="...">로 분리된 정적 파일들을 전부 하나의
    인라인 HTML 문자열로 합친다. pywebview에서 url=(로컬 파일 서버 경유)로 창을 열면
    투명(transparent=True) 처리가 깨지는 문제가 있어서, html=(인라인 문자열)로 대신
    열기 위해 필요하다 - 그러려면 외부 리소스(css/js/아이콘 이미지)도 전부 문서 안에
    직접 들어있어야 한다."""
    html = (STATIC_DIR / template_name).read_text(encoding="utf-8")

    # (CSS zoom이나 px 값 축소로 DPI 배율을 보정해보려던 시도가 있었는데, 전부
    # 투명 창에서 "칠해진 내용이 없는" 부분(아이콘 사이 간격 등)이 회색으로
    # 보이는 부작용이 있어서 걷어냈다 - CSS는 그대로 원본 픽셀 값을 쓴다. 그
    # 대신 아주 살짝(몇 픽셀) 잘려 보일 수 있는데, 화면이 통째로 회색 박스로
    # 덮이는 것보다는 훨씬 낫다.)
    def inline_css(match):
        css_path = STATIC_DIR / match.group(1)
        return f"<style>{css_path.read_text(encoding='utf-8')}</style>"

    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">', inline_css, html)

    def inline_js(match):
        js_path = STATIC_DIR / match.group(1)
        return f"<script>{js_path.read_text(encoding='utf-8')}</script>"

    html = re.sub(r'<script src="([^"]+)"></script>', inline_js, html)

    # CSS의 url(...)이나 태그 style 속성에 남아있는 아이콘 경로를 data URI로 바꾼다.
    html = _ICON_REF_RE.sub(lambda m: _icon_data_uri(m.group(1)), html)

    return html

TREE_TITLES = {
    "company_tree": "전체 프로젝트",
    "team_tree": "팀 레드마인",
}
ISSUES_TITLES = {
    "my_issues": "내 일감",
    "favorites": "즐겨찾기 프로젝트",
}
RESOLVED_TITLE = "버전별 해결 일감"
SECTION_LABEL = {"company": "레드마인(150)", "team": "레드마인(20)"}
SECTION_ORDER = {"company": 0, "team": 1}

# kind -> (템플릿 파일, 창 너비, 창 높이)
PANEL_SPEC = {
    "company_tree": ("panel.html", 300, 640),
    "team_tree": ("panel.html", 300, 640),
    "my_issues": ("issues_panel.html", 800, 760),
    "favorites": ("issues_panel.html", 800, 760),
    "resolved_by_version": ("resolved_panel.html", 1000, 680),
}


class Api:
    """shell.html/panel.html/issues_panel.html의 JS에서 window.pywebview.api.* 로 호출하는
    파이썬 쪽 진입점."""

    def __init__(self, app):
        self._app = app
        # _create_window()가 만들어진 창을 여기에 짝지어 준다. 이름 앞의 _는 필수 -
        # pywebview는 js_api 객체의 "밑줄로 시작하지 않는" 속성을 전부 훑어서 JS에
        # 노출하는데(util.py get_functions), 밑줄이 없으면 Window 객체 내부 메서드까지
        # 통째로 페이지에 노출된다.
        self._window = None

    def set_window_shape(self, rects, dpr):
        """window_shape.js가 잰 카드 모양을 받아서 창을 그 모양으로 잘라낸다."""
        if self._window is not None:
            _set_window_shape(self._window, rects, dpr)

    def open_panel(self, kind):
        self._app.open_panel(kind)

    def open_url(self, url):
        webbrowser.open(url)

    def refresh_redmine(self):
        self._app.refresh_trees()

    def refresh_my_issues(self):
        self._app.refresh_my_issues()

    def open_user_id_dialog(self):
        self._app.open_user_id_dialog()

    def close_user_id_dialog(self):
        self._app.close_user_id_dialog()

    def save_user_id(self, value):
        self._app.save_user_id(value)

    def open_context_menu(self):
        self._app.open_context_menu()

    def close_context_menu(self):
        self._app.close_context_menu()

    def set_toolbar_open(self, open_):
        self._app.set_toolbar_open(open_)

    def set_shell_shape(self, state, rects, dpr):
        self._app.set_shell_shape(state, rects, dpr)

    def search_issues(self, kind, query):
        return self._app.search_issues(kind, query)

    def load_more_issues(self, project_id, source, offset):
        return self._app.load_more_issues(project_id, source, offset)

    def toggle_favorite(self, project_id, name, url, source):
        return self._app.toggle_favorite(project_id, name, url, source)

    def get_resolved_by_version(self, project_id):
        return self._app.get_resolved_by_version(project_id)

    def open_toast_url(self, toast_id, url):
        self._app.open_toast_url(toast_id, url)


class App:
    def __init__(self):
        # webview.screens[0]가 항상 주 모니터라는 보장이 없다(다중 모니터에서 보조
        # 모니터가 먼저 나올 수 있음) - 원점(0,0)에 있는 화면을 주 모니터로 본다.
        screen = next((s for s in webview.screens if s.x == 0 and s.y == 0), webview.screens[0])
        self.icon_size = config.ICON_SIZE  # shell 창은 _scale_size=False라 CSS 원본
        # 픽셀(56 등) 그대로 쓰지만, 실제 화면에 보이는 물리 크기는 DPI 배율만큼
        # 커진다(_apply_geometry 설명 참고) - 아래 icon_y처럼 "아이콘이 실제로
        # 차지하는 물리 픽셀 크기"가 필요한 계산은 icon_size가 아니라 이 값을 쓴다.
        self.icon_size_physical = round(self.icon_size * _DPI_SCALE)
        self.icon_x = config.MARGIN
        self.icon_y = screen.height - self.icon_size_physical - config.MARGIN - 40

        self.shell_w = (
            self.icon_size + config.QUICK_TOOLBAR_MARGIN
            + config.QUICK_TOOLBAR_TOTAL_W + 20
        )
        # 셸 창은 transparent=True를 안 쓴다 - 그건 WebView2만 투명하게 만들 뿐
        # 창(Form) 배경은 회색으로 남아서 오히려 아이콘 뒤가 회색 막대로 보인다
        # (_set_window_shape 설명 참고). 대신 창 배경을 버튼과 같은 남색으로 칠하고,
        # 실제 투명 처리는 SetWindowRgn(창 모양 잘라내기)으로 한다.
        self.shell = _create_window(
            "shell", html=bundle_html("shell.html"),
            width=self.icon_size, height=self.icon_size,
            x=self.icon_x, y=self.icon_y,
            frameless=True, on_top=True, resizable=False, shadow=False,
            background_color=CARD_BG["shell.html"],
            easy_drag=False,  # 기본값 True면 창 아무 데나 눌러서 드래그가 돼 스크롤/클릭과 충돌한다
            min_size=(1, 1),  # 기본 최소 크기(200x100)보다 작은 창이 강제로 커지는 것을 막는다
            js_api=Api(self),
            _scale_size=False,  # _apply_geometry 설명 참고 - CSS가 원본 px 그대로라 크기는 안 나눔
        )
        # JS가 재서 넘겨준 "닫힘/열림 상태의 버튼 사각형들"(_set_window_shape 참고)
        self.shell_shapes = {}
        self.shell_state = "closed"
        self.shell_dpr = _DPI_SCALE

        self.panel = None
        self.panel_kind = None
        self.company_tree = []
        self.team_tree = []

        self.redmine_user_id = redmine_api.load_redmine_user_id()
        self.my_issues = []
        self.favorites = redmine_api.load_favorites()
        self.favorite_issues = {}  # f"{source}:{id}" -> issues 리스트(처음엔 최근 200건)
        self.favorite_issue_totals = {}  # f"{source}:{id}" -> 전체 이슈 개수

        self.user_id_dialog = None
        self._pending_my_issues_open = False  # 아이디 설정 후 "내 일감"을 이어서 열지 여부
        self.context_menu = None

        self.seen_issue_ids = redmine_api.load_seen_issues()  # 즐겨찾기별로 이미 알린 이슈 id
        self.toasts = []  # [(toast_id, window), ...] - 아래에서 위로 쌓임
        self._toast_counter = 0

    # ── 메인 아이콘 옆 퀵 툴바 펼침/접힘 ───────────
    # 창을 툴바가 닫혔을 땐 아이콘 크기만큼만, 열렸을 땐 전체 너비로 실제로 resize
    # 한다. 창 모양(리전)도 같이 그 상태의 버튼들 모양으로 바꿔줘야 아이콘 사이/뒤가
    # 투명하게 유지된다(_set_window_shape 참고).
    def set_toolbar_open(self, open_):
        self.shell_state = "open" if open_ else "closed"
        width = self.shell_w if open_ else self.icon_size
        _apply_geometry(
            self.shell, width=width, height=self.icon_size,
            x=self.icon_x, y=self.icon_y, scale_size=False,
        )
        self._apply_shell_shape()

    def set_shell_shape(self, state, rects, dpr):
        """shell.js가 두 상태(closed/open)의 버튼 사각형을 재서 넘겨준다."""
        self.shell_shapes[state] = rects
        self.shell_dpr = dpr or _DPI_SCALE
        if state == self.shell_state:
            self._apply_shell_shape()

    def _apply_shell_shape(self):
        rects = self.shell_shapes.get(self.shell_state)
        if rects:
            _set_window_shape(self.shell, rects, self.shell_dpr)

    # ── 우클릭 메뉴 ──────────────────────────────
    def open_context_menu(self):
        if self.context_menu is not None:
            self.context_menu.destroy()
        w, h = 220, 108
        x = self.icon_x
        y = max(self.icon_y - 8 - h, 0)
        self.context_menu = _create_window(
            "context_menu", html=bundle_html("context_menu.html"),
            width=w, height=h, x=x, y=y,
            frameless=True, on_top=True, resizable=False, shadow=False,
            background_color=CARD_BG["context_menu.html"],
            easy_drag=False, min_size=(1, 1), js_api=Api(self),
        )

    def close_context_menu(self):
        if self.context_menu is not None:
            self.context_menu.destroy()
            self.context_menu = None

    # ── 백그라운드 조회 ──────────────────────────
    def refresh_trees(self):
        def worker_company():
            tree = redmine_api.build_project_tree(redmine_api.fetch_redmine_projects())
            self.company_tree = tree
            if self.panel_kind == "company_tree":
                self._push_tree()

        def worker_team():
            tree = redmine_api.build_project_tree(redmine_api.fetch_team_redmine_projects())
            self.team_tree = tree
            if self.panel_kind == "team_tree":
                self._push_tree()

        threading.Thread(target=worker_company, daemon=True).start()
        threading.Thread(target=worker_team, daemon=True).start()

    def refresh_my_issues(self):
        def worker():
            user_id = self.redmine_user_id or redmine_api.fetch_current_user_id()
            issues = redmine_api.fetch_my_issues(user_id) if user_id else []
            self.my_issues = issues
            if self.panel_kind == "my_issues":
                self._push_issues()
            self.shell.evaluate_js(f"setMyIssuesCount({len(issues)})")

        threading.Thread(target=worker, daemon=True).start()

    def refresh_favorite_issues(self):
        favorites_snapshot = list(self.favorites)
        if not favorites_snapshot:
            return

        def worker():
            for fav in favorites_snapshot:
                source = fav.get("source", "company")
                key = f"{source}:{fav['id']}"
                issues, total = redmine_api.fetch_project_issue_list(fav["id"], source)
                self.favorite_issues[key] = issues
                self.favorite_issue_totals[key] = total
            if self.panel_kind == "favorites":
                self._push_issues()

        threading.Thread(target=worker, daemon=True).start()

    # ── 새 이슈 알림 (즐겨찾기 프로젝트 대상, 1분 주기) ──
    def start_notify_loop(self):
        def loop():
            self._check_new_issues()  # 시작하자마자 한 번 확인, 그 뒤로 주기적으로
            while True:
                time.sleep(config.NOTIFY_POLL_INTERVAL_MS / 1000)
                self._check_new_issues()

        threading.Thread(target=loop, daemon=True).start()

    def _check_new_issues(self):
        favorites_snapshot = list(self.favorites)
        if not favorites_snapshot:
            return
        new_issues = []  # [(project_name, issue), ...]
        updated = {}
        for fav in favorites_snapshot:
            source = fav.get("source", "company")
            issues = redmine_api.fetch_recent_issues(fav["id"], source)
            if issues is None:
                continue  # 조회 실패 → 이번 회차는 건너뛰고 기존 기록 유지
            key = f"{source}:{fav['id']}"
            known = self.seen_issue_ids.get(key)
            if known is not None:
                known_ids = set(known)
                for issue in issues:
                    if issue["id"] not in known_ids:
                        new_issues.append((fav["name"], issue))
            # 처음 감시하는 프로젝트는 알림 없이 현재 이슈들만 "확인함"으로 기록
            updated[key] = [issue["id"] for issue in issues]
        self.seen_issue_ids.update(updated)
        redmine_api.save_seen_issues(self.seen_issue_ids)
        for project_name, issue in new_issues:
            self.show_toast(project_name, issue)

    def show_toast(self, project_name, issue):
        self._toast_counter += 1
        toast_id = self._toast_counter
        # 창을 만들자마자 move()로 옮기면 아직 초기화가 덜 끝나 자리를 못 잡는 경우가
        # 있어서(왼쪽 아래 대신 화면 맨 위 등에 뜸), 처음부터 최종 위치에 만든다.
        x = self.icon_x + self.icon_size_physical + 12
        idx = len(self.toasts)
        base_y = self.icon_y + self.icon_size_physical
        y = base_y - (idx + 1) * (config.TOAST_H + config.TOAST_GAP)
        toast = _create_window(
            f"toast-{toast_id}", html=bundle_html("toast.html"),
            width=config.TOAST_W, height=config.TOAST_H, x=x, y=y,
            frameless=True, on_top=True, resizable=False, shadow=False,
            background_color=CARD_BG["toast.html"],
            easy_drag=False, min_size=(1, 1), js_api=Api(self),
        )
        self.toasts.append((toast_id, toast))
        self._reflow_toasts()  # 그 사이 다른 토스트가 사라졌으면 자리를 다시 맞춘다

        def push():
            data = json.dumps({
                "id": toast_id, "project": project_name,
                "subject": issue["subject"], "url": issue["url"],
            }, ensure_ascii=False)
            toast.evaluate_js(f"renderToast({data})")

        toast.events.loaded += push

        def auto_dismiss():
            time.sleep(config.TOAST_DURATION_MS / 1000)
            self.dismiss_toast(toast_id)

        threading.Thread(target=auto_dismiss, daemon=True).start()

    def dismiss_toast(self, toast_id):
        for i, (tid, win) in enumerate(self.toasts):
            if tid == toast_id:
                self.toasts.pop(i)
                win.destroy()
                break
        self._reflow_toasts()

    def _reflow_toasts(self):
        # 메인 아이콘 오른쪽에, 아래에서 위로 쌓아 배치한다.
        x = self.icon_x + self.icon_size_physical + 12
        base_y = self.icon_y + self.icon_size_physical
        for idx, (_tid, win) in enumerate(self.toasts):
            y = base_y - (idx + 1) * (config.TOAST_H + config.TOAST_GAP)
            win.move(x, y)

    def open_toast_url(self, toast_id, url):
        webbrowser.open(url)
        self.dismiss_toast(toast_id)

    def search_issues(self, kind, query):
        query = (query or "").strip()
        if not query:
            return []
        if kind == "my_issues":
            words = [w.lower() for w in redmine_api.search_query_words(query)]
            return [
                {
                    "issue_id": issue["issue_id"], "url": issue["url"], "title": issue["title"],
                    "tracker": issue.get("tracker", ""), "priority": issue.get("priority", ""),
                }
                for issue in self.my_issues
                if all(w in issue["title"].lower() for w in words)
            ]
        if kind == "favorites":
            matches = []
            for f in self.favorites:
                source = f.get("source", "company")
                results = redmine_api.search_project_issues(f["id"], query, source)
                if not results:
                    continue
                key = f"{source}:{f['id']}"
                cached_by_id = {i["issue_id"]: i for i in self.favorite_issues.get(key, [])}
                for r in results:
                    cached = cached_by_id.get(r["issue_id"])
                    matches.append({
                        "issue_id": r["issue_id"], "url": r["url"],
                        "title": f"[{f['name']}] {r['title']}",
                        "tracker": cached.get("tracker", "") if cached else "",
                        "priority": cached.get("priority", "") if cached else "",
                    })
            return matches
        return []

    def load_more_issues(self, project_id, source, offset):
        more, total = redmine_api.fetch_project_issue_list(project_id, source, offset=offset)
        key = f"{source}:{project_id}"
        self.favorite_issues[key] = self.favorite_issues.get(key, []) + more
        self.favorite_issue_totals[key] = total
        return {"issues": more, "total": total}

    # ── 즐겨찾기 추가/해제 ────────────────────────
    def is_favorite(self, project_id, source):
        return any(
            f["id"] == project_id and f.get("source", "company") == source
            for f in self.favorites
        )

    def toggle_favorite(self, project_id, name, url, source):
        project_id = int(project_id)
        key = f"{source}:{project_id}"
        if self.is_favorite(project_id, source):
            self.favorites = [
                f for f in self.favorites
                if not (f["id"] == project_id and f.get("source", "company") == source)
            ]
            self.favorite_issues.pop(key, None)
            self.favorite_issue_totals.pop(key, None)
        else:
            self.favorites.append({"id": project_id, "name": name, "url": url, "source": source})
            self.refresh_favorite_issues()
        redmine_api.save_favorites(self.favorites)
        if self.panel_kind == "favorites":
            self._push_issues()
        return self.is_favorite(project_id, source)

    # ── "내 일감" 조회용 로그인 아이디 설정 ──────
    def open_user_id_dialog(self):
        if self.user_id_dialog is not None:
            self.user_id_dialog.destroy()
        w, h = 340, 210
        x = self.icon_x
        y = max(self.icon_y - 8 - h, 0)
        self.user_id_dialog = _create_window(
            "user_id_dialog", html=bundle_html("user_id_dialog.html"),
            width=w, height=h, x=x, y=y,
            frameless=True, on_top=True, resizable=False, shadow=False,
            background_color=CARD_BG["user_id_dialog.html"],
            easy_drag=False, min_size=(1, 1), js_api=Api(self),
        )
        self.user_id_dialog.events.loaded += self._push_user_id

    def _push_user_id(self):
        if self.user_id_dialog is None:
            return
        data = json.dumps({"value": self.redmine_user_id or ""}, ensure_ascii=False)
        self.user_id_dialog.evaluate_js(f"renderUserIdDialog({data})")

    def close_user_id_dialog(self):
        self._pending_my_issues_open = False
        if self.user_id_dialog is not None:
            self.user_id_dialog.destroy()
            self.user_id_dialog = None

    def save_user_id(self, value):
        value = (value or "").strip()
        if not value:
            return
        self.redmine_user_id = value
        redmine_api.save_redmine_user_id(value)
        if self.user_id_dialog is not None:
            self.user_id_dialog.destroy()
            self.user_id_dialog = None
        self.refresh_my_issues()
        if self._pending_my_issues_open:
            self._pending_my_issues_open = False
            self.open_panel("my_issues")

    # ── 패널 열기/닫기(토글) ──────────────────────
    # 모든 패널은 같은 self.panel 슬롯 하나를 재사용한다 - 팝업으로 따로 안 튀어나오고
    # 항상 위젯 아이콘 바로 위(같은 위치)에 뜨게 하기 위함이다.
    def open_panel(self, kind):
        if kind not in PANEL_SPEC:
            return
        if kind == "my_issues" and not self.redmine_user_id:
            self._pending_my_issues_open = True
            self.open_user_id_dialog()
            return

        if self.panel is not None:
            was_same = self.panel_kind == kind
            self.panel.destroy()
            self.panel = None
            self.panel_kind = None
            if was_same:
                return

        self.panel_kind = kind
        template, panel_w, panel_h = PANEL_SPEC[kind]
        x = self.icon_x
        y = max(self.icon_y - 8 - panel_h, 0)
        self.panel = _create_window(
            "panel", html=bundle_html(template),
            width=panel_w, height=panel_h, x=x, y=y,
            frameless=True, on_top=True, resizable=False, shadow=False,
            background_color=CARD_BG[template],
            easy_drag=False,  # 기본값 True면 목록 스크롤/클릭이 창 드래그로 먹힌다
            min_size=(1, 1), js_api=Api(self),
        )
        if kind in TREE_TITLES:
            self.panel.events.loaded += self._push_tree
        elif kind == "resolved_by_version":
            self.panel.events.loaded += self._push_resolved_tree
        else:
            self.panel.events.loaded += self._push_issues
            if kind == "my_issues" and not self.my_issues:
                self.refresh_my_issues()

    def _push_tree(self):
        if self.panel is None:
            return
        title = TREE_TITLES.get(self.panel_kind, "")
        tree = self.company_tree if self.panel_kind == "company_tree" else self.team_tree
        fav_keys = [f"{f.get('source', 'company')}:{f['id']}" for f in self.favorites]
        data = json.dumps(
            {"title": title, "tree": tree, "favorites": fav_keys}, ensure_ascii=False,
        )
        self.panel.evaluate_js(f"renderPanel({data})")

    def _push_resolved_tree(self):
        if self.panel is None:
            return
        # 원래 Tkinter 버전과 동일하게 전사 레드마인 프로젝트만 대상으로 한다.
        data = json.dumps({"title": RESOLVED_TITLE, "tree": self.company_tree}, ensure_ascii=False)
        self.panel.evaluate_js(f"renderResolvedPanel({data})")

    def get_resolved_by_version(self, project_id):
        return redmine_api.fetch_resolved_issues_by_version(project_id)

    def _push_issues(self):
        if self.panel is None:
            return
        title = ISSUES_TITLES.get(self.panel_kind, "")
        if self.panel_kind == "my_issues":
            groups = self._my_issues_groups()
        else:
            groups = self._favorite_groups()
        data = json.dumps(
            {"kind": self.panel_kind, "title": title, "groups": groups}, ensure_ascii=False,
        )
        self.panel.evaluate_js(f"renderIssuesPanel({data})")

    def _my_issues_groups(self):
        # "[프로젝트명] 제목" 형태인 제목에서 프로젝트명을 뽑아 프로젝트별로 묶는다.
        groups = {}
        order = []
        for issue in self.my_issues:
            m = re.match(r"^\[(.+?)\]\s*(.*)$", issue["title"])
            project_name, subject = (m.group(1), m.group(2)) if m else ("프로젝트 미상", issue["title"])
            if project_name not in groups:
                groups[project_name] = []
                order.append(project_name)
            groups[project_name].append({
                "issue_id": issue["issue_id"], "title": subject, "url": issue["url"],
                "tracker": issue.get("tracker", ""), "priority": issue.get("priority", ""),
            })
        return [
            {"project": p, "issues": groups[p]}
            for p in sorted(order)
        ]

    def _favorite_groups(self):
        def to_group(f):
            source = f.get("source", "company")
            key = f"{source}:{f['id']}"
            issues = self.favorite_issues.get(key, [])
            return {
                "project": f["name"],
                "issues": issues,
                "section": SECTION_LABEL.get(source, source),
                "_order": SECTION_ORDER.get(source, 99),
                "project_id": f["id"],
                "source": source,
                "total": self.favorite_issue_totals.get(key, len(issues)),
            }

        groups = sorted((to_group(f) for f in self.favorites), key=lambda g: (g["_order"], g["project"]))
        for g in groups:
            del g["_order"]
        return groups


def main():
    app = App()

    def startup():
        app.refresh_trees()
        app.refresh_my_issues()
        app.refresh_favorite_issues()
        app.start_notify_loop()

    webview.start(startup, debug=False)


if __name__ == "__main__":
    main()
