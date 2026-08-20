"""
pywebview로 새로 만드는 위젯 셸 - 메인 아이콘 + 퀵 툴바 + 전사/팀 레드마인 프로젝트
트리(즐겨찾기 추가·해제 포함) + 할당된 일감/즐겨찾기 프로젝트 2단 창(검색/유형 필터/
스크롤 더 불러오기 포함) + 버전별 연결된 일감 3단 창 + 로그인 아이디 설정 창 + 새 이슈
토스트 알림까지 구현했다. 패널은 전부 self.panel 슬롯 하나를 재사용해서 위젯 아이콘
바로 위, 같은 자리에만 뜬다(따로 팝업 안 튐). config.py/redmine_api.py는 기존
Tkinter 버전과 그대로 공유한다(순수 데이터 계층이라 프레임워크에 안 묶여 있음).
"""

import base64
import ctypes
import functools
import json
import random
import re
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import korean_holidays
import redmine_api
import widget_state

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


# 창별 배경색 - 각 CSS에서 창을 꽉 채우는 카드(#panel/#win/#toast, 셸은 바)의
# background와 같은 값이어야 한다. 창은 불투명하고 모서리만 DWM이 깎기 때문에
# (_round_window_corners 참고) 카드가 안 덮은 자리와 둥근 모서리 가장자리에는 이 색이
# 깔린다 - 카드 색과 다르면 테두리처럼 삐져나와 보인다.
# 네이비(#152340)는 위젯 자체 - 바, 그 바에 붙어 뜨는 우클릭 메뉴와 설정창.
# 쿨 그레이(#F1F3F5)는 레드마인 데이터를 보여주는 창들 - 프로젝트 트리, 일감,
# 버전별, 진행상황, 토스트. 창이 무엇을 담는지에 따라 둘 중 하나를 쓴다.
CARD_BG = {
    "shell.html": "#152340",
    "context_menu.html": "#152340",
    "api_key_dialog.html": "#152340",
    "panel.html": "#F1F3F5",
    "issues_panel.html": "#F1F3F5",
    "resolved_panel.html": "#F1F3F5",
    "team_progress.html": "#F1F3F5",
    "calendar_panel.html": "#F1F3F5",
    "toast.html": "#F1F3F5",
}

# 툴바 펼침/접힘 애니메이션(App._animate_shell_width 참고). 창을 resize하는 방식이라
# 한 단계마다 WebView2가 다시 배치를 계산한다 - 단계를 너무 잘게 쪼개면 오히려 버벅인다.
_SHELL_ANIM_MS = 160
_SHELL_ANIM_STEPS = 10


_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2  # 윈도우 11 기본 창과 같은 반지름(이 화면 기준 약 8px)

_GCL_STYLE = -26  # WinUser.h GCL_STYLE
_CS_DROPSHADOW = 0x00020000


def _round_window_corners(win):
    """창 모서리를 DWM(윈도우 컴포지터)한테 둥글게 깎아달라고 맡긴다. 이 프로젝트의
    모든 창(셸/패널/토스트/메뉴/다이얼로그)이 이걸로 모서리를 만든다.

    창은 전부 불투명하다 - 웹 쪽을 투명하게 만들어서 둥근 모서리를 그리는 방법은
    두 번 시도했다가 다 막혔다. pywebview는 transparent=True면 WebView2의
    DefaultBackgroundColor만 투명으로 바꿔주고(edgechromium.py), 정작 그 WebView2를
    담고 있는 WinForms Form의 BackColor는 기본값(SystemColors.Control = 밝은 회색)
    그대로 둬서, 투명한 부분에 바탕화면이 아니라 회색이 비친다(pywebview 6.2.1에는
    AllowTransparency/TransparencyKey를 세팅하는 코드가 아예 없다). 그렇다고 Form에
    TransparencyKey를 걸면 보이기는 뚫리는데 창 전체가 레이어드 윈도우가 되면서
    클릭이 통째로 뒤(바탕화면)로 새어나간다 - WindowFromPoint가 아이콘 한가운데에서도
    바탕화면 SysListView32를 돌려주는 걸 확인했다.

    그래서 창 배경을 카드와 같은 색으로 칠해두고(CARD_BG), 모서리만 DWM한테
    맡긴다. 예전에는 SetWindowRgn으로 창 모양 자체를 카드 모양대로 도려냈는데,
    GDI 리전은 경계가 픽셀 단위 on/off라(안티에일리어싱이 없다) 둥근 모서리가
    눈에 띄게 계단처럼 깨졌다. DWM 라운딩은 컴포지터가 알파로 섞어 그려서 매끈하다.

    대신 DWM은 "창 사각형 하나"만 깎을 수 있다. 창을 버튼 여러 개 모양으로 뚫는
    건 리전으로만 되는 일이라, 셸을 아이콘 사이 간격 없는 이어진 바 하나로 만든
    게 이것 때문이다(shell.css 참고).

    반지름은 우리가 못 정하고 DWM이 정한다(둥글게/살짝 둥글게 둘 중 하나). 또
    윈도우 11(빌드 22000+)부터만 있는 속성이라, 그 이전 윈도우에서는 그냥
    실패값을 돌려주고 아무 일도 안 일어난다 - 모서리가 각져 보일 뿐 나머지
    동작에는 문제가 없다."""
    hwnd = _window_hwnd(win)
    if not hwnd:
        return

    pref = ctypes.c_int(_DWMWCP_ROUND)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(_DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )
    except (AttributeError, OSError):
        pass

    # 라운딩을 걸면 윈도우 11 DWM이 창마다 기본 그림자도 같이 입힌다 - 토스트처럼
    # 여러 창이 촘촘하게(TOAST_GAP) 쌓이면 그림자가 서로 겹쳐 아래로 갈수록 얼룩진
    # 것처럼 보였다. CSS box-shadow를 지워도 이건 OS가 그리는 것이라 안 없어져서,
    # 창 클래스 스타일의 CS_DROPSHADOW 비트를 직접 꺼서 막는다.
    try:
        get_style = ctypes.windll.user32.GetClassLongPtrW
        set_style = ctypes.windll.user32.SetClassLongPtrW
        get_style.restype = ctypes.c_ulonglong
        set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ulonglong]
        style = get_style(ctypes.c_void_p(hwnd), _GCL_STYLE)
        if style & _CS_DROPSHADOW:
            set_style(ctypes.c_void_p(hwnd), _GCL_STYLE, style & ~_CS_DROPSHADOW)
    except (AttributeError, OSError):
        pass


def _window_hwnd(win):
    """pywebview 창의 진짜 Win32 핸들. 창이 아직 안 만들어졌으면 None."""
    from webview.platforms.winforms import BrowserView

    form = BrowserView.instances.get(win.uid)
    return int(form.Handle.ToInt64()) if form is not None else None


def _create_window(title, _scale_size=True, _round_corners=False, **kwargs):
    """webview.create_window()의 얇은 래퍼. frameless+transparent 창을 만들면 pywebview가
    Windows에서 창 생성 시점에 크기를 요청한 것과 전혀 다른 비율로(가로는 부풀고
    세로는 찌그러들어, 예: 56x56 요청 -> 115x18) 잡는 버그가 있다 - 이게 바로
    "아이콘이 잘려 보이는" 원인이었다(Tkinter는 이 문제가 없었음). loaded 이벤트에서
    요청했던 크기/위치로 다시 한 번 강제로 맞춘다(resize/move). _scale_size는
    _apply_geometry의 scale_size로 그대로 전달된다.
    (before_show 이벤트에서 고치면 더 일찍 고칠 수 있어 보이지만, 그 시점엔 아직
    WebView2 컨트롤 초기화가 안 끝나 있어서 resize/move 호출이 핸들을 깨뜨리고
    창 생성 자체가 실패하는 경우가 있었다 - loaded까지 기다려야 안전하다.)

    hidden=True로 만들어서 그 틀린 크기 상태로는 아예 화면에 안 그리다가, loaded에서
    resize/move로 정확한 크기를 맞춘 다음에야 show()한다 - 안 그러면(원래 코드처럼
    보이는 채로 만들었다가 나중에 고치면) 사용자 눈에 창이 잘못된 크기로 반짝 나타났다가
    올바른 크기로 훽 줄어드는(또는 커지는) 게 그대로 보인다("할당된 일감"처럼 큰 패널일수록
    더 눈에 띈다). 호출부에서 hidden을 따로 넘기면 그 값을 존중한다.

    _round_corners=True면 보여주기 직전에 DWM 라운딩을 걸어둔다(_round_window_corners
    참고) - 창 핸들이 있어야 하니 창이 다 만들어지는 loaded까지 기다렸다 건다."""
    kwargs.setdefault("hidden", True)
    win = webview.create_window(title, **kwargs)
    width, height = kwargs.get("width"), kwargs.get("height")
    x, y = kwargs.get("x"), kwargs.get("y")

    def _reveal():
        _apply_geometry(win, width, height, x, y, _scale_size)
        if _round_corners:
            _round_window_corners(win)
        win.show()

    win.events.loaded += _reveal
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

