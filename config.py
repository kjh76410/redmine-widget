"""
설정 상수 모음 - 링크/색상/크기/아이콘 파일 경로 등, 위젯 전체에서 공유하는 값들.
FONT_FAMILY만 예외로 load_app_font() 호출 뒤 실제 사용할 폰트명으로 바뀌는 뮤터블
전역값이라(다른 모듈은 이 값을 "복사"해오면 안 되고 항상 config.FONT_FAMILY로 접근해야
최신값을 본다), 그 값을 바꾸는 load_app_font()도 여기 같이 둔다.
"""

import ctypes
from pathlib import Path

import tkinter.font as tkfont

# ─────────────────────────────────────────────
# 1. 여기만 수정하면 됩니다 : 뱃지에 표시할 링크 목록
#    (표시이름, URL, 이모지 아이콘)
# ─────────────────────────────────────────────
LINKS = [
    ("전사 레드마인",    "http://10.1.100.150/redmine/issues", "🏢"),
]

TEAM_REDMINE_URL = "http://10.1.100.20/projects"  # 팀 레드마인 (전사 레드마인과 별도 서버) 프로젝트 목록 폴백 링크

# ─────────────────────────────────────────────
# 브라우저 선택
#   None  → 시스템 기본 브라우저로 열기 (권장)
#   특정 브라우저 강제 지정 예시:
#     BROWSER = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
#     BROWSER = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# ─────────────────────────────────────────────
BROWSER = None

# ─────────────────────────────────────────────
# 2. 색상 / 크기 설정
# ─────────────────────────────────────────────
ICON_SIZE   = 56          # 아이콘 버튼 한 변 크기(px)
ICON_IMAGE  = Path(__file__).parent / "assets" / "icons" / "main.png"    # 아이콘 이미지 경로
ICON_KEY_COLOR = "#FF00FF"  # 아이콘 창을 투명하게 만드는 색상 키 (실제로 쓰이는 색이 아니므로 테마와 무관하게 고정)
ICON_BUTTON_BG = "#152340"  # 아이콘 배경(둥근 네모) 색 - 남색
ICON_BUTTON_FG = "#FFFFFF"  # 아이콘 자체 색 - 흰색 실루엣
ICON_RADIUS = 10          # 아이콘 배경 둥근 네모의 모서리 반경(px)
ICON_GLYPH_PAD = 10       # 아이콘 배경 안쪽에서 실제 그림이 차지하는 여백(px, 사방 동일)
MARGIN      = 20          # 화면 가장자리로부터의 여백(px)

# 메인 아이콘 옆에 뜨는 퀵 툴바(내 일감 / 즐겨찾기 / 전체 프로젝트 / 팀 레드마인 / 버전별 해결 일감 원형 아이콘 5개) 설정
QUICK_TOOLBAR_ICON_SIZE  = 52   # 아이콘 배경(둥근 네모) 한 변 크기(px)
QUICK_TOOLBAR_RADIUS     = 12   # 아이콘 배경 둥근 네모의 모서리 반경(px) - 메인 아이콘과 비슷한 느낌
QUICK_TOOLBAR_GLYPH_PAD  = 9    # 배경 안쪽에서 실제 그림이 차지하는 여백(px, 사방 동일) - 메인 아이콘과 비슷한 비율
QUICK_TOOLBAR_GAP        = 10   # 아이콘 사이 간격(px)
QUICK_TOOLBAR_MARGIN     = 10   # 메인 아이콘과 퀵 툴바 사이 가로 간격(px)
QUICK_TOOLBAR_BUTTON_COUNT = 5  # 아이콘 개수(내 일감 / 즐겨찾기 / 전체 프로젝트 / 팀 레드마인 / 버전별 해결 일감)
QUICK_TOOLBAR_TOTAL_W = (
    QUICK_TOOLBAR_ICON_SIZE * QUICK_TOOLBAR_BUTTON_COUNT
    + QUICK_TOOLBAR_GAP * (QUICK_TOOLBAR_BUTTON_COUNT - 1)
)  # 퀵 툴바 전체 너비(px) - 플라이아웃을 그 오른쪽에 이어 붙이는 데 사용
MY_ICON_FILE       = Path(__file__).parent / "assets" / "icons" / "my.png"
BOOKMARK_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "bookmark.png"
FOLDER_ICON_FILE   = Path(__file__).parent / "assets" / "icons" / "folder.png"
WINDOW_ICON_FILE   = Path(__file__).parent / "assets" / "icons" / "window.png"
SEARCH_ICON_FILE   = Path(__file__).parent / "assets" / "icons" / "search.png"
SEARCH_ICON_SIZE   = 14  # 검색 버튼 안 돋보기 아이콘 크기(px)

# 폰트 파일 하나만 설치 없이 이 프로세스에서만 쓰도록 등록해서 쓴다.
# Pretendard-Regular.otf는 CFF(PostScript) 외곽선 방식이라 윈도우 GDI 텍스트 렌더러와
# 궁합이 안 좋아 글자가 얇아지거나 깨져 보였다. NotoSansKR-Regular.ttf는 GDI가 안정적으로
# 지원하는 진짜 트루타입(glyf) 방식이라 이걸 쓴다.
# 등록에 실패하면(윈도우가 아니거나, 파일이 없거나) 시스템 기본 한글 폰트로 자동 대체된다.
FONT_FILE = Path(__file__).parent / "assets" / "fonts" / "NotoSansKR-Regular.ttf"
FONT_FILE_FAMILY = "Noto Sans KR"  # 위 파일이 등록됐을 때 실제로 쓸 폰트 패밀리명
FONT_FAMILY_FALLBACK = "맑은 고딕"
FONT_FAMILY = FONT_FAMILY_FALLBACK  # load_app_font() 호출 후 실제 사용할 폰트명으로 바뀐다
BG_COLOR    = "#6E92C8"   # 포인트 컬러(Accent)
BADGE_BG    = "#233149"   # 뱃지/카드 배경색 (패널 배경보다 살짝 밝은 표면색)
BADGE_FG    = "#E4E9F2"   # 뱃지 글자색(주 텍스트)
BADGE_FG_MUTED = "#98A2B8"  # 보조/설명 텍스트 색
BADGE_HOVER  = "#313F63"  # 뱃지 호버 배경색 (포인트 컬러 톤이 살짝 섞인 밝은 표면색)
BADGE_SELECTED_BG = BG_COLOR   # 펼쳐져서 선택된(depth 진입한) 뱃지 배경색 = 포인트 컬러
BADGE_SELECTED_FG = "#FFFFFF"  # 선택된 뱃지 글자색
BADGE_RADIUS = 15         # 뱃지 모서리 둥근 정도(px)
SUB_BADGE_H  = 38         # 플라이아웃(하위 프로젝트) 뱃지 높이(px)
SHADOW_COLOR = "#061431"  # 카드 아래에 깔리는 그림자색 (어두운 배경이라 더 어둡게)
SHADOW_OFFSET = 3         # 그림자 오프셋(px)
PANEL_BG    = ICON_BUTTON_BG   # 패널 배경색 - 메인 아이콘과 같은 남색
FLYOUT_W    = 300         # 플라이아웃 패널 너비(px, 전사 프로젝트/즐겨찾기 공용)
MY_ISSUES_FLYOUT_W = 460  # "내 일감" 플라이아웃 너비(px) - 이슈 제목이 길어서 더 넓게
PANEL_GAP   = 6           # 패널/플라이아웃 사이 가로 간격(px)
WIDGET_WINDOW_H = 760     # "내 일감"/"즐겨찾기 프로젝트" 창 높이 - 전사 프로젝트 플라이아웃도 높이를 여기에 맞춤
GO_ZONE_W   = 26          # 하위 항목이 있는 뱃지 오른쪽 끝의 "바로 이동" 버튼 클릭 영역 너비(px)
GO_ICON_SIZE = 16         # "바로 이동" 버튼 아이콘 크기(px)
GO_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "go.png"
# 이슈 카드 우선순위 뱃지 아이콘 - "긴급"/"즉시"는 별도 아이콘이 없어 critical.png를 같이 쓴다.
PRIORITY_ICON_SIZE = 12
LOW_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "low.png"
MIDDLE_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "middle.png"
HIGH_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "high.png"
CRITICAL_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "critical.png"
ISSUE_BADGE_PAD_X = 6     # 이슈 id 뱃지(필) 좌우 안쪽 여백(px)
ISSUE_BADGE_H     = 20    # 이슈 id 뱃지(필) 높이(px)
ISSUE_BADGE_GAP   = 8     # 이슈 id 뱃지와 제목(첫 줄) 사이 가로 간격(px)
ISSUE_ROW_PAD_Y   = 6     # 이슈 뱃지 위/아래 안쪽 여백(px)
ISSUE_LINE_GAP    = 2     # 이슈 제목 1줄째와 2줄째 사이 세로 간격(px)
SEARCH_BOX_H      = 38    # 이슈 목록 위 검색창이 차지하는 높이(px, 여백 포함)
TOAST_W      = 300        # 새 이슈 알림 토스트 너비(px)
TOAST_H      = 68         # 새 이슈 알림 토스트 높이(px)
TOAST_GAP    = 8          # 토스트 사이 세로 간격(px)
TOAST_DURATION_MS = 8000  # 토스트가 자동으로 사라지기까지 시간(ms)
TOAST_ICON_SIZE = 20       # 토스트 왼쪽에 표시할 알람 아이콘(흰색 실루엣) 크기(px)
TOAST_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "alarm.png"
TOAST_CHIP_SIZE = 34       # 알람 아이콘 뒤 포인트 컬러 배지(둥근 네모) 크기(px)
TOAST_CHIP_RADIUS = 10     # 알람 아이콘 뒤 배지의 모서리 반경(px)