# 어느 레드마인 서버에서 온 것인지를 가리키는 이름. 즐겨찾기/검색 목록의 구분자로도,
# 프로젝트 트리 창의 제목으로도 같은 문구를 쓴다(TREE_TITLES 참고) - 서버가 바뀌어
# 숫자를 고칠 때 두 군데를 따로 고치지 않도록 여기 한 곳에만 적는다.
SECTION_LABEL = {"company": "레드마인(150)", "team": "레드마인(20)"}
SECTION_ORDER = {"company": 0, "team": 1}

TREE_TITLES = {
    "company_tree": SECTION_LABEL["company"],
    "team_tree": SECTION_LABEL["team"],
}
ISSUES_TITLES = {
    "my_issues": "할당된 일감",
    "favorites": "즐겨찾기 프로젝트",
}

# 내 일감 알림(App._notify_new_my_issues)이 쓰는 값들. seen 키는 redmine_seen_issues.json에서
# 즐겨찾기 프로젝트 키("company:123" 같은 "source:id" 꼴)와 한 파일을 나눠 쓰므로 겹치면 안 된다.
MY_ISSUES_SEEN_KEY = "my_issues"
MY_ISSUES_TOAST_HEADING = "나에게 할당됨"

# 패널과 아이콘 사이 세로 간격(물리 px). 패널은 아이콘 바로 위에 붙어서 뜬다.
_PANEL_ICON_GAP = 8
# 화면이 좁아 패널을 줄여야 할 때의 하한(물리 px). 여기까지 줄면 아이콘을 덮게 되는데,
# 목록이 한 줄도 안 보이는 창을 여는 것보다는 낫다.
_PANEL_MIN_H = 240

# kind -> (템플릿 파일, 창 너비, 창 높이)
# 창 크기는 물리 픽셀이다(_create_window의 _scale_size 기본값 True - _apply_geometry 참고).
# 높이 850은 1920x1080에서 아이콘 위에 남는 자리를 거의 다 쓰는 값이라, 더 작은 화면에서
# 그대로 쓰면 위쪽이 잘린다 - App._panel_geometry가 들어가는 만큼으로 줄여서 연다.
PANEL_SPEC = {
    "company_tree": ("panel.html", 300, 850),
    "team_tree": ("panel.html", 300, 850),
    # 일감/즐겨찾기/연결된 일감/팀별 진행상황/배포 달력 다섯 창은 같은 크기로 맞춰 둔다
    # (툴바에서 서로 오갈 때 창이 안 흔들리게) - 팀별 진행상황의 Month 그리드 자리를
    # 넓히려고 다 1000 -> 1100으로 같이 늘렸고, 아이콘 위로 놀고 있던 자리를 쓰려고
    # 높이도 680 -> 850으로 같이 늘렸다(트리 두 창도 같은 높이로 맞춘다).
    "my_issues": ("issues_panel.html", 1100, 850),
    "favorites": ("issues_panel.html", 1100, 850),
    "resolved_by_version": ("resolved_panel.html", 1100, 850),
    "team_progress": ("team_progress.html", 1100, 850),
    "deploy_calendar": ("calendar_panel.html", 1100, 850),
}


class Api:
    """shell.html/panel.html/issues_panel.html의 JS에서 window.pywebview.api.* 로 호출하는
    파이썬 쪽 진입점."""

    def __init__(self, app):
        # 이름 앞의 _는 필수 - pywebview는 js_api 객체의 "밑줄로 시작하지 않는" 속성을
        # 전부 훑어서 JS에 노출하는데(util.py get_functions), 밑줄이 없으면 App 객체
        # 내부 메서드까지 통째로 페이지에 노출된다.
        self._app = app

    def open_panel(self, kind):
        self._app.open_panel(kind)

    def close_panel(self):
        self._app.close_panel()

    def open_url(self, url):
        webbrowser.open(url)

    def refresh_redmine(self):
        self._app.refresh_trees()

    def refresh_my_issues(self):
        self._app.refresh_my_issues()

    def refresh_favorites(self):
        self._app.refresh_favorite_issues()

    def open_api_key_dialog(self, kind):
        self._app.open_api_key_dialog(kind)

    def close_api_key_dialog(self):
        self._app.close_api_key_dialog()

    def save_api_key(self, value):
        self._app.save_api_key(value)

    def open_context_menu(self):
        self._app.open_context_menu()

    def close_context_menu(self):
        self._app.close_context_menu()

    def set_toolbar_open(self, open_):
        self._app.set_toolbar_open(open_)

    def begin_icon_drag(self):
        self._app.begin_icon_drag()

    def drag_icon(self, dx, dy):
        self._app.drag_icon(dx, dy)

    def end_icon_drag(self):
        self._app.end_icon_drag()

    def toggle_autostart(self):
        self._app.toggle_autostart()

    def toggle_always_on_top(self):
        self._app.toggle_always_on_top()

    def search_issues(self, kind, query, all_projects=False):
        return self._app.search_issues(kind, query, all_projects)

    def open_issue_by_id(self, issue_id):
        return self._app.open_issue_by_id(issue_id)

    def load_more_issues(self, project_id, source, offset):
        return self._app.load_more_issues(project_id, source, offset)

    def toggle_favorite(self, project_id, name, url, source):
        return self._app.toggle_favorite(project_id, name, url, source)

    def toggle_notify(self, project_id, source):
        return self._app.toggle_notify(project_id, source)

    def set_notify_all(self, source, on):
        return self._app.set_notify_all(source, on)

    def get_resolved_by_version(self, project_id):
        return self._app.get_resolved_by_version(project_id)

    def refresh_resolved_by_version(self, project_id):
        self._app.refresh_resolved_by_version(project_id)

    def get_team_progress(self, project_id):
        return self._app.get_team_progress(project_id)

    def refresh_team_progress(self, project_id):
        self._app.refresh_team_progress(project_id)

    def get_version_progress(self, version_id, source):
        return self._app.get_version_progress(version_id, source)

    def refresh_calendar(self):
        self._app.refresh_calendar()

    def open_toast_url(self, toast_id, url):
        self._app.open_toast_url(toast_id, url)

    def close_toast(self, toast_id):
        self._app.dismiss_toast(toast_id)


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
        self.screen_w, self.screen_h = screen.width, screen.height
        # 기본 자리는 화면 왼쪽 아래(작업표시줄 위). 한 번이라도 끌어서 옮겼으면
        # 그 자리를 기억해 뒀다가 거기서 뜬다(_end_icon_drag 참고).
        default_pos = (
            config.MARGIN,
            screen.height - self.icon_size_physical - config.MARGIN - 40,
        )
        self.icon_x, self.icon_y = self._clamp_icon_pos(
            *(widget_state.load_icon_position() or default_pos)
        )
        self._drag_origin = None  # 드래그 시작 시점의 아이콘 위치

        # 항상 위 표시 - 꺼두면 위젯도 다른 창들처럼 뒤로 갈 수 있다(우클릭 메뉴에서 토글).
        self.always_on_top = widget_state.always_on_top_enabled()

        # 셸 창은 창 사각형 = 눈에 보이는 바 그 자체라(리전으로 잘라내지 않는다 -
        # _round_window_corners 참고), 이 너비가 shell.css의 바 너비와 정확히 같아야
        # 한다. 남으면 아이콘 없는 빈 남색이 붙어 보이고, 모자라면 마지막 아이콘이 잘린다.
        self.shell_w = (
            self.icon_size + config.QUICK_TOOLBAR_MARGIN + config.QUICK_TOOLBAR_TOTAL_W
        )
        self.shell_width = self.icon_size  # 지금 실제 창 너비(접힘 상태로 시작)
        self._shell_anim_id = 0
        # 창 배경을 바와 같은 남색으로 칠하고 모서리만 DWM한테 둥글게 깎아달라고
        # 맡긴다 - transparent=True는 왜 못 쓰는지 포함해서 _round_window_corners 참고.
        self.shell = _create_window(
            "shell", html=bundle_html("shell.html"),
            width=self.icon_size, height=self.icon_size,
            x=self.icon_x, y=self.icon_y,
            frameless=True, on_top=self.always_on_top, resizable=False, shadow=False,
            background_color=CARD_BG["shell.html"],
            easy_drag=False,  # 기본값 True면 창 아무 데나 눌러서 드래그가 돼 스크롤/클릭과 충돌한다
            min_size=(1, 1),  # 기본 최소 크기(200x100)보다 작은 창이 강제로 커지는 것을 막는다
            js_api=Api(self),
            _scale_size=False,  # _apply_geometry 설명 참고 - CSS가 원본 px 그대로라 크기는 안 나눔
            _round_corners=True,
        )
        self.shell.events.loaded += self._push_shell_labels

        self.panel = None
        self.panel_kind = None
        # 프로젝트 트리 두 개도 디스크에 저장돼 있어(redmine_projects_cache.json) 앱을
        # 다시 켜자마자 지난 목록으로 그린다 - 트리 창뿐 아니라 할당된 일감/즐겨찾기의
        # 최상위 프로젝트 구분자(_root_project_name)도 이 목록이 있어야 나오는데, 전에는
        # 조회가 끝날 때까지 구분자 없이 그렸다가 다시 그리느라 목록이 한 번 튀었다.
        cached_projects = redmine_api.load_projects_cache()
        self.company_projects_by_id = {p["id"]: p for p in cached_projects["company"]}
        self.team_projects_by_id = {p["id"]: p for p in cached_projects["team"]}
        # (company_projects_by_id: id -> {id, parent_id, name, ...} 평면 목록,
        # team_projects_by_id는 같은 형식의 팀 레드마인용)
        self.company_tree = redmine_api.build_project_tree(cached_projects["company"])
        self.team_tree = redmine_api.build_project_tree(cached_projects["team"])

        self.favorites = redmine_api.load_favorites()
        # 할당된 일감/즐겨찾기 이슈도 디스크에 저장해 둔다(redmine_my_issues_cache.json /
        # redmine_favorite_issues_cache.json) - 카드를 열자마자 지난 목록을 그리고 뒤에서
        # 새로 받아 갱신한다. 배지 숫자도 셸이 뜨는 순간 이 캐시로 채운다
        # (_push_shell_labels 참고).
        self.my_issues = redmine_api.load_my_issues_cache()
        # f"{source}:{id}" -> issues 리스트(처음엔 최근 200건) / 전체 이슈 개수
        self.favorite_issues, self.favorite_issue_totals = (
            redmine_api.load_favorite_issues_cache()
        )
        self._prune_favorite_issues_cache()
        # 배포 달력이 쓰는 버전 목록 - 디스크에 저장돼 있어 앱을 다시 켜도 남아있다
        # (redmine_calendar_cache.json). None은 "아직 한 번도 못 받아옴"이고 []는
        # "받아왔는데 종료일 잡힌 버전이 없음"이라, 화면이 "불러오는 중"과 "없음"을
        # 구분할 수 있어야 해서 굳이 나눠 둔다(_render_calendar 참고).
        self.calendar_versions = redmine_api.load_calendar_cache()
        # {프로젝트id(str): 그 프로젝트를 마지막으로 골랐을 때 받아온 결과} - 디스크에
        # 저장돼 있어 앱을 다시 켜도 남아있다. 패널을 열 때마다 레드마인 응답을 기다리지
        # 않고 이 캐시부터 보여준 뒤, 뒤에서 새로 받아와 갱신한다(get_resolved_by_version/
        # get_team_progress 참고) - 레드마인 이슈 페이징 조회가 한 프로젝트만 골라도
        # 몇 초씩 걸려서, 클릭할 때마다 매번 기다리게 하면 너무 느리다.
        self.resolved_by_version_cache = redmine_api.load_resolved_by_version_cache()
        self.team_progress_cache = redmine_api.load_team_progress_cache()

        self.api_key_dialog = None
        self.api_key_dialog_kind = None  # "company" 또는 "team" - 지금 여는/열려 있는 창이 어느 쪽 키인지
        self.context_menu = None

        self.seen_issue_ids = redmine_api.load_seen_issues()  # 즐겨찾기별로 이미 알린 이슈 id
        self.toasts = []  # [(toast_id, window), ...] - 아래에서 위로 쌓임
        self._toast_counter = 0

    # ── 메인 아이콘 옆 퀵 툴바 펼침/접힘 ───────────
    def set_toolbar_open(self, open_):
        """툴바를 펼치거나 접는다 - 실제로는 셸 창 너비를 늘렸다 줄이는 게 전부다.

        예전엔 CSS(#toolbar의 max-width transition)가 펼침 애니메이션을 맡고 창은
        한 번에 넓혔다. 창을 버튼 모양대로 잘라내던(SetWindowRgn) 시절엔 창의 빈
        부분이 아예 안 보였으니 그래도 됐는데, 지금은 창 사각형 그대로가 눈에 보이는
        바라(_round_window_corners 참고) 창을 먼저 넓히면 아이콘 없는 빈 남색 바가
        번쩍 나타난 뒤에 아이콘이 따라 들어온다. 그래서 아이콘들은 늘 그려 두고,
        바가 자라면서 그것들이 차례로 드러나게 창 너비 쪽을 애니메이션한다."""
        self._animate_shell_width(self.shell_w if open_ else self.icon_size)

    def _animate_shell_width(self, target):
        # 펼치는 중에 다시 접으라고 하면(빠르게 두 번 클릭) 두 애니메이션이 서로
        # 너비를 되돌리며 싸운다 - 번호를 매겨서 최신 것만 살아남게 한다.
        self._shell_anim_id += 1
        anim_id = self._shell_anim_id
        start = self.shell_width
        if start == target:
            return

        def run():
            for step in range(1, _SHELL_ANIM_STEPS + 1):
                time.sleep(_SHELL_ANIM_MS / 1000 / _SHELL_ANIM_STEPS)
                if anim_id != self._shell_anim_id:
                    return  # 더 최신 애니메이션이 시작됐다
                # ease-out - 처음엔 빠르게, 끝에서 부드럽게 멈춘다
                t = step / _SHELL_ANIM_STEPS
                eased = 1 - (1 - t) ** 3
                self._set_shell_width(target if step == _SHELL_ANIM_STEPS
                                      else round(start + (target - start) * eased))

        threading.Thread(target=run, daemon=True).start()

    def _set_shell_width(self, width):
        self.shell_width = width
        _apply_geometry(
            self.shell, width=width, height=self.icon_size,
            x=self.icon_x, y=self.icon_y, scale_size=False,
        )

    def _push_shell_labels(self):
        """프로젝트 트리 버튼 두 개의 툴팁을 넣어준다. 트리 창 제목과 같은 문구라
        (TREE_TITLES 참고) shell.html에 또 적지 않고 SECTION_LABEL에서 가져온다.

        같은 김에 일감 배지도 캐시로 미리 채운다 - 첫 조회는 알림 루프가 무작위
        지연을 두고 시작해서(start_notify_loop) 배지가 몇 초에서 몇십 초쯤 비어
        있었는데, 배지는 위젯을 접어놔도 늘 보이는 유일한 신호라 그 사이가 "일감
        없음"으로 읽힌다."""
        data = json.dumps(SECTION_LABEL, ensure_ascii=False)
        self.shell.evaluate_js(f"setToolbarLabels({data})")
        if self.my_issues:
            self.shell.evaluate_js(f"setMyIssuesCount({len(self.my_issues)})")

    # ── 아이콘을 끌어서 위젯 옮기기 ────────────────
    def _clamp_icon_pos(self, x, y):
        """아이콘이 화면 밖으로 나가지 않게 자른다. 저장해 둔 위치를 불러올 때도 꼭
        거쳐야 한다 - 그 사이 해상도나 배율이 바뀌었거나 모니터를 뺐으면, 위젯이
        보이지도 않는 자리에 떠서 다시 끌어올 방법이 없어진다."""
        max_x = max(0, self.screen_w - self.icon_size_physical)
        max_y = max(0, self.screen_h - self.icon_size_physical)
        return min(max(0, int(x)), max_x), min(max(0, int(y)), max_y)

    def begin_icon_drag(self):
        # 패널/우클릭 메뉴는 열릴 때 아이콘 위치를 기준으로 자리를 잡는다(open_panel
        # 참고) - 끌고 가는 동안 제자리에 남아 있으면 어색하니 그냥 닫는다.
        self.close_panel()
        self.close_context_menu()
        self._drag_origin = (self.icon_x, self.icon_y)

    def drag_icon(self, dx, dy):
        """드래그 시작점에서 (dx, dy)만큼 옮긴 자리로 위젯을 보낸다(물리 픽셀).
        매번 현재 위치에 더하지 않고 시작점 기준으로 계산하는 이유: 이동 요청이
        하나 유실되거나 화면 끝에서 잘려도 오차가 쌓이지 않는다."""
        if self._drag_origin is None:
            return
        origin_x, origin_y = self._drag_origin
        self.icon_x, self.icon_y = self._clamp_icon_pos(origin_x + dx, origin_y + dy)
        _apply_geometry(self.shell, x=self.icon_x, y=self.icon_y)
        self._reflow_toasts()  # 토스트는 아이콘 옆에 붙어 뜨니 같이 따라가야 한다

    def end_icon_drag(self):
        self._drag_origin = None
        widget_state.save_icon_position(self.icon_x, self.icon_y)

    # ── 윈도우 시작 시 자동 실행 ───────────────────
    def toggle_autostart(self):
        widget_state.set_autostart(not widget_state.autostart_enabled())
        self._push_context_menu()  # 체크 표시를 실제로 적용된 상태로 다시 그린다

    # ── 항상 위에 표시 ─────────────────────────────
    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        widget_state.set_always_on_top(self.always_on_top)
        # 지금 떠 있는 모든 창에 바로 적용한다 - pywebview의 on_top setter가 그 창의
        # TopMost를 즉시 바꿔주니(webview.window.Window.on_top 참고), 새로 여는 창까지
        # 기다릴 필요 없이 아이콘/패널/메뉴 전부 한 번에 뒤로(또는 다시 위로) 간다.
        live_windows = [self.shell, self.context_menu, self.api_key_dialog, self.panel]
        live_windows += [win for _tid, win in self.toasts]
        for win in live_windows:
            if win is not None:
                win.on_top = self.always_on_top
        self._push_context_menu()  # 체크 표시를 실제로 적용된 상태로 다시 그린다

    # ── 우클릭 메뉴 ──────────────────────────────
    def open_context_menu(self):
        if self.context_menu is not None:
            self.context_menu.destroy()
        # 내용이 고정 크기(항목 5개)라 창을 CSS 픽셀 기준으로 잡는다(_scale_size=False,
        # _apply_geometry 설명 참고). 물리 픽셀로 주면 배율이 높은 화면일수록 CSS 뷰포트가
        # 그만큼 줄어서 아래쪽 항목이 잘린다 - 실제로 110% 화면에서 108px로 준 창의
        # 뷰포트가 99px까지 줄어 마지막 항목이 잘려 있었다.
        # 실측 필요 높이는 항목 하나당 35.2 + #win 위아래 패딩 6이다(항목 5개 -> 188.8).
        # 항목을 추가/제거하면 여기 높이도 항목당 36px씩 같이 조정해야 한다(항목 4개 -> 192 - 36).
        w, h = 200, 156
        x = self.icon_x
        # y는 물리 픽셀이라 창이 실제로 차지하는 물리 높이(= CSS 높이 x 배율)를 빼야 한다.
        y = max(self.icon_y - _PANEL_ICON_GAP - round(h * _DPI_SCALE), 0)
        self.context_menu = _create_window(
            "context_menu", html=bundle_html("context_menu.html"),
            width=w, height=h, x=x, y=y,
            frameless=True, on_top=self.always_on_top, resizable=False, shadow=False,
            background_color=CARD_BG["context_menu.html"],
            easy_drag=False, min_size=(1, 1), js_api=Api(self),
            _round_corners=True, _scale_size=False,
        )
        self.context_menu.events.loaded += self._push_context_menu

    def _push_context_menu(self):
        """자동 실행/항상 위 표시가 켜져 있는지를 메뉴에 알려준다(체크 표시). 자동
        실행은 레지스트리를 그때그때 읽으므로, 다른 데서 꺼졌더라도 메뉴를 열면 실제
        상태가 보인다."""
        if self.context_menu is None:
            return
        data = json.dumps({
            "autostart": widget_state.autostart_enabled(),
            "always_on_top": self.always_on_top,
        })
        self.context_menu.evaluate_js(f"renderContextMenu({data})")

    def close_context_menu(self):
        if self.context_menu is not None:
            self.context_menu.destroy()
            self.context_menu = None

    # ── 백그라운드 조회 ──────────────────────────
    def refresh_trees(self):
        # fetch_*_projects는 조회에 실패했을 때도 (API 키가 없을 때와 같이) 빈 리스트를
        # 돌려준다 - 그걸 그대로 받아 쓰면 잠깐의 실패에 트리가 통째로 비어버리고, 캐시에
        # 남아 있던 지난 목록까지 빈 목록으로 덮인다. 갖고 있는 목록이 있는 한 빈 결과는
        # 무시하고 다음 회차를 기다린다(할당된 일감이 None을 건너뛰는 것과 같은 이유).
        def worker_company():
            projects = redmine_api.fetch_redmine_projects()
            if not projects and self.company_projects_by_id:
                return
            self.company_projects_by_id = {p["id"]: p for p in projects}
            redmine_api.save_projects_cache("company", projects)
            self.company_tree = redmine_api.build_project_tree(projects)
            if self.panel_kind == "company_tree":
                self._push_tree()
            elif self.panel_kind in ("my_issues", "favorites"):
                self._push_issues()  # 최상위 프로젝트 구분자를 이제서야 알았으면 다시 그린다

        def worker_team():
            projects = redmine_api.fetch_team_redmine_projects()
            if not projects and self.team_projects_by_id:
                return
            self.team_projects_by_id = {p["id"]: p for p in projects}
            redmine_api.save_projects_cache("team", projects)
            self.team_tree = redmine_api.build_project_tree(projects)
            if self.panel_kind == "team_tree":
                self._push_tree()
            elif self.panel_kind == "favorites":
                self._push_issues()  # 최상위 프로젝트 구분자를 이제서야 알았으면 다시 그린다

        threading.Thread(target=worker_company, daemon=True).start()
        threading.Thread(target=worker_team, daemon=True).start()

    def refresh_my_issues(self):
        threading.Thread(target=self._reload_my_issues, daemon=True).start()

    def _reload_my_issues(self, notify=False):
        """내게 할당된 일감을 다시 받아서 배지와 (열려 있다면) 목록을 갱신한다.
        이미 백그라운드 스레드 위라고 보고 그 자리에서 조회한다 - 알림 루프가
        이걸 직접 부르고, 나머지 호출부는 refresh_my_issues()로 스레드를 띄운다.

        notify=True면 지난번에 없던 일감을 토스트로 알린다(알림 루프에서만 켠다)."""
        issues = redmine_api.fetch_my_issues()
        if issues is None:
            return  # 조회 실패 - 이번 회차는 건너뛰고 기존 목록/배지를 그대로 둔다

        # API 키를 아직 설정 안 했으면 목록이 빈 게 맞지만, 그걸 "일감이 사라졌다"고
        # 기록해두면 나중에 키를 넣은 순간 갖고 있던 일감이 전부 새 일감으로 보인다 -
        # 믿을 수 있는 목록일 때만(키가 있을 때만) 알림 기준을 갱신한다.
        if notify and redmine_api.load_redmine_api_key():
            self._notify_new_my_issues(issues)

        self.my_issues = issues
        redmine_api.save_my_issues_cache(issues)
        if self.panel_kind == "my_issues":
            self._push_issues()
        self.shell.evaluate_js(f"setMyIssuesCount({len(issues)})")

    def _notify_new_my_issues(self, issues):
        """지난 회차에 없던 일감(= 그 사이에 나에게 할당된 일감)을 토스트로 알린다."""
        known = self.seen_issue_ids.get(MY_ISSUES_SEEN_KEY)
        # 처음 보는 경우엔 알리지 않고 지금 목록만 "확인함"으로 기록한다 - 안 그러면
        # 위젯을 처음 켜자마자 갖고 있던 일감 전부가 토스트로 쏟아진다
        # (_check_new_issues의 즐겨찾기 쪽도 같은 방식이다).
        if known is not None:
            known_ids = set(known)
            for issue in issues:
                if issue["issue_id"] not in known_ids:
                    self.show_toast(MY_ISSUES_TOAST_HEADING, issue["title"], issue["url"])
        self.seen_issue_ids[MY_ISSUES_SEEN_KEY] = [issue["issue_id"] for issue in issues]
        redmine_api.save_seen_issues(self.seen_issue_ids)

    def refresh_favorite_issues(self):
        favorites_snapshot = list(self.favorites)
        if not favorites_snapshot:
            return

        def worker():
            for fav in favorites_snapshot:
                source = fav.get("source", "company")
                key = f"{source}:{fav['id']}"
                issues, total = redmine_api.fetch_project_issue_list(fav["id"], source)
                # 조회 실패도 ([], 0)으로 돌아온다(fetch_project_issue_list) - 갖고 있는
                # 목록이 있으면 빈 결과로 덮지 않는다(refresh_trees와 같은 이유).
                if not issues and self.favorite_issues.get(key):
                    continue
                self.favorite_issues[key] = issues
                self.favorite_issue_totals[key] = total
            self._save_favorite_issues_cache()
            if self.panel_kind == "favorites":
                self._push_issues()

        threading.Thread(target=worker, daemon=True).start()

    def _save_favorite_issues_cache(self):
        # 저장하는 사이에 다른 스레드가 즐겨찾기를 추가/해제하면 json.dump가 "dictionary
        # changed size during iteration"으로 터진다 - 얕은 복사본을 넘긴다.
        redmine_api.save_favorite_issues_cache(
            dict(self.favorite_issues), dict(self.favorite_issue_totals),
        )

    def _prune_favorite_issues_cache(self):
        """즐겨찾기에서 빠진 프로젝트의 이슈가 캐시 파일에 남아 있으면 지운다 -
        위젯이 꺼져 있는 동안 파일을 직접 손댔거나, 즐겨찾기 저장은 됐는데 이슈
        캐시 저장 전에 앱이 죽은 경우에 남는다. 그냥 두면 다시는 안 쓸 이슈 수백
        건이 파일에 계속 쌓인다."""
        live = {f"{f.get('source', 'company')}:{f['id']}" for f in self.favorites}
        stale = [key for key in self.favorite_issues if key not in live]
        stale += [k for k in self.favorite_issue_totals if k not in live and k not in stale]
        if not stale:
            return
        for key in stale:
            self.favorite_issues.pop(key, None)
            self.favorite_issue_totals.pop(key, None)
        self._save_favorite_issues_cache()

    # ── 새 이슈 알림 (내 일감 + 즐겨찾기 프로젝트, 기본 3분 주기) ──
    def start_notify_loop(self):
        def poll():
            # 내 일감을 먼저 본다 - 배지는 위젯을 접어놔도 늘 보이는 유일한 신호라
            # 이게 밀리면 안 된다. 둘 다 같은 스레드에서 차례로 하는 이유는
            # seen_issue_ids를 양쪽이 같이 쓰기 때문(따로 돌리면 서로 덮어쓴다).
            self._reload_my_issues(notify=True)
            self._check_new_issues()

        def loop():
            # 이 위젯을 여러 사람이 같이 쓸 때(예: 출근 직후 자동 실행) 다들 같은
            # 순간에 첫 요청을 보내지 않게, 시작 전에 무작위로 조금 기다린다. 그 뒤
            # 주기에도 매번 지터를 더해서 시간이 지나도 여러 PC의 폴링이 한 박자로
            # 안 맞춰지게 한다(config.NOTIFY_POLL_JITTER_MS 참고).
            time.sleep(random.uniform(0, config.NOTIFY_POLL_JITTER_MS) / 1000)
            poll()
            while True:
                jitter = random.uniform(-config.NOTIFY_POLL_JITTER_MS, config.NOTIFY_POLL_JITTER_MS)
                time.sleep(max(5, (config.NOTIFY_POLL_INTERVAL_MS + jitter) / 1000))
                poll()

        threading.Thread(target=loop, daemon=True).start()

    def _check_new_issues(self):
        # 알림을 끈 프로젝트(notify=False)는 아예 조회도 안 한다. 키가 없는 기존
        # 즐겨찾기는 켜짐으로 본다(예전에 저장된 파일도 그대로 동작하게).
        favorites_snapshot = [f for f in self.favorites if f.get("notify", True)]
        if not favorites_snapshot:
            return
        # 레드마인은 project_id로 물으면 하위 프로젝트의 이슈까지 같이 돌려준다
        # (redmine_api.fetch_recent_issues 설명 참고) - 최상위와 하위 프로젝트를 둘 다
        # 즐겨찾기했으면 같은 이슈가 여러 즐겨찾기 조회에 다 걸려서, 그대로 두면 토스트가
        # 그 즐겨찾기 개수만큼 중복으로 뜬다. issue_id를 키로 모아 이슈 하나당 토스트도
        # 딱 하나만 뜨게 하고, 어느 즐겨찾기에서 걸렸는지가 아니라 이슈 자신의 project
        # 값으로 "진짜 소속 프로젝트" 이름을 붙인다.
        new_issues = {}  # issue_id -> issue
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
                        new_issues[issue["id"]] = issue
            # 처음 감시하는 프로젝트는 알림 없이 현재 이슈들만 "확인함"으로 기록
            updated[key] = [issue["id"] for issue in issues]
        self.seen_issue_ids.update(updated)
        redmine_api.save_seen_issues(self.seen_issue_ids)
        for issue in new_issues.values():
            project_name = issue.get("project") or "레드마인"
            self.show_toast(f"{project_name}  새 이슈", issue["subject"], issue["url"])

    def show_toast(self, heading, subject, url):
        """토스트 하나를 띄운다. heading은 첫 줄에 그대로 찍히는 문구다 - 어떤 종류의
        알림인지(즐겨찾기 프로젝트의 새 이슈 / 나에게 할당된 일감) 여기서 정한다."""
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
            frameless=True, on_top=self.always_on_top, resizable=False, shadow=False,
            background_color=CARD_BG["toast.html"],
            easy_drag=False, min_size=(1, 1), js_api=Api(self),
            _round_corners=True,
        )
        self.toasts.append((toast_id, toast))
        self._reflow_toasts()  # 그 사이 다른 토스트가 사라졌으면 자리를 다시 맞춘다

        def push():
            data = json.dumps({
                "id": toast_id, "heading": heading, "subject": subject, "url": url,
            }, ensure_ascii=False)
            toast.evaluate_js(f"renderToast({data})")

        toast.events.loaded += push

    def dismiss_toast(self, toast_id):
        for i, (tid, win) in enumerate(self.toasts):
            if tid == toast_id:
                self.toasts.pop(i)
                win.destroy()
                break
        self._reflow_toasts()

    def _reflow_toasts(self):
        # 메인 아이콘 오른쪽에, 아래에서 위로 쌓아 배치한다.
        # win.move()를 직접 부르면 안 된다 - pywebview가 내부적으로 DPI 배율을 한 번 더
        # 곱해서(_dpi_scale 설명 참고) 배율이 100%가 아닌 화면에서는 토스트가 엉뚱한
        # 자리로 튄다. 창을 만들 때와 똑같이 _apply_geometry를 거쳐야 한다.
        x = self.icon_x + self.icon_size_physical + 12
        base_y = self.icon_y + self.icon_size_physical
        for idx, (_tid, win) in enumerate(self.toasts):
            y = base_y - (idx + 1) * (config.TOAST_H + config.TOAST_GAP)
            _apply_geometry(win, x=x, y=y)

    def open_toast_url(self, toast_id, url):
        webbrowser.open(url)
        self.dismiss_toast(toast_id)

    def open_issue_by_id(self, issue_id):
        """검색창에 이슈 번호만 친 경우 그 이슈를 바로 브라우저로 연다.

        번호만으로는 전사/팀 어느 레드마인인지 알 수 없어서 전사부터 찾아보고 없으면
        팀을 본다. 어느 쪽에도 없으면(또는 볼 권한이 없으면) None을 돌려주고, 그러면
        검색창은 평소대로 제목 검색을 한다(issues_panel.js의 fireSearch 참고)."""
        for source in ("company", "team"):
            issue = redmine_api.fetch_issue(issue_id, source)
            if issue:
                webbrowser.open(issue["url"])
                return issue
        return None

    def search_issues(self, kind, query, all_projects=False):
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
            if all_projects:
                return self._search_all_projects(query)
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
                        "source_label": SECTION_LABEL.get(source, source),
                    })
            return matches
        return []

    def _search_all_projects(self, query):
        """즐겨찾기로 좁히지 않고 전사/팀 레드마인 두 서버 전체 프로젝트를 대상으로 검색한다
        (redmine_api.search_all_projects_issues, 서버당 한 번의 요청). API 키가 없는 서버는
        결과가 None이라 조용히 건너뛴다."""
        matches = []
        for source in ("company", "team"):
            results = redmine_api.search_all_projects_issues(query, source)
            if not results:
                continue
            for r in results:
                matches.append({
                    "issue_id": r["issue_id"], "url": r["url"],
                    "title": f"[{r.get('project_name', '')}] {r['title']}",
                    "tracker": r.get("tracker", ""), "priority": r.get("priority", ""),
                    "source_label": SECTION_LABEL.get(source, source),
                })
        return matches

    def load_more_issues(self, project_id, source, offset):
        more, total = redmine_api.fetch_project_issue_list(project_id, source, offset=offset)
        key = f"{source}:{project_id}"
        self.favorite_issues[key] = self.favorite_issues.get(key, []) + more
        self.favorite_issue_totals[key] = total
        # 더 받아온 페이지까지 캐시에 남겨야, 앱을 다시 켰을 때도 방금 보던 만큼
        # 그대로 보인다(다음 새로고침에서 다시 최근 200건으로 줄어든다).
        self._save_favorite_issues_cache()
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
            self._save_favorite_issues_cache()
        else:
            self.favorites.append({"id": project_id, "name": name, "url": url, "source": source})
            self.refresh_favorite_issues()
        redmine_api.save_favorites(self.favorites)
        if self.panel_kind == "favorites":
            self._push_issues()
        return self.is_favorite(project_id, source)

    def toggle_notify(self, project_id, source):
        """즐겨찾기 프로젝트의 새 이슈 알림을 켜고 끈다(_check_new_issues가 이 값을 본다).
        반환값은 바뀐 뒤의 상태. 목록 전체를 다시 그릴 필요는 없어서 _push_issues는 안 한다."""
        project_id = int(project_id)
        for f in self.favorites:
            if f["id"] == project_id and f.get("source", "company") == source:
                f["notify"] = not f.get("notify", True)
                redmine_api.save_favorites(self.favorites)
                return f["notify"]
        return True

    def set_notify_all(self, source, on):
        """한 레드마인(source)에 속한 즐겨찾기 프로젝트의 알림을 한꺼번에 켜고 끈다.
        구분자 줄의 "전체 알림" 버튼이 쓴다 - 프로젝트가 십수 개씩 되면 종을 하나씩
        누르는 게 일이라서. 반환값은 적용된 상태.

        toggle_notify와 같은 이유로 _push_issues는 안 한다 - 목록 내용은 그대로고
        종 모양만 바뀌므로, 화면 쪽에서 왼쪽 목록만 다시 그리는 게 싸다."""
        on = bool(on)
        changed = False
        for f in self.favorites:
            if f.get("source", "company") == source and f.get("notify", True) != on:
                f["notify"] = on
                changed = True
        if changed:
            redmine_api.save_favorites(self.favorites)
        return on

    # ── 전사/팀 레드마인 API 키 설정 ─────────────
    # 나 혼자만 쓰는 위젯이 아니라서(레드마인 서버가 둘이라 API 키도 따로 필요하다),
    # config.py 주석처럼 텍스트 파일을 직접 열어 붙여넣으라고 하는 대신 우클릭 메뉴 ->
    # 팝업으로 누구나 키를 넣을 수 있게 한다.
    _API_KEY_DIALOG_LABEL = {"company": "전사 레드마인", "team": "팀 레드마인"}

    def open_api_key_dialog(self, kind):
        if kind not in self._API_KEY_DIALOG_LABEL:
            return
        if self.api_key_dialog is not None:
            self.api_key_dialog.destroy()
        self.api_key_dialog_kind = kind
        # 우클릭 메뉴와 같은 이유로 CSS 픽셀 기준(open_context_menu 설명 참고).
        # 폭/높이는 #desc 2줄 안내문 + 입력칸/버튼 줄이 안 잘리게 잡은 값이다 -
        # 문구를 고치면 이 값도 같이 재야 한다.
        w, h = 380, 188
        x = self.icon_x
        y = max(self.icon_y - _PANEL_ICON_GAP - round(h * _DPI_SCALE), 0)
        self.api_key_dialog = _create_window(
            "api_key_dialog", html=bundle_html("api_key_dialog.html"),
            width=w, height=h, x=x, y=y,
            frameless=True, on_top=self.always_on_top, resizable=False, shadow=False,
            background_color=CARD_BG["api_key_dialog.html"],
            easy_drag=False, min_size=(1, 1), js_api=Api(self),
            _round_corners=True, _scale_size=False,
        )
        self.api_key_dialog.events.loaded += self._push_api_key_dialog

    def _push_api_key_dialog(self):
        if self.api_key_dialog is None:
            return
        kind = self.api_key_dialog_kind
        label = self._API_KEY_DIALOG_LABEL.get(kind, "")
        value = (
            redmine_api.load_redmine_api_key() if kind == "company"
            else redmine_api.load_team_redmine_api_key()
        ) or ""
        data = json.dumps({
            "title": f"{label} API 키 설정",
            "desc": (
                f"{label} 접속 후 오른쪽 위 계정 &gt; 개인 설정 페이지에서 API 키를<br>"
                "발급받아 붙여넣으세요. 이 PC에 저장되며, 위젯을 쓰는 모두가 같은 키를 씁니다."
            ),
            "value": value,
        }, ensure_ascii=False)
        self.api_key_dialog.evaluate_js(f"renderApiKeyDialog({data})")

    def close_api_key_dialog(self):
        if self.api_key_dialog is not None:
            self.api_key_dialog.destroy()
            self.api_key_dialog = None
        self.api_key_dialog_kind = None

    def save_api_key(self, value):
        value = (value or "").strip()
        kind = self.api_key_dialog_kind
        if not value or kind not in self._API_KEY_DIALOG_LABEL:
            return
        if kind == "company":
            redmine_api.save_redmine_api_key(value)
        else:
            redmine_api.save_team_redmine_api_key(value)
        self.close_api_key_dialog()
        self.refresh_trees()  # 방금 넣은 키로 바로 프로젝트 목록을 다시 받아온다
        if kind == "company":
            self.refresh_my_issues()  # "할당된 일감"도 전사 레드마인 API 키로만 조회된다

    # ── 패널 열기/닫기(토글) ──────────────────────
    def _panel_geometry(self, panel_w, panel_h):
        """PANEL_SPEC 크기를 이 화면에 들어가는 만큼으로 자르고, 아이콘 바로 위에
        붙는 좌표까지 같이 돌려준다(x, y, w, h - 전부 물리 px).

        PANEL_SPEC 값은 1920x1080 기준으로 잡아 둔 거라, 더 작은 화면(노트북 등)이나
        아이콘을 화면 위쪽으로 끌어다 둔 상태에서 그대로 열면 창 위쪽이 화면 밖으로
        잘려 나간다. 패널은 아이콘 위에 붙으므로 세로 상한은 "아이콘 위에 남은 자리"고,
        가로는 왼쪽으로 밀어서 맞추되 그래도 넘치면 화면 너비까지 줄인다.
        _clamp_icon_pos와 같은 이유로 필요한 처리다."""
        panel_h = min(panel_h, max(self.icon_y - _PANEL_ICON_GAP, _PANEL_MIN_H))
        panel_w = min(panel_w, self.screen_w)
        x = min(self.icon_x, max(self.screen_w - panel_w, 0))
        y = max(self.icon_y - _PANEL_ICON_GAP - panel_h, 0)
        return x, y, panel_w, panel_h

    # 모든 패널은 같은 self.panel 슬롯 하나를 재사용한다 - 팝업으로 따로 안 튀어나오고
    # 항상 위젯 아이콘 바로 위(같은 위치)에 뜨게 하기 위함이다.
    def open_panel(self, kind):
        if kind not in PANEL_SPEC:
            return

        # 다른 화면을 여는 순간, 열려 있던 우클릭 메뉴/API 키 설정 창은 닫는다. 이
        # 창들은 항상 위(on_top)에 떠 있어서, 안 닫으면 새로 연 패널을 가린 채 남는다.
        self.close_context_menu()
        self.close_api_key_dialog()

        if self.panel is not None:
            was_same = self.panel_kind == kind
            self.panel.destroy()
            self.panel = None
            self.panel_kind = None
            if was_same:
                return

        self.panel_kind = kind
        template, panel_w, panel_h = PANEL_SPEC[kind]
        x, y, panel_w, panel_h = self._panel_geometry(panel_w, panel_h)
        self.panel = _create_window(
            "panel", html=bundle_html(template),
            width=panel_w, height=panel_h, x=x, y=y,
            frameless=True, on_top=self.always_on_top, resizable=False, shadow=False,
            background_color=CARD_BG[template],
            easy_drag=False,  # 기본값 True면 목록 스크롤/클릭이 창 드래그로 먹힌다
            min_size=(1, 1), js_api=Api(self),
            _round_corners=True,
        )
        if kind in TREE_TITLES:
            self.panel.events.loaded += self._push_tree
        elif kind == "resolved_by_version":
            self.panel.events.loaded += self._push_resolved_tree
        elif kind == "team_progress":
            self.panel.events.loaded += self._push_team_progress_tree
        elif kind == "deploy_calendar":
            self.panel.events.loaded += self._push_calendar
        else:
            # 캐시로 먼저 그린 뒤(_push_issues) 항상 뒤에서 다시 받아온다 - 배포 달력과
            # 같은 방식(_push_calendar 참고). 전에는 "할당된 일감"이 비어 있을 때만
            # 받아왔는데, 이제 캐시 덕에 비는 일이 없어서 그대로 두면 카드를 열어도
            # 지난 목록만 계속 보인다.
            self.panel.events.loaded += self._push_issues
            if kind == "my_issues":
                self.refresh_my_issues()
            else:
                self.refresh_favorite_issues()

    def close_panel(self):
        """메인 아이콘을 누르면(shell.js의 mainIcon 클릭) 열려있던 카드를 닫는다."""
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
            self.panel_kind = None

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
        data = json.dumps({"tree": self.company_tree}, ensure_ascii=False)
        self.panel.evaluate_js(f"renderResolvedPanel({data})")

    def get_resolved_by_version(self, project_id):
        """최상위(하위 프로젝트가 있는) 프로젝트를 고르면 그 자신뿐 아니라 하위
        프로젝트에 걸린 로드맵/일감까지 다 모아서 보여준다 - 실제 배포 버전은 하위
        프로젝트 쪽에 달려 있는 경우가 많아서, 최상위 하나만 보면 화면이 텅 비어
        보인다(_resolved_targets 참고). 하위가 둘 이상 섞이면 버전 이름이 겹칠 수
        있어 각 항목에 project 필드를 붙인다(_fetch_resolved_by_version).

        캐시(self.resolved_by_version_cache)에 이 프로젝트(선택한 노드 기준) 결과가
        있으면 레드마인을 새로 묻지 않고 바로 돌려주고, 최신 데이터는 뒤에서 조용히
        받아와 갱신한다(_refresh_resolved_by_version 참고) - 없으면(처음 고르는
        프로젝트) 이번 한 번만 기다린다. 레드마인 이슈 페이징 조회가 프로젝트 하나만
        골라도 몇 초씩 걸려서, 클릭할 때마다 매번 기다리게 하면 너무 느리다."""
        project_id = int(project_id)
        targets = self._resolved_targets(project_id)
        if not targets:
            return []

        cache_key = str(project_id)
        cached = self.resolved_by_version_cache.get(cache_key)
        if cached is not None:
            threading.Thread(
                target=self._refresh_resolved_by_version, args=(project_id, targets), daemon=True,
            ).start()
            return cached

        result = self._fetch_resolved_by_version(targets)
        self.resolved_by_version_cache[cache_key] = result
        redmine_api.save_resolved_by_version_cache(self.resolved_by_version_cache)
        return result

    def refresh_resolved_by_version(self, project_id):
        """화면 안 새로고침 아이콘이 부른다 - get_resolved_by_version처럼 캐시부터
        돌려주고 기다리는 대신, 지금 고른 프로젝트를 곧바로 다시 받아와 화면을 갱신한다
        (_refresh_resolved_by_version이 다 받아오면 evaluate_js로 밀어준다)."""
        project_id = int(project_id)
        targets = self._resolved_targets(project_id)
        if not targets:
            return
        threading.Thread(
            target=self._refresh_resolved_by_version, args=(project_id, targets), daemon=True,
        ).start()

    def _resolved_targets(self, project_id):
        """project_id 노드를 트리에서 찾아 자기 자신 + 모든 하위 프로젝트를
        [(id, name), ...]로 평평하게 돌려준다(고른 게 최상위면 하위 전부, 이미 말단
        이면 자기 자신 하나). 트리에 없는 id면 []."""
        def find(nodes):
            for n in nodes:
                if n["id"] == project_id:
                    return n
                found = find(n.get("children") or [])
                if found is not None:
                    return found
            return None

        node = find(self.company_tree)
        if node is None:
            return []

        targets = []

        def collect(n):
            targets.append((n["id"], n["name"]))
            for c in n.get("children") or []:
                collect(c)

        collect(node)
        return targets

    def _fetch_resolved_by_version(self, targets):
        multiple = len(targets) > 1
        if not multiple:
            pid, _name = targets[0]
            return redmine_api.fetch_issues_by_version(pid)

        # 최상위를 골라 하위 프로젝트를 다 훑을 때, 순서대로 하나씩 물으면 프로젝트
        # 개수만큼 시간이 곱해져 너무 느려진다(하위가 수십 개면 몇십 초씩 걸렸다) -
        # 몇 개씩 동시에 물어서 기다리는 시간을 줄인다.
        result = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(redmine_api.fetch_issues_by_version, pid): name
                for pid, name in targets
            }
            for future in as_completed(futures):
                name = futures[future]
                for g in future.result():
                    result.append({**g, "project": name})
        return result

    def _refresh_resolved_by_version(self, project_id, targets):
        """get_resolved_by_version이 캐시를 먼저 돌려준 뒤 백그라운드에서 부르는 함수.
        새로 받아온 결과로 캐시를 갱신하고, 그 사이 다른 프로젝트로 안 넘어갔으면
        (패널이 여전히 열려 있고 버전별 연결된 일감 화면이면) 화면도 최신으로 다시 그린다."""
        result = self._fetch_resolved_by_version(targets)
        self.resolved_by_version_cache[str(project_id)] = result
        redmine_api.save_resolved_by_version_cache(self.resolved_by_version_cache)
        if self.panel is not None and self.panel_kind == "resolved_by_version":
            data = json.dumps(result, ensure_ascii=False)
            self.panel.evaluate_js(f"updateVersionGroups({project_id}, {data})")

    def _push_team_progress_tree(self):
        if self.panel is None:
            return
        # 왼쪽 목록은 전사 레드마인 최상위(루트) 프로젝트("Cybertel Bridge" 같은 회사/
        # 조직 단위) 그대로 쓴다. 실제 "팀"은 최상위가 아니라 대체로 그 바로 아래
        # 자식 프로젝트다(예: Cybertel Bridge 밑의 "MCX솔루션 개발팀", "기구팀" 등) -
        # 그래서 최상위를 고르면 get_team_progress가 자식 단위로 쪼개서 보여준다.
        data = json.dumps({"teams": self.company_tree}, ensure_ascii=False)
        self.panel.evaluate_js(f"renderTeamProgressPanel({data})")

    def get_team_progress(self, project_id):
        """왼쪽 트리에서 고른 게 최상위(루트) 프로젝트면 그 바로 아래 depth 1 자식
        (팀)마다 섹션을 나누고, 각 팀 섹션 안에서 다시 그 팀의 depth 2 자식 프로젝트별로
        구분해서 보여준다 - 실제 "팀"은 최상위가 아니라 그 한 단계 아래 단위인 경우가
        많고(_push_team_progress_tree 설명 참고), 팀 밑에도 "국내 프로젝트"/"해외
        프로젝트"처럼 성격이 다른 하위 프로젝트가 섞여 있어서, depth 2까지 나눠야 어떤
        프로젝트 진행 상황인지 한눈에 구분된다. 고른 게 depth 1(팀 자신)이면 팀 하나에
        대해서만 depth 2로 나눠 보여준다. depth 2 자식이 없는 팀/프로젝트는 자기 자신
        하나를 그 depth 2 그룹으로 취급한다.
        반환 형식: [{"team": str, "team_id": int,
                     "subgroups": [{"team": str, "team_id": int, "is_subproject": bool,
                                     "versions": [...]}, ...]},
                    ...]
        (subgroups 안의 "versions"는 fetch_team_progress 반환값과 동일. is_subproject가
        False면 depth 2 자식이 없어 팀 자신을 그룹으로 대신 쓴 것이라, "team" 이름이
        위 팀 이름과 똑같다 - team_progress.js가 이때 뱃지를 안 그린다)

        캐시(self.team_progress_cache)에 이 프로젝트 결과가 있으면 레드마인을 새로
        묻지 않고 그걸 바로 돌려주고, 최신 데이터는 뒤에서 조용히 받아와 갱신한다
        (_refresh_team_progress 참고) - 없으면(처음 고르는 프로젝트) 이번 한 번만
        기다린다."""
        project_id = int(project_id)
        team_nodes = self._team_progress_nodes(project_id)
        if team_nodes is None:
            return []

        cache_key = str(project_id)
        cached = self.team_progress_cache.get(cache_key)
        if cached is not None:
            threading.Thread(
                target=self._refresh_team_progress, args=(project_id, team_nodes), daemon=True,
            ).start()
            return cached

        result = self._fetch_team_progress(team_nodes)
        self.team_progress_cache[cache_key] = result
        redmine_api.save_team_progress_cache(self.team_progress_cache)
        return result

    def refresh_team_progress(self, project_id):
        """화면 안 새로고침 아이콘이 부른다 - get_team_progress처럼 캐시부터 돌려주고
        기다리는 대신, 지금 고른 조직/팀을 곧바로 다시 받아와 화면을 갱신한다
        (_refresh_team_progress가 다 받아오면 evaluate_js로 밀어준다)."""
        project_id = int(project_id)
        team_nodes = self._team_progress_nodes(project_id)
        if team_nodes is None:
            return
        threading.Thread(
            target=self._refresh_team_progress, args=(project_id, team_nodes), daemon=True,
        ).start()

    def _team_progress_nodes(self, project_id):
        """project_id로 고른 노드가 최상위(루트)면 그 depth 1 자식들을, 팀 자신(depth 1)
        이면 그 하나만 담은 리스트를 돌려준다(get_team_progress 설명 참고). 트리에
        없는 id면 None."""
        root = next((n for n in self.company_tree if n["id"] == project_id), None)
        if root is not None:
            return root.get("children") or [root]
        for r in self.company_tree:
            child = next((c for c in r.get("children", []) if c["id"] == project_id), None)
            if child is not None:
                return [child]
        return None

    def _fetch_team_progress(self, team_nodes):
        # 팀(depth 1)마다 순서대로 조회하면 팀 개수만큼 시간이 곱해져 너무 느려지므로,
        # 모든 팀의 depth 2 자식을 한 평평한 목록으로 모아 한 번에 조회한 뒤 팀별로
        # 다시 묶는다.
        flat = []  # [(project_id, name, team_index, is_subproject), ...]
        for team_index, team_node in enumerate(team_nodes):
            children = team_node.get("children") or []
            # depth 2 자식이 없는 팀은 자기 자신 하나를 그 depth 2 그룹으로 취급한다
            # (get_team_progress 설명 참고) - 이때는 subgroup의 "team" 이름이 위에
            # 이미 붙는 team-heading과 똑같아지므로, is_subproject를 False로 표시해서
            # JS 쪽이 중복되는 뱃지를 안 그리게 한다(team_progress.js renderSubgroup 참고).
            is_subproject = bool(children)
            for c in (children or [team_node]):
                flat.append((c["id"], c["name"], team_index, is_subproject))

        flat_results = redmine_api.fetch_org_progress([(pid, name) for pid, name, _, _ in flat])

        result = [{"team": t["name"], "team_id": t["id"], "subgroups": []} for t in team_nodes]
        for (_pid, _name, team_index, is_subproject), r in zip(flat, flat_results):
            r["is_subproject"] = is_subproject
            result[team_index]["subgroups"].append(r)
        return result

    def _refresh_team_progress(self, project_id, team_nodes):
        """get_team_progress가 캐시를 먼저 돌려준 뒤 백그라운드에서 부르는 함수.
        새로 받아온 결과로 캐시를 갱신하고, 그 사이 다른 조직/팀으로 안 넘어갔으면
        (패널이 여전히 열려 있고 팀별 진행상황 화면이면) 화면도 최신으로 다시 그린다."""
        result = self._fetch_team_progress(team_nodes)
        self.team_progress_cache[str(project_id)] = result
        redmine_api.save_team_progress_cache(self.team_progress_cache)
        if self.panel is not None and self.panel_kind == "team_progress":
            data = json.dumps(result, ensure_ascii=False)
            self.panel.evaluate_js(f"updateOrgCol({project_id}, {data})")

    # ── 배포 달력 ─────────────────────────────────
    # 즐겨찾기한 프로젝트의 배포 버전(종료일이 잡힌 것)을 달마다 점으로 찍어 보여주는
    # 화면. 다른 화면들과 달리 왼쪽에서 프로젝트를 고를 필요가 없다 - 즐겨찾기 전체를
    # 가로질러 "언제 무엇이 나가는지"를 한 번에 보는 게 이 화면의 존재 이유라서다.
    def _push_calendar(self):
        # 캐시가 있으면 그걸로 즉시 그려서 창이 비어 보이지 않게 하고, 그 뒤에 항상
        # 다시 받아온다 - 배포일은 자주 바뀌진 않지만 창을 열 때만큼은 최신이어야 한다.
        self._render_calendar()
        self.refresh_calendar()

    def refresh_calendar(self):
        threading.Thread(target=self._reload_calendar, daemon=True).start()

    def _reload_calendar(self):
        pairs = [
            (f["id"], f["name"], f.get("source", "company")) for f in self.favorites
        ]
        versions = redmine_api.fetch_calendar_versions(pairs)
        # fetch_calendar_versions는 조회에 실패한 프로젝트를 조용히 건너뛴다 - 네트워크가
        # 통째로 끊긴 회차엔 빈 목록이 돌아오고, 그대로 저장하면 캐시에 남아 있던 배포
        # 일정까지 지워진다("배포 예정 없음"으로 보인다). 갖고 있는 목록이 있으면 빈
        # 결과는 무시한다(refresh_trees/refresh_favorite_issues와 같은 이유).
        if not versions and self.calendar_versions:
            return
        self.calendar_versions = versions
        redmine_api.save_calendar_cache(self.calendar_versions)
        if self.panel_kind == "deploy_calendar":
            self._render_calendar()

    def _calendar_years(self):
        """공휴일을 뽑을 연도 목록. 버전 종료일이 걸린 연도들과 오늘 연도를 합치고,
        달만 넘겨도(예: 12월->1월) 빈 연도가 안 나오게 앞뒤 1년을 여유로 더한다."""
        years = {time.localtime().tm_year}
        for v in self.calendar_versions or []:
            due_date = v.get("due_date")
            if due_date:
                years.add(int(due_date[:4]))
        years.update({min(years) - 1, max(years) + 1})
        return years

    def _render_calendar(self):
        if self.panel is None:
            return
        versions = self.calendar_versions
        # holidays_for_year가 이미 {"YYYY-MM-DD": 이름} 꼴로 주므로(화면이 쓰는 모양
        # 그대로라 변환할 게 없다) 연도별 결과를 그냥 합치기만 한다. 음력 표에 없는
        # 연도는 빈 dict가 아니라 양력 공휴일만 담겨 오므로 따로 거를 필요도 없다.
        holidays = {}
        for year in self._calendar_years():
            holidays.update(korean_holidays.holidays_for_year(year))
        data = json.dumps(
            {
                "versions": versions or [],
                "loading": versions is None,
                # 즐겨찾기가 아예 없으면 "버전이 없다"가 아니라 "즐겨찾기부터 하라"고
                # 안내해야 해서, 화면이 두 경우를 구분할 수 있게 같이 넘긴다.
                "has_favorites": bool(self.favorites),
                "today": time.strftime("%Y-%m-%d"),
                # 달력은 달을 넘길 때 서버에 다시 묻지 않으므로(전부 클라이언트에서
                # 그린다) 공휴일도 창을 열 때 아는 연도치를 통째로 넘겨둔다.
                # 수백 건이 아니라 수십 건이라 payload에 부담이 없다.
                "holidays": holidays,
            },
            ensure_ascii=False,
        )
        self.panel.evaluate_js(f"renderCalendarPanel({data})")

    def get_version_progress(self, version_id, source):
        """달력에서 날짜를 눌렀을 때 그 날 나가는 버전의 진행률을 센다.
        실패하면 None - 화면은 진행률만 빼고 나머지를 그대로 보여준다."""
        return redmine_api.fetch_version_issue_counts(version_id, source)

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

    def _root_project_name(self, project_id, source="company"):
        """company_projects_by_id/team_projects_by_id의 parent_id를 타고 올라가
        최상위 프로젝트 이름을 찾는다. 그 프로젝트 자신이 이미 최상위거나, 아직
        트리를 못 받았거나(비어있음), 모르는 project_id면 None을 돌려준다 - 호출부에서
        그룹 이름으로 대신 채운다."""
        projects_by_id = self.team_projects_by_id if source == "team" else self.company_projects_by_id
        node = projects_by_id.get(project_id)
        if node is None:
            return None
        seen = set()
        while node.get("parent_id") is not None and node["parent_id"] not in seen:
            parent = projects_by_id.get(node["parent_id"])
            if parent is None:
                break
            seen.add(node["parent_id"])
            node = parent
        return node["name"]

    def _my_issues_groups(self):
        # "[프로젝트명] 제목" 형태인 제목에서 프로젝트명을 뽑아 프로젝트별로 묶고,
        # 그 프로젝트의 최상위 프로젝트를 구분자(section)로 붙인다.
        groups = {}
        order = []
        for issue in self.my_issues:
            m = re.match(r"^\[(.+?)\]\s*(.*)$", issue["title"])
            project_name, subject = (m.group(1), m.group(2)) if m else ("프로젝트 미상", issue["title"])
            if project_name not in groups:
                section = self._root_project_name(issue.get("project_id")) or project_name
                groups[project_name] = {"section": section, "issues": []}
                order.append(project_name)
            groups[project_name]["issues"].append({
                "issue_id": issue["issue_id"], "title": subject, "url": issue["url"],
                "tracker": issue.get("tracker", ""), "priority": issue.get("priority", ""),
            })
        order.sort(key=lambda p: (groups[p]["section"], p))
        return [
            {"project": p, "issues": groups[p]["issues"], "section": groups[p]["section"]}
            for p in order
        ]

    def _favorite_groups(self):
        def to_group(f):
            source = f.get("source", "company")
            key = f"{source}:{f['id']}"
            issues = self.favorite_issues.get(key, [])
            # _root_project_name은 이 프로젝트 자신이 이미 최상위면 자기 이름을 그대로
            # 돌려준다("할당된 일감" 쪽은 그래야 항상 구분자가 있다) - 즐겨찾기는 그 경우
            # 카드 이름과 겹치는 구분자를 또 넣을 필요가 없어서 여기서 None으로 걸러낸다.
            root = self._root_project_name(f["id"], source)
            parent = root if root and root != f["name"] else None
            return {
                "project": f["name"],
                # 최상위 프로젝트가 다르면 카드 목록에서 그 이름으로 작은 구분자를 하나
                # 더 넣는다("전사/팀 레드마인" 구분자 안쪽에서 한 단계 더 - issues_panel.js
                # renderLeft 참고). 이 프로젝트 자신이 최상위면 구분자 없이 카드만 보여준다.
                "parent": parent,
                "issues": issues,
                "section": SECTION_LABEL.get(source, source),
                "_order": SECTION_ORDER.get(source, 99),
                "project_id": f["id"],
                "source": source,
                "url": f.get("url", ""),
                "notify": f.get("notify", True),
                "total": self.favorite_issue_totals.get(key, len(issues)),
            }

        groups = sorted(
            (to_group(f) for f in self.favorites),
            key=lambda g: (g["_order"], g["parent"] or g["project"], g["project"]),
        )
        for g in groups:
            del g["_order"]
        return groups


def main():
    app = App()

    def startup():
        app.refresh_trees()
        app.refresh_favorite_issues()
        # 내 일감은 따로 안 부른다 - 알림 루프가 시작하자마자 한 번 조회하면서
        # 배지까지 채운다(App.start_notify_loop 참고).
        app.start_notify_loop()

    webview.start(startup, debug=False)


if __name__ == "__main__":
    main()