# 레드마인 프로젝트 뱃지를 우클릭해 즐겨찾기한 목록이 저장되는 파일 (앱을 다시 실행해도 유지됨)
FAVORITES_FILE = Path(__file__).parent / "redmine_favorites.json"

# 즐겨찾기한 프로젝트에서 이미 알림을 보낸 이슈 id 목록이 저장되는 파일 (앱을 다시 실행해도 유지됨)
SEEN_ISSUES_FILE = Path(__file__).parent / "redmine_seen_issues.json"

# 새 이슈를 확인하는 주기(ms)
NOTIFY_POLL_INTERVAL_MS = 60 * 1000

# True면 즐겨찾기 여부와 상관없이 전사 레드마인 전체 프로젝트의 새 이슈를 알림.
# 프로젝트가 많으면(수백 개) 1분 주기 안에 순서대로 다 조회하지 못해 요청이 밀리고
# 타임아웃이 늘면서 오히려 알림이 누락될 수 있어 기본은 즐겨찾기만 감시하도록 False로 둔다.
NOTIFY_ALL_PROJECTS = False

# ─────────────────────────────────────────────
# 전사 레드마인 프로젝트 목록 자동 조회
#   1) 레드마인 내 계정 > 개인 설정 페이지에서 API 키 발급
#   2) redmine_api_key.txt 파일을 열어 키 값만 붙여넣고 저장
#      (이 파일은 이 PC에만 저장되며 대화창에는 입력하지 않는 것을 권장)
# ─────────────────────────────────────────────
REDMINE_BASE_URL = "http://10.1.100.150/redmine"
REDMINE_API_KEY_FILE = Path(__file__).parent / "redmine_api_key.txt"
REDMINE_API_KEY_PLACEHOLDER = "PUT_YOUR_API_KEY_HERE"

# 팀 레드마인 (전사 레드마인과 별도 서버, 자체 API 키 사용)
TEAM_REDMINE_BASE_URL = "http://10.1.100.20"
TEAM_REDMINE_API_KEY_FILE = Path(__file__).parent / "team_redmine_api_key.txt"

# "내 일감" 목록 조회에 쓸 레드마인 사용자 ID(숫자)가 저장되는 파일 (앱을 다시 실행해도 유지됨)
REDMINE_USER_ID_FILE = Path(__file__).parent / "redmine_user_id.txt"


def load_app_font():
    """FONT_FILE(NotoSansKR-Regular.ttf)을 설치 없이 이 프로세스 전용으로 등록하고,
    실제로 쓸 수 있게 됐는지 확인한 뒤 폰트 패밀리명을 전역 FONT_FAMILY에 반영한다.
    (Windows 전용 API를 쓰므로, 실패하면 조용히 기존 시스템 폰트를 그대로 쓴다)
    Tk 루트 윈도우가 만들어진 뒤(폰트 목록 조회가 가능한 시점)에 호출해야 한다."""
    global FONT_FAMILY
    if not FONT_FILE.exists():
        return
    try:
        FR_PRIVATE = 0x10
        added = ctypes.windll.gdi32.AddFontResourceExW(str(FONT_FILE), FR_PRIVATE, 0)
        if not added:
            return
        available = {f.lower() for f in tkfont.families()}
        if FONT_FILE_FAMILY.lower() in available:
            FONT_FAMILY = FONT_FILE_FAMILY
    except (AttributeError, OSError):
        pass  # Windows가 아니거나 GDI 호출이 불가능한 환경 → 기본 폰트 유지
