"""
회사용 데스크톱 비서 위젯 (초안)
--------------------------------
- 화면 좌측 하단에 항상 위에 떠 있는 작은 아이콘 버튼을 표시
- 아이콘을 누르면 위쪽으로 링크 뱃지 패널이 펼쳐짐
- 각 뱃지를 누르면 기본 브라우저로 해당 링크가 열림
- 다시 아이콘을 누르거나 바깥을 클릭하면 패널이 닫힘

필요 라이브러리: 파이썬 표준 라이브러리만 사용 (tkinter, webbrowser)
실행: python assistant_widget.py
"""

import ctypes
import json
import queue
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import webbrowser


def open_url(url):
    """BROWSER가 지정돼 있으면 해당 브라우저로, 아니면 시스템 기본 브라우저로 연다."""
    if BROWSER:
        try:
            webbrowser.get(f'"{BROWSER}" %s').open(url)
            return
        except Exception:
            pass  # 지정 브라우저 실행 실패 시 기본 브라우저로 폴백
    webbrowser.open(url)

# ─────────────────────────────────────────────
# 1. 여기만 수정하면 됩니다 : 뱃지에 표시할 링크 목록
#    (표시이름, URL, 이모지 아이콘)
# ─────────────────────────────────────────────
LINKS = [
    ("전사 레드마인",    "http://10.1.100.150/redmine/issues", "🏢"),
    ("팀 레드마인",      "http://10.1.100.20/projects",  "👥"),
    ("TMS (Cybertel)",  "http://10.1.100.80/main",              "🖥️"),
]

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
BADGE_H      = 42         # 뱃지 높이(px)
SUB_BADGE_H  = 38         # 플라이아웃(하위 프로젝트) 뱃지 높이(px)
SHADOW_COLOR = "#061431"  # 카드 아래에 깔리는 그림자색 (어두운 배경이라 더 어둡게)
SHADOW_OFFSET = 3         # 그림자 오프셋(px)
PANEL_BG    = ICON_BUTTON_BG   # 패널 배경색 - 메인 아이콘과 같은 남색
PANEL_W     = 220         # 메인 패널 너비(px)
FLYOUT_W    = 200         # 플라이아웃 패널 너비(px)
MY_ISSUES_FLYOUT_W = 460  # "내 일감" 플라이아웃 너비(px) - 이슈 제목이 길어서 더 넓게
PANEL_GAP   = 6           # 패널/플라이아웃 사이 가로 간격(px)
GO_ZONE_W   = 26          # 하위 항목이 있는 뱃지 오른쪽 끝의 "바로 이동" 버튼 클릭 영역 너비(px)
GO_ICON_SIZE = 16         # "바로 이동" 버튼 아이콘 크기(px)
GO_ICON_FILE = Path(__file__).parent / "assets" / "icons" / "go.png"
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

# 우클릭 메뉴로 추가한 링크가 저장되는 파일 (앱을 다시 실행해도 유지됨)
CUSTOM_LINKS_FILE = Path(__file__).parent / "custom_links.json"

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

# "내 일감" 목록 조회에 쓸 레드마인 사용자 ID(숫자)가 저장되는 파일 (앱을 다시 실행해도 유지됨)
REDMINE_USER_ID_FILE = Path(__file__).parent / "redmine_user_id.txt"


def load_redmine_api_key():
    if not REDMINE_API_KEY_FILE.exists():
        return None
    key = REDMINE_API_KEY_FILE.read_text(encoding="utf-8").strip()
    if not key or key == REDMINE_API_KEY_PLACEHOLDER:
        return None
    return key


def load_redmine_user_id():
    if not REDMINE_USER_ID_FILE.exists():
        return None
    value = REDMINE_USER_ID_FILE.read_text(encoding="utf-8").strip()
    return value or None


def save_redmine_user_id(value):
    REDMINE_USER_ID_FILE.write_text(value, encoding="utf-8")


def fetch_redmine_projects():
    """레드마인 REST API로 프로젝트 목록(평면 리스트, parent_id 포함)을 가져온다.
    실패/미설정 시 빈 리스트를 반환."""
    api_key = load_redmine_api_key()
    if not api_key:
        return []

    projects = []
    offset = 0
    limit = 100
    while True:
        url = f"{REDMINE_BASE_URL}/projects.json?limit={limit}&offset={offset}"
        req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError):
            break

        batch = data.get("projects", [])
        for p in batch:
            parent = p.get("parent")
            projects.append({
                "id": p.get("id"),
                "parent_id": parent.get("id") if parent else None,
                "name": p.get("name", ""),
                "url": f"{REDMINE_BASE_URL}/projects/{p.get('identifier', '')}/issues",
            })

        offset += limit
        if not batch or offset >= data.get("total_count", 0):
            break

    return projects


def fetch_recent_issues(project_id):
    """레드마인 REST API로 특정 프로젝트의 최근 이슈 목록(id, 제목, url)을 가져온다.
    실패/미설정 시 None을 반환(빈 목록과 구분해 이번 회차는 건너뛰기 위함)."""
    api_key = load_redmine_api_key()
    if not api_key:
        return None

    url = (
        f"{REDMINE_BASE_URL}/issues.json"
        f"?project_id={project_id}&status_id=*&sort=created_on:desc&limit=25"
    )
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    return [
        {
            "id": i.get("id"),
            "subject": i.get("subject", ""),
            "url": f"{REDMINE_BASE_URL}/issues/{i.get('id')}",
        }
        for i in data.get("issues", [])
    ]


def fetch_current_user_id():
    """API 키로 인증된 "나" 자신의 레드마인 사용자 ID를 조회한다.
    (/my/account 처럼 URL에 숫자 ID가 안 보이는 경우에도, API 키만으로 알아낼 수 있다)
    실패/미설정 시 None을 반환."""
    api_key = load_redmine_api_key()
    if not api_key:
        return None

    url = f"{REDMINE_BASE_URL}/users/current.json"
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    user_id = data.get("user", {}).get("id")
    return str(user_id) if user_id is not None else None


def resolve_user_id(identifier):
    """identifier가 이미 숫자(사용자 ID)면 그대로 반환하고, 로그인 아이디(문자)면
    레드마인 사용자 검색 API로 실제 로그인이 일치하는 사용자를 찾아 숫자 ID로 변환한다.
    (레드마인 설정에 따라 일반 계정은 사용자 검색 권한이 없을 수도 있다) 실패 시 None."""
    identifier = identifier.strip()
    if identifier.isdigit():
        return identifier

    api_key = load_redmine_api_key()
    if not api_key:
        return None

    url = f"{REDMINE_BASE_URL}/users.json?name={urllib.parse.quote(identifier)}&limit=25"
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    users = data.get("users", [])
    for u in users:
        if u.get("login") == identifier:
            return str(u.get("id"))
    if len(users) == 1:
        return str(users[0].get("id"))
    return None


def fetch_my_issues(identifier):
    """레드마인 REST API로 identifier(로그인 아이디 또는 숫자 ID)에게 할당된
    이슈 목록(열림/닫힘 모두, 업데이트 최신순)을 가져온다. 열린 것만 따로 구분하지
    않는 이유는, 목록 위 검색창에서 완료된 이슈까지 같이 검색되게 하기 위함이다.
    identifier가 없으면(아직 설정 전) 빈 리스트를 반환."""
    if not identifier:
        return []
    api_key = load_redmine_api_key()
    if not api_key:
        return []

    user_id = resolve_user_id(identifier)
    if not user_id:
        return []

    url = (
        f"{REDMINE_BASE_URL}/issues.json"
        f"?assigned_to_id={user_id}&status_id=*&sort=updated_on:desc&limit=100"
    )
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return []

    issues = []
    for i in data.get("issues", []):
        project_name = i.get("project", {}).get("name", "")
        subject = i.get("subject", "")
        issue_id = i.get("id")
        title = f"[{project_name}] {subject}" if project_name else subject
        issues.append({
            "issue_id": issue_id,
            "title": title,
            "url": f"{REDMINE_BASE_URL}/issues/{issue_id}",
        })
    return issues


def fetch_project_issue_list(project_id):
    """레드마인 REST API로 특정 프로젝트의 이슈 목록(열림/닫힘 모두, 업데이트 최신순)을
    가져온다. 열린 것만 따로 구분하지 않는 이유는, 목록 위 검색창에서 닫힌 이슈까지
    같이 검색되게 하기 위함이다. 실패/미설정 시 빈 리스트를 반환."""
    api_key = load_redmine_api_key()
    if not api_key:
        return []

    url = (
        f"{REDMINE_BASE_URL}/issues.json"
        f"?project_id={project_id}&status_id=*&sort=updated_on:desc&limit=200"
    )
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return []

    return [
        {
            "issue_id": i.get("id"),
            "title": i.get("subject", ""),
            "url": f"{REDMINE_BASE_URL}/issues/{i.get('id')}",
        }
        for i in data.get("issues", [])
    ]


def search_project_issues(project_id, query):
    """레드마인 자체 검색(/projects/:id/search.json)으로 해당 프로젝트의 이슈를
    제목뿐 아니라 본문·댓글까지 포함해서 검색한다(레드마인 웹 검색과 동일한 결과 범위).
    실패 시 None을 반환(빈 결과와 구분해 이번 검색은 건너뛰기 위함)."""
    api_key = load_redmine_api_key()
    if not api_key or not query:
        return None

    url = (
        f"{REDMINE_BASE_URL}/projects/{project_id}/search.json"
        f"?q={urllib.parse.quote(query)}&issues=1&limit=100"
    )
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    results = []
    for r in data.get("results", []):
        if r.get("type") != "issue":
            continue
        match = re.search(r"/issues/(\d+)", r.get("url", ""))
        if not match:
            continue
        # 레드마인 검색 결과 제목은 보통 "버그 #1234: 제목"처럼 앞에 트래커/번호가
        # 붙어오는데, 우리 쪽엔 id 뱃지가 이미 있으므로 그 부분은 잘라낸다.
        title = re.sub(r"^.*?#\d+:\s*", "", r.get("title", ""))
        results.append({
            "issue_id": int(match.group(1)),
            "title": title,
            "url": f"{REDMINE_BASE_URL}/issues/{match.group(1)}",
        })
    return results


def build_project_tree(projects):
    """평면 프로젝트 리스트를 parent_id 기준으로 최상위→하위 트리로 묶는다.
    각 레벨은 이름 기준 내림차순으로 정렬한다."""
    by_parent = {}
    for p in projects:
        by_parent.setdefault(p["parent_id"], []).append(p)

    def attach(node):
        node["children"] = sorted(
            by_parent.get(node["id"], []), key=lambda n: n["name"], reverse=True
        )
        for child in node["children"]:
            attach(child)
        return node

    roots = sorted(by_parent.get(None, []), key=lambda n: n["name"], reverse=True)
    return [attach(root) for root in roots]


def load_custom_links():
    if not CUSTOM_LINKS_FILE.exists():
        return []
    try:
        with open(CUSTOM_LINKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_custom_links(custom_links):
    with open(CUSTOM_LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(custom_links, f, ensure_ascii=False, indent=2)


def load_favorites():
    if not FAVORITES_FILE.exists():
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_favorites(favorites):
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)


def load_seen_issues():
    """{프로젝트id(str): [이슈id, ...]} 형태로 이미 알림을 보낸 이슈 id들을 불러온다."""
    if not SEEN_ISSUES_FILE.exists():
        return {}
    try:
        with open(SEEN_ISSUES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen_issues(seen_issue_ids):
    with open(SEEN_ISSUES_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_issue_ids, f, ensure_ascii=False, indent=2)


def load_toast_icon():
    """새 이슈 알림 토스트에 쓸 알람 아이콘을 흰색 실루엣으로 TOAST_ICON_SIZE만큼 불러온다.
    (포인트 컬러 배지 위에 올릴 것이므로 원래 색과 상관없이 흰색으로 통일한다)"""
    return load_icon_glyph(TOAST_ICON_FILE, TOAST_ICON_SIZE, "#FFFFFF")


def load_go_icon():
    """뱃지의 "바로 이동" 화살표 아이콘을 GO_ICON_SIZE로 불러온다. 원본은 검정 원
    배경 위에 흰 화살표인데, 어두운 카드 위에서 검정 원이 안 보이므로 원(어두운
    픽셀)만 포인트 컬러로 바꾸고 화살표(밝은 픽셀)는 흰색 그대로 살린다."""
    try:
        from PIL import Image, ImageTk
        img = Image.open(GO_ICON_FILE).convert("RGBA")
        r, g, b = tuple(int(BG_COLOR[i:i + 2], 16) for i in (1, 3, 5))
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                pr, pg, pb, pa = px[x, y]
                if pa == 0:
                    continue
                if (pr + pg + pb) / 3 < 128:
                    px[x, y] = (r, g, b, pa)  # 어두운(원) 픽셀 → 포인트 컬러
                else:
                    px[x, y] = (255, 255, 255, pa)  # 밝은(화살표) 픽셀 → 흰색
        img = img.resize((GO_ICON_SIZE, GO_ICON_SIZE), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except ImportError:
        return tk.PhotoImage(file=str(GO_ICON_FILE))


def load_icon_glyph(path, size, color):
    """아이콘 이미지를 원래 색과 상관없이 color 단색 실루엣으로 만들어 size로 불러온다.
    (원본의 알파 채널을 마스크로 써서 모양만 남기고 전부 color로 칠한다)"""
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGBA")
        alpha = img.split()[3]
        r, g, b = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        solid = Image.new("RGBA", img.size, (r, g, b, 0))
        solid.putalpha(alpha)
        solid = solid.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(solid)
    except ImportError:
        return tk.PhotoImage(file=str(path))


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


def draw_rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """캔버스에 둥근 모서리 사각형(뱃지 모양)을 그린다."""
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def draw_card(canvas, w, h, radius, fill, tags="badge"):
    """캔버스(w×h) 안에 부드러운 그림자가 깔린 둥근 카드를 그린다.
    카드가 그림자만큼 살짝 안쪽으로 들어가므로, 텍스트/아이콘을 배치할
    카드 중심 좌표 (cx, cy)를 반환한다."""
    cx2, cy2 = w - 1 - SHADOW_OFFSET, h - 1 - SHADOW_OFFSET
    draw_rounded_rect(
        canvas, SHADOW_OFFSET, SHADOW_OFFSET, w - 1, h - 1, radius,
        fill=SHADOW_COLOR, outline="", tags=tags,
    )
    draw_rounded_rect(
        canvas, 0, 0, cx2, cy2, radius,
        fill=fill, outline="", tags=tags,
    )
    return cx2 / 2, cy2 / 2


def truncate_text(font_obj, text, max_width):
    """max_width(px) 안에 들어가도록 text를 말줄임표(…)로 잘라 반환한다.
    max_width가 충분하면 원본 그대로 반환한다."""
    if max_width <= 0:
        return "…"
    if font_obj.measure(text) <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font_obj.measure(text[:mid] + "…") <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + "…") if lo > 0 else "…"


def wrap_text_two_lines(font_obj, text, first_width, rest_width=None):
    """text를 최대 2줄로 줄바꿈한다. 첫 줄은 first_width(px), 둘째 줄은 rest_width(px)
    안에 들어가야 하며, rest_width를 생략하면 첫 줄과 같은 너비를 쓴다.
    (첫 줄 앞에 id 뱃지 등이 붙어 첫 줄만 폭이 좁은 경우에 쓴다)
    2줄에도 다 안 들어가면 2번째 줄 끝을 말줄임표(…)로 자른다."""
    if rest_width is None:
        rest_width = first_width
    if font_obj.measure(text) <= first_width:
        return [text]

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font_obj.measure(text[:mid]) <= first_width:
            lo = mid
        else:
            hi = mid - 1
    line1 = text[:lo] if lo > 0 else text[:1]
    rest = text[len(line1):]

    if font_obj.measure(rest) <= rest_width:
        return [line1, rest]
    return [line1, truncate_text(font_obj, rest, rest_width)]


def issue_row_height(font_obj):
    """이슈 id 뱃지 + 제목(최대 2줄, 뱃지 옆에 이어서 표시)을 담는 뱃지의 전체 높이(px)를 계산한다."""
    line_h = font_obj.metrics("linespace")
    row1_h = max(ISSUE_BADGE_H, line_h)
    return ISSUE_ROW_PAD_Y + row1_h + ISSUE_LINE_GAP + line_h + ISSUE_ROW_PAD_Y


class AssistantWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # 메인 윈도우는 숨김
        load_app_font()  # Pretendard 폰트 등록 (실패 시 기본 한글 폰트로 자동 대체)

        # 화면 크기 파악 (좌측 하단 좌표 계산용)
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        self.panel = None      # 뱃지 패널 (열려 있을 때만 존재)
        self.panel_open = False
        self.flyouts = []       # 레드마인 하위 프로젝트 플라이아웃 스택 (depth 순서, 열려 있을 때만 존재)
        self.active_main_badge = None    # 메인 패널에서 현재 펼쳐져 있는(depth 0을 연) 뱃지의 (canvas, render)
        self.active_flyout_badge = {}    # depth -> 그 플라이아웃에서 현재 펼쳐져 있는(depth+1을 연) 뱃지의 (canvas, render)

        self.custom_links = load_custom_links()  # 우클릭으로 추가한 링크 (영구 저장됨)
        self.favorites = load_favorites()  # 레드마인 프로젝트 뱃지를 우클릭해 즐겨찾기한 목록 (영구 저장됨)
        self.favorite_issues = {}  # 즐겨찾기 프로젝트id(str) -> 그 프로젝트의 열려있는 이슈 목록 (백그라운드로 채워짐)
        self._favorite_issues_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달
        self.redmine_tree = []  # 전사 레드마인 최상위 프로젝트 트리 (children에 하위 프로젝트, 백그라운드로 채워짐)
        self._redmine_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달

        self.redmine_user_id = load_redmine_user_id()  # "내 일감" 조회에 쓸 레드마인 사용자 ID (영구 저장됨)
        self.my_issues = []  # 내게 할당된 이슈 목록 (백그라운드로 채워짐)
        self._my_issues_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달

        self.seen_issue_ids = load_seen_issues()  # 즐겨찾기 프로젝트별로 이미 알림을 보낸 이슈 id (영구 저장됨)
        self._notify_queue = queue.Queue()  # 이슈 조회 백그라운드 스레드 → 메인 스레드로 결과 전달
        self._notify_worker_running = False  # 이전 조회가 안 끝났는데 새로 겹쳐 시작하지 않기 위한 플래그
        self.toasts = []  # 화면에 떠 있는 새 이슈 알림 토스트 목록
        self.toast_icon = load_toast_icon()  # 참조 유지(GC 방지)
        self.go_icon = load_go_icon()  # 뱃지 "바로 이동" 버튼 아이콘, 참조 유지(GC 방지)

        self._build_icon()
        self._poll_redmine_queue()
        self.refresh_redmine_projects()
        self._poll_my_issues_queue()
        self.refresh_my_issues()
        self._poll_favorite_issues_queue()
        self.refresh_favorite_project_issues()
        self._poll_notify_queue()
        self._notify_tick()

    # ── 즐겨찾기 + 기본 링크 + 사용자 추가 링크를 합친 전체 목록 ──
    #    "전사 레드마인"에는 레드마인 최상위 프로젝트 트리가, "⭐ 즐겨찾기"에는
    #    즐겨찾기한 프로젝트 목록이 children으로 붙어서, 클릭하면 오른쪽 플라이아웃으로 펼쳐진다.
    def _all_links(self):
        links = []
        my_issue_nodes = [
            {
                "name": issue["title"], "url": issue["url"], "children": None,
                "issue_id": issue["issue_id"],
            }
            for issue in self.my_issues
        ]
        links.append({
            "name": "📋 내 일감", "url": f"{REDMINE_BASE_URL}/my/page", "children": my_issue_nodes,
            "my_issues": True, "flyout_width": MY_ISSUES_FLYOUT_W, "count": len(self.my_issues),
        })
        if self.favorites:
            favorite_nodes = [
                {
                    "name": f["name"], "url": f["url"], "id": f["id"],
                    "children": [
                        {"name": issue["title"], "url": issue["url"], "issue_id": issue["issue_id"]}
                        for issue in self.favorite_issues.get(str(f["id"]), [])
                    ],
                }
                for f in self.favorites
            ]
            links.append({"name": "⭐ 즐겨찾기", "url": None, "children": favorite_nodes})
        for name, url, _emoji in LINKS:
            children = self.redmine_tree if name == "전사 레드마인" else None
            links.append({"name": name, "url": url, "children": children})
        links += [
            {"name": item["name"], "url": item["url"], "children": None, "removable": True}
            for item in self.custom_links
        ]
        return links

    # ── 레드마인 프로젝트 목록 백그라운드 조회 ──
    #    (tkinter는 다른 스레드에서 직접 건드릴 수 없으므로 Queue로 결과만 전달받는다)
    def refresh_redmine_projects(self):
        def worker():
            tree = build_project_tree(fetch_redmine_projects())
            self._redmine_queue.put(tree)

        threading.Thread(target=worker, daemon=True).start()

    def _poll_redmine_queue(self):
        try:
            tree = self._redmine_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.redmine_tree = tree
            if self.panel_open:
                self.close_panel()
                self.open_panel()
        self.root.after(500, self._poll_redmine_queue)

    # ── 내게 할당된 이슈 목록 백그라운드 조회 ──
    def refresh_my_issues(self):
        known_user_id = self.redmine_user_id

        def worker():
            # 저장된 사용자 ID가 없으면, API 키만으로 "나"의 ID를 자동으로 알아낸다.
            user_id = known_user_id or fetch_current_user_id()
            issues = fetch_my_issues(user_id) if user_id else []
            self._my_issues_queue.put((user_id, issues))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_my_issues_queue(self):
        try:
            user_id, issues = self._my_issues_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            # 그 사이 사용자가 직접 ID를 입력/변경했을 수 있으므로, 아직 비어있을 때만
            # 자동으로 알아낸 ID를 채워 넣는다(수동 입력값을 되돌리지 않기 위함).
            if user_id and not self.redmine_user_id:
                self.redmine_user_id = user_id
                save_redmine_user_id(user_id)
            self.my_issues = issues
            if self.panel_open:
                self.close_panel()
                self.open_panel()
        self.root.after(500, self._poll_my_issues_queue)

    # ── 즐겨찾기한 프로젝트별 이슈 목록 백그라운드 조회 ──
    #    ("⭐ 즐겨찾기" 플라이아웃에서 프로젝트를 클릭하면 그 프로젝트의 이슈 목록이 펼쳐진다)
    def refresh_favorite_project_issues(self):
        favorites_snapshot = list(self.favorites)
        if not favorites_snapshot:
            return

        def worker():
            result = {}
            for fav in favorites_snapshot:
                result[str(fav["id"])] = fetch_project_issue_list(fav["id"])
            self._favorite_issues_queue.put(result)

        threading.Thread(target=worker, daemon=True).start()

    def _poll_favorite_issues_queue(self):
        try:
            result = self._favorite_issues_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.favorite_issues.update(result)
            if self.panel_open:
                self.close_panel()
                self.open_panel()
        self.root.after(500, self._poll_favorite_issues_queue)

    # ── 새 이슈 알림 ──────────────────────────
    #    (tkinter는 다른 스레드에서 직접 건드릴 수 없으므로 Queue로 결과만 전달받는다)
    def _notify_tick(self):
        self.refresh_favorite_issues()
        self.refresh_favorite_project_issues()
        self.root.after(NOTIFY_POLL_INTERVAL_MS, self._notify_tick)

    def _flatten_projects(self, nodes):
        """레드마인 프로젝트 트리(children 포함)를 평면 리스트로 펼친다."""
        flat = []
        for node in nodes:
            flat.append(node)
            flat.extend(self._flatten_projects(node.get("children") or []))
        return flat

    def refresh_favorite_issues(self):
        if NOTIFY_ALL_PROJECTS:
            # 즐겨찾기 여부와 상관없이 전사 레드마인 전체 프로젝트를 감시한다.
            # (프로젝트가 많으면 한 주기 안에 다 못 돌 수 있으니 기본은 꺼져있다)
            watch_list = self._flatten_projects(self.redmine_tree)
        else:
            watch_list = list(self.favorites)
        if not watch_list:
            return
        if self._notify_worker_running:
            # 이전 조회가 아직 안 끝났으면 겹쳐서 새로 시작하지 않는다.
            # (프로젝트가 많아 한 주기(1분) 안에 다 못 도는 경우, 요청이 계속 쌓이는 것을 방지)
            return
        self._notify_worker_running = True

        def worker():
            try:
                new_issues = []  # [(project_name, issue), ...]
                updated = {}
                for project in watch_list:
                    issues = fetch_recent_issues(project["id"])
                    if issues is None:
                        continue  # 조회 실패 → 이번 회차는 건너뛰고 기존 기록 유지
                    key = str(project["id"])
                    known = self.seen_issue_ids.get(key)
                    if known is not None:
                        known_ids = set(known)
                        for issue in issues:
                            if issue["id"] not in known_ids:
                                new_issues.append((project["name"], issue))
                    # 처음 감시하는 프로젝트는 알림 없이 현재 이슈들만 "확인함"으로 기록
                    updated[key] = [issue["id"] for issue in issues]
                self._notify_queue.put((new_issues, updated))
            finally:
                self._notify_worker_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _poll_notify_queue(self):
        try:
            new_issues, updated = self._notify_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.seen_issue_ids.update(updated)
            save_seen_issues(self.seen_issue_ids)
            for project_name, issue in new_issues:
                self.show_issue_toast(project_name, issue)
        self.root.after(500, self._poll_notify_queue)

    # ── 새 이슈 알림 토스트 (화면 우측 아래부터 위로 쌓임) ──
    def show_issue_toast(self, project_name, issue):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=PANEL_BG)

        canvas = tk.Canvas(
            toast, width=TOAST_W, height=TOAST_H,
            bg=PANEL_BG, highlightthickness=0, cursor="hand2",
        )
        canvas.pack()
        draw_card(canvas, TOAST_W, TOAST_H, BADGE_RADIUS, BADGE_BG)
        card_h = TOAST_H - SHADOW_OFFSET

        icon_x = 14
        text_x = icon_x + TOAST_CHIP_SIZE + 10
        chip_cy = card_h / 2
        draw_rounded_rect(
            canvas, icon_x, chip_cy - TOAST_CHIP_SIZE / 2,
            icon_x + TOAST_CHIP_SIZE, chip_cy + TOAST_CHIP_SIZE / 2,
            TOAST_CHIP_RADIUS, fill=BG_COLOR, outline="",
        )
        canvas.create_image(icon_x + TOAST_CHIP_SIZE / 2, chip_cy, image=self.toast_icon)

        canvas.create_text(
            text_x, 20, anchor="w", text=f"{project_name}  새 이슈",
            fill=BG_COLOR, font=(FONT_FAMILY, 9, "bold"),
        )
        subject = issue["subject"]
        if len(subject) > 20:
            subject = subject[:19] + "…"
        canvas.create_text(
            text_x, 44, anchor="w", text=subject,
            fill=BADGE_FG, font=(FONT_FAMILY, 10, "bold"),
        )

        def dismiss():
            if toast in self.toasts:
                self.toasts.remove(toast)
            toast.destroy()
            self._reflow_toasts()

        def open_and_dismiss(_e=None):
            open_url(issue["url"])
            dismiss()

        canvas.bind("<Button-1>", open_and_dismiss)
        self.toasts.append(toast)
        self._reflow_toasts()
        toast.after(TOAST_DURATION_MS, dismiss)

    def _reflow_toasts(self):
        """토스트들을 메인 아이콘 바로 오른쪽에, 아래에서 위로 쌓아 배치한다."""
        x = self.icon_x + ICON_SIZE + 12
        base_y = self.icon_y + ICON_SIZE  # 아이콘 아래쪽 기준선에 맞춤
        for idx, toast in enumerate(self.toasts):
            y = base_y - (idx + 1) * (TOAST_H + TOAST_GAP)
            toast.geometry(f"{TOAST_W}x{TOAST_H}+{x}+{y}")

    # ── 좌측 하단 아이콘 버튼 ──────────────────
    #    남색 둥근 네모 배경 위에 흰색 실루엣 아이콘을 그린다.
    def _build_icon(self):
        self.icon = tk.Toplevel(self.root)
        self.icon.overrideredirect(True)          # 타이틀바 제거
        self.icon.attributes("-topmost", True)    # 항상 위
        # 작업표시줄 높이를 대략 감안해 살짝 위로
        x = MARGIN
        y = self.sh - ICON_SIZE - MARGIN - 40
        self.icon.geometry(f"{ICON_SIZE}x{ICON_SIZE}+{x}+{y}")
        self.icon.configure(bg=ICON_KEY_COLOR)
        self.icon.attributes("-transparentcolor", ICON_KEY_COLOR)  # 둥근 모서리 바깥을 창에서 완전히 투명 처리 (Windows 전용)

        self.icon_glyph = load_icon_glyph(ICON_IMAGE, ICON_SIZE - ICON_GLYPH_PAD * 2, ICON_BUTTON_FG)  # 참조 유지(GC 방지)
        btn = tk.Canvas(
            self.icon, width=ICON_SIZE, height=ICON_SIZE,
            bg=ICON_KEY_COLOR, highlightthickness=0, cursor="hand2",
        )
        btn.pack(expand=True, fill="both")
        draw_rounded_rect(
            btn, 0, 0, ICON_SIZE - 1, ICON_SIZE - 1, ICON_RADIUS,
            fill=ICON_BUTTON_BG, outline="",
        )
        btn.create_image(ICON_SIZE / 2, ICON_SIZE / 2, image=self.icon_glyph)
        btn.bind("<Button-1>", lambda e: self.toggle_panel())
        btn.bind("<Button-3>", self.show_context_menu)

        # 아이콘 위치 기억 (패널 위치 계산에 사용)
        self.icon_x = x
        self.icon_y = y

    # ── 아이콘 우클릭 메뉴 ─────────────────────
    def show_context_menu(self, event):
        menu = tk.Menu(self.icon, tearoff=0)
        menu.add_command(label="링크 추가", command=self.open_add_link_dialog)
        menu.add_command(label="레드마인 프로젝트 새로고침", command=self.refresh_redmine_projects)
        menu.add_command(label="내 일감 새로고침", command=self.refresh_my_issues)
        menu.tk_popup(event.x_root, event.y_root)

    # ── 링크 추가 다이얼로그 ───────────────────
    def open_add_link_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("링크 추가")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.configure(bg=PANEL_BG)

        pad = {"padx": 12, "pady": (10, 0)}

        tk.Label(dialog, text="이름", bg=PANEL_BG, fg=BADGE_FG,
                 font=(FONT_FAMILY, 9), anchor="w").pack(fill="x", **pad)
        name_entry = tk.Entry(dialog, font=(FONT_FAMILY, 10))
        name_entry.pack(fill="x", padx=12, pady=(2, 0))

        tk.Label(dialog, text="URL", bg=PANEL_BG, fg=BADGE_FG,
                 font=(FONT_FAMILY, 9), anchor="w").pack(fill="x", **pad)
        url_entry = tk.Entry(dialog, font=(FONT_FAMILY, 10))
        url_entry.pack(fill="x", padx=12, pady=(2, 0))

        def submit():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            if not name or not url:
                messagebox.showwarning("입력 필요", "이름과 URL을 모두 입력해 주세요.", parent=dialog)
                return
            self.add_link(name, url)
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg=PANEL_BG)
        btn_row.pack(fill="x", padx=12, pady=12)
        tk.Button(btn_row, text="추가", command=submit).pack(side="right")
        tk.Button(btn_row, text="취소", command=dialog.destroy).pack(side="right", padx=(0, 6))

        name_entry.focus_set()
        dialog.bind("<Return>", lambda e: submit())

        # 아이콘 근처에 다이얼로그 배치
        dialog.geometry(f"+{self.icon_x}+{max(self.icon_y - 140, 0)}")

    def add_link(self, name, url):
        self.custom_links.append({"name": name, "url": url})
        save_custom_links(self.custom_links)
        if self.panel_open:
            self.close_panel()
            self.open_panel()

    # ── "내 일감" 조회용 레드마인 사용자 ID 설정 다이얼로그 ──
    def open_set_user_id_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("내 일감 - 로그인 아이디 설정")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.configure(bg=PANEL_BG)

        pad = {"padx": 12, "pady": (10, 0)}

        tk.Label(
            dialog,
            text="보통은 API 키만으로 자동으로 알아내지만, 실패했거나 다른 사람의\n"
                 "일감을 보고 싶다면 레드마인 로그인 아이디(계정)를 직접 입력하세요.\n"
                 "(숫자로 된 사용자 ID를 알고 있다면 그것도 입력 가능합니다)",
            bg=PANEL_BG, fg=BADGE_FG, font=(FONT_FAMILY, 9), justify="left", anchor="w",
        ).pack(fill="x", **pad)
        id_entry = tk.Entry(dialog, font=(FONT_FAMILY, 10))
        id_entry.pack(fill="x", padx=12, pady=(6, 0))
        if self.redmine_user_id:
            id_entry.insert(0, self.redmine_user_id)

        def submit():
            value = id_entry.get().strip()
            if not value:
                messagebox.showwarning("입력 필요", "로그인 아이디를 입력해 주세요.", parent=dialog)
                return
            self.redmine_user_id = value
            save_redmine_user_id(value)
            self.refresh_my_issues()
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg=PANEL_BG)
        btn_row.pack(fill="x", padx=12, pady=12)
        tk.Button(btn_row, text="저장", command=submit).pack(side="right")
        tk.Button(btn_row, text="취소", command=dialog.destroy).pack(side="right", padx=(0, 6))

        id_entry.focus_set()
        dialog.bind("<Return>", lambda e: submit())

        # 아이콘 근처에 다이얼로그 배치
        dialog.geometry(f"+{self.icon_x}+{max(self.icon_y - 160, 0)}")

    # ── 패널 열기 / 닫기 ──────────────────────
    def toggle_panel(self):
        if self.panel_open:
            self.close_panel()
        else:
            self.open_panel()

    def open_panel(self):
        self.panel = tk.Toplevel(self.root)
        self.panel.overrideredirect(True)
        self.panel.attributes("-topmost", True)
        self.panel.configure(bg=PANEL_BG)

        links = self._all_links()
        pad = 12  # 뱃지 안쪽 텍스트 여백(12px)과 맞춰서, 패널 바깥 여백도 위/아래/좌/우 전부 12px로 통일

        title = tk.Label(
            self.panel, text="바로가기", bg=PANEL_BG, fg=BADGE_FG_MUTED,
            font=(FONT_FAMILY, 9, "bold"), anchor="w",
        )
        title.pack(fill="x", padx=pad, pady=(pad, 4))

        badge_w = PANEL_W - pad * 2
        for entry in links:
            self._make_badge(entry, badge_w, pad)

        # 타이틀 + 뱃지들이 실제로 차지하는 높이에 맞춰 창 크기를 정한다.
        # (직접 계산한 높이를 쓰면 폰트/여백 차이로 맨 아래 카드가 잘릴 수 있음)
        self.panel.update_idletasks()
        panel_h = self.panel.winfo_reqheight() + pad

        # 아이콘 바로 위에 패널 배치 (아래쪽 기준선에 맞춰 위로 쌓임)
        px = self.icon_x
        py = self.icon_y - panel_h - 8
        self.panel.geometry(f"{PANEL_W}x{panel_h}+{px}+{py}")

        self.panel_open = True

    def close_panel(self):
        self.close_all_flyouts()
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
        self.panel_open = False
        self.active_main_badge = None  # 패널이 통째로 사라지므로 canvas 참조도 함께 정리

    # ── 링크 뱃지 하나 만들기 (둥근 필 형태) ───
    #    entry["children"]가 있으면(=전사 레드마인) 클릭 시 오른쪽 플라이아웃으로 펼쳐짐
    def _make_badge(self, entry, badge_w, pad):
        name, url, children = entry["name"], entry["url"], entry["children"]
        has_children = children is not None
        has_go_button = has_children and bool(url)

        badge_font = (FONT_FAMILY, 10, "bold")
        font10 = tkfont.Font(family=FONT_FAMILY, size=10, weight="bold")
        suffix = "  ›" if has_children else ""
        count = entry.get("count")
        count_text = str(count) if count else None
        count_pill_w = (font10.measure(count_text) + ISSUE_BADGE_PAD_X * 2) if count_text else 0
        count_reserve = (count_pill_w + ISSUE_BADGE_GAP) if count_text else 0
        right_reserve = GO_ZONE_W if has_go_button else 12
        name_max_w = badge_w - 12 - right_reserve - count_reserve - font10.measure(suffix)
        text = truncate_text(font10, name, name_max_w) + suffix

        canvas = tk.Canvas(
            self.panel, width=badge_w, height=BADGE_H,
            bg=PANEL_BG, highlightthickness=0, cursor="hand2",
        )
        canvas.pack(padx=pad, pady=2)

        def render(bg, fg=BADGE_FG):
            canvas.delete("badge")
            _, cy = draw_card(canvas, badge_w, BADGE_H, BADGE_RADIUS, bg)
            canvas.create_text(
                12, cy, anchor="w", text=text, fill=fg,
                font=badge_font, tags="badge",
            )
            if count_text:
                # 개수 뱃지: 라벨 텍스트 바로 뒤에 포인트 컬러 알약으로 표시한다.
                pill_x = 12 + font10.measure(text) + ISSUE_BADGE_GAP
                pill_y1, pill_y2 = cy - ISSUE_BADGE_H / 2, cy + ISSUE_BADGE_H / 2
                draw_rounded_rect(
                    canvas, pill_x, pill_y1, pill_x + count_pill_w, pill_y2, ISSUE_BADGE_H / 2,
                    fill=BG_COLOR, outline="", tags="badge",
                )
                canvas.create_text(
                    pill_x + count_pill_w / 2, cy, text=count_text, fill="#FFFFFF",
                    font=badge_font, tags="badge",
                )
            if has_go_button:
                canvas.create_image(
                    badge_w - 1 - SHADOW_OFFSET - GO_ZONE_W / 2, cy,
                    image=self.go_icon, tags="badge",
                )

        def restore_idle():
            # 이 뱃지가 현재 펼쳐진(depth 0을 연) 상태라면 선택 표시를 유지한다.
            if self.active_main_badge and self.active_main_badge[0] is canvas:
                render(BADGE_SELECTED_BG, BADGE_SELECTED_FG)
            else:
                render(BADGE_BG)

        render(BADGE_BG)

        if has_children:
            def click(e):
                if has_go_button and e.x >= badge_w - GO_ZONE_W:
                    # 오른쪽 끝 "↗" 버튼: 하위 목록을 펼치지 않고 이 항목 자체 페이지로 바로 이동
                    self._open_and_close(url)
                    return
                if entry.get("my_issues") and not self.redmine_user_id:
                    # "내 일감"인데 아직 사용자 ID가 없으면, 목록을 펼치는 대신 먼저 입력받는다.
                    self.open_set_user_id_dialog()
                    return
                self.toggle_redmine_flyout(url, children, entry.get("flyout_width", FLYOUT_W))
                if self.flyouts:
                    # 새로 펼쳐짐 → 이 뱃지를 선택 표시하고, 이전에 선택돼 있던 다른 뱃지는 되돌린다.
                    prev = self.active_main_badge
                    if prev and prev[0] is not canvas and prev[0].winfo_exists():
                        prev[1](BADGE_BG)
                    self.active_main_badge = (canvas, render)
                    render(BADGE_SELECTED_BG, BADGE_SELECTED_FG)
                elif canvas.winfo_exists():
                    # 다시 클릭해서 닫혔거나(선택 해제), 프로젝트 목록이 없어 패널 자체가
                    # 닫혔을 수 있으므로(이 경우 canvas가 이미 사라졌으므로) 존재를 확인한다.
                    self.active_main_badge = None
                    render(BADGE_BG)
        else:
            click = lambda e: self._open_and_close(url)

        canvas.bind("<Button-1>", click)
        if entry.get("removable"):
            canvas.bind("<Button-3>", lambda e, nm=name: self.show_delete_link_menu(e, nm))
        elif entry.get("my_issues"):
            canvas.bind("<Button-3>", lambda e: self.open_set_user_id_dialog())
        canvas.bind("<Enter>", lambda e: render(BADGE_HOVER))
        canvas.bind("<Leave>", lambda e: restore_idle())

    def _open_and_close(self, url):
        open_url(url)
        self.close_panel()

    # ── 사용자 추가 링크 삭제 (뱃지 우클릭) ─────
    def show_delete_link_menu(self, event, name):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="삭제", command=lambda: self.remove_link(name))
        menu.tk_popup(event.x_root, event.y_root)

    def remove_link(self, name):
        self.custom_links = [item for item in self.custom_links if item["name"] != name]
        save_custom_links(self.custom_links)
        self.close_panel()

    # ── 즐겨찾기 (레드마인 프로젝트 뱃지 우클릭) ─────
    def is_favorite(self, project_id):
        return any(f["id"] == project_id for f in self.favorites)

    def toggle_favorite(self, node):
        project_id = node["id"]
        if self.is_favorite(project_id):
            self.favorites = [f for f in self.favorites if f["id"] != project_id]
            # 즐겨찾기 해제 시 해당 프로젝트의 "확인한 이슈" 기록/이슈 목록 캐시도 함께 정리
            if self.seen_issue_ids.pop(str(project_id), None) is not None:
                save_seen_issues(self.seen_issue_ids)
            self.favorite_issues.pop(str(project_id), None)
        else:
            self.favorites.append({"id": project_id, "name": node["name"], "url": node["url"]})
            self.refresh_favorite_project_issues()  # 새로 즐겨찾기된 프로젝트의 이슈 목록을 바로 조회
        save_favorites(self.favorites)
        self.close_panel()

    def show_favorite_menu(self, event, node):
        if node.get("id") is None:
            return
        menu = tk.Menu(self.root, tearoff=0)
        label = "즐겨찾기 제거" if self.is_favorite(node["id"]) else "즐겨찾기 추가"
        menu.add_command(label=label, command=lambda: self.toggle_favorite(node))
        menu.tk_popup(event.x_root, event.y_root)

    # ── 레드마인 프로젝트 플라이아웃 (최상위 → 하위로 depth별 오른쪽에 펼침) ──
    def toggle_redmine_flyout(self, fallback_url, top_level_nodes, width=FLYOUT_W):
        if self.flyouts:
            self.close_all_flyouts()
            return
        if not top_level_nodes:
            # 아직 못 불러왔거나 등록된 프로젝트가 없으면 기본 링크로 이동
            self._open_and_close(fallback_url)
            return
        self.open_flyout_level(0, top_level_nodes, width)

    def open_flyout_level(self, depth, nodes, width=FLYOUT_W, project_id=None):
        # 같은 depth를 다시 열 때는 그보다 깊은 플라이아웃부터 정리
        self.close_flyouts_from(depth)

        flyout = tk.Toplevel(self.root)
        flyout.overrideredirect(True)
        flyout.attributes("-topmost", True)
        flyout.configure(bg=PANEL_BG)

        pad = 12  # 뱃지 안쪽 텍스트 여백(12px)과 맞춰서, 플라이아웃 바깥 여백도 통일
        # 이슈 목록(아이디 뱃지 + 제목 2줄)은 일반 프로젝트 항목보다 뱃지가 더 높고, 검색창도 붙는다.
        is_issue_list = bool(nodes) and nodes[0].get("issue_id") is not None
        if is_issue_list:
            row_h = issue_row_height(tkfont.Font(family=FONT_FAMILY, size=9, weight="bold"))
        else:
            row_h = SUB_BADGE_H
        item_h = row_h + 4  # 배지 높이 + 위아래 pady(2)*2
        search_h = SEARCH_BOX_H if is_issue_list else 0
        content_h = pad * 2 + search_h + len(nodes) * item_h
        max_h = min(560, self.sh - 160)  # 화면을 벗어나지 않는 선에서 최대 높이 제한
        panel_h = min(content_h, max_h)
        needs_scroll = content_h > max_h

        # 메인 패널의 아래쪽 기준선에 맞춰, depth가 깊을수록 오른쪽 칸에 위로 쌓아 표시
        # (아이콘이 화면 맨 아래에 있으므로 위→아래가 아니라 아래→위로 쌓아야 안 잘림)
        base_y = self.icon_y - 8
        x = self.icon_x + PANEL_W + (PANEL_GAP + FLYOUT_W) * depth
        y = base_y - panel_h
        flyout.geometry(f"{width}x{panel_h}+{x}+{y}")

        search_entry = None
        search_placeholder = "제목+본문+댓글 검색..." if project_id is not None else "제목 검색..."
        if is_issue_list:
            # 이슈 제목으로 검색할 수 있는 검색창을 목록 위에 둔다.
            search_entry = tk.Entry(
                flyout, font=(FONT_FAMILY, 9), bg=BADGE_BG, fg=BADGE_FG_MUTED,
                relief="flat", insertbackground=BADGE_FG,
                highlightthickness=1, highlightbackground=SHADOW_COLOR, highlightcolor=BG_COLOR,
            )
            search_entry.insert(0, search_placeholder)
            search_entry.pack(fill="x", padx=pad, pady=(pad, 4), ipady=3)

            def on_search_focus_in(_e):
                if search_entry.get() == search_placeholder:
                    search_entry.delete(0, "end")
                    search_entry.config(fg=BADGE_FG)

            def on_search_focus_out(_e):
                if not search_entry.get():
                    search_entry.insert(0, search_placeholder)
                    search_entry.config(fg=BADGE_FG_MUTED)

            search_entry.bind("<FocusIn>", on_search_focus_in)
            search_entry.bind("<FocusOut>", on_search_focus_out)

        if needs_scroll:
            # 항목이 너무 많아 화면에 다 못 들어가면 스크롤 가능한 목록으로 만든다.
            scroll_canvas = tk.Canvas(flyout, bg=PANEL_BG, highlightthickness=0)
            scrollbar = tk.Scrollbar(flyout, orient="vertical", command=scroll_canvas.yview)
            scroll_canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            scroll_canvas.pack(side="left", fill="both", expand=True)

            badge_parent = tk.Frame(scroll_canvas, bg=PANEL_BG)
            window_id = scroll_canvas.create_window((0, 0), window=badge_parent, anchor="nw")

            def sync_scrollregion(_e=None):
                scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

            badge_parent.bind("<Configure>", sync_scrollregion)
            scroll_canvas.bind(
                "<Configure>", lambda e: scroll_canvas.itemconfigure(window_id, width=e.width)
            )

            def on_mousewheel(e):
                if scroll_canvas.winfo_exists():
                    scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

            scroll_canvas.bind_all("<MouseWheel>", on_mousewheel)

            def cleanup_wheel_binding(e):
                if e.widget is flyout:
                    scroll_canvas.unbind_all("<MouseWheel>")

            flyout.bind("<Destroy>", cleanup_wheel_binding)

            # 스크롤바의 실제 너비만큼만 정확히 제외한다.
            # (고정값을 대충 빼면 테마/DPI에 따라 실제 스크롤바 폭과 달라져 오른쪽 여백이 안 맞을 수 있음)
            flyout.update_idletasks()
            badge_w = width - pad * 2 - scrollbar.winfo_reqwidth()
        else:
            badge_parent = flyout
            badge_w = width - pad * 2

        badge_widgets = []

        def render_nodes(filtered_nodes):
            for w in badge_widgets:
                w.destroy()
            badge_widgets.clear()
            for node in filtered_nodes:
                badge_widgets.append(self._make_flyout_badge(badge_parent, node, badge_w, pad, depth))

        render_nodes(nodes)

        if search_entry is not None and project_id is not None:
            # 레드마인 자체 검색 API로 제목+본문+댓글까지 포함해서 검색한다
            # (프로젝트 하나를 보고 있을 때만 가능 - "내 일감"처럼 여러 프로젝트에
            # 걸쳐 있는 목록은 기존처럼 이미 불러온 제목 안에서만 찾는다).
            debounce = {"job": None}
            result_queue = queue.Queue()

            def poll_search_queue():
                if not flyout.winfo_exists():
                    return
                try:
                    results = result_queue.get_nowait()
                except queue.Empty:
                    pass
                else:
                    if results is not None:
                        render_nodes([
                            {"name": r["title"], "url": r["url"], "issue_id": r["issue_id"]}
                            for r in results
                        ])
                flyout.after(100, poll_search_queue)

            def fire_search():
                query = search_entry.get().strip()
                if query == search_placeholder:
                    query = ""
                if not query:
                    render_nodes(nodes)
                    return

                def worker():
                    result_queue.put(search_project_issues(project_id, query))

                threading.Thread(target=worker, daemon=True).start()

            def on_search_change(_e=None):
                if debounce["job"] is not None:
                    flyout.after_cancel(debounce["job"])
                debounce["job"] = flyout.after(350, fire_search)

            poll_search_queue()
            search_entry.bind("<KeyRelease>", on_search_change)
        elif search_entry is not None:
            def on_search_change(_e=None):
                query = search_entry.get().strip()
                if query == search_placeholder:
                    query = ""
                query = query.lower()
                render_nodes([n for n in nodes if query in n["name"].lower()] if query else nodes)

            search_entry.bind("<KeyRelease>", on_search_change)

        self.flyouts.append(flyout)

    def _make_flyout_badge(self, flyout, node, badge_w, pad, depth):
        name, url = node["name"], node["url"]
        children = node.get("children") or []
        has_children = bool(children)
        is_favorite_node = self.is_favorite(node.get("id"))
        issue_id = node.get("issue_id")
        id_badge_text = f"#{issue_id}" if issue_id is not None else None
        sub_font = (FONT_FAMILY, 9, "bold")
        sub_font_obj = tkfont.Font(family=FONT_FAMILY, size=9, weight="bold")

        if id_badge_text:
            # 이슈 항목: id 뱃지가 왼쪽에 고정되고, 제목은 그 오른쪽 영역
            # 안에서만 표시된다(2줄째도 뱃지 아래로 안 내려가고 제목 칸 폭 그대로 정렬).
            content_left = 12
            id_pill_w = sub_font_obj.measure(id_badge_text) + ISSUE_BADGE_PAD_X * 2
            title_indent_x = content_left + id_pill_w + ISSUE_BADGE_GAP
            title_w = badge_w - title_indent_x - 12
            title_lines = wrap_text_two_lines(sub_font_obj, name, title_w)
            # 제목이 1줄이든 2줄이든 위/아래 여백(ISSUE_ROW_PAD_Y)이 항상 똑같도록,
            # 실제 줄 수에 맞춰 뱃지 높이를 정한다(2줄 기준으로 고정하면 1줄일 때
            # 아래쪽에 남는 공간 때문에 위/아래 여백이 서로 달라 보인다).
            # draw_card가 그림자 때문에 카드 자체를 아래/오른쪽으로 (1 + SHADOW_OFFSET)px
            # 만큼 줄여서 그리므로, 그만큼을 여기서 미리 더해줘야 실제로 보이는 카드
            # 기준 아래 여백이 위 여백과 같아진다.
            line_h = sub_font_obj.metrics("linespace")
            row1_h = max(ISSUE_BADGE_H, line_h)
            card_shrink = 1 + SHADOW_OFFSET
            if len(title_lines) > 1:
                row_h = ISSUE_ROW_PAD_Y + row1_h + ISSUE_LINE_GAP + line_h + ISSUE_ROW_PAD_Y + card_shrink
            else:
                row_h = ISSUE_ROW_PAD_Y + row1_h + ISSUE_ROW_PAD_Y + card_shrink
        else:
            row_h = SUB_BADGE_H
            suffix = "  ›" if has_children else ""
            star_w = sub_font_obj.measure("★ ") if is_favorite_node else 0
            right_reserve = GO_ZONE_W if has_children else 12
            name_max_w = badge_w - 12 - star_w - right_reserve - sub_font_obj.measure(suffix)
            label = truncate_text(sub_font_obj, name, name_max_w) + suffix

        canvas = tk.Canvas(
            flyout, width=badge_w, height=row_h,
            bg=PANEL_BG, highlightthickness=0, cursor="hand2",
        )
        canvas.pack(padx=pad, pady=2)

        def render(bg, fg=BADGE_FG):
            canvas.delete("badge")
            _, cy = draw_card(canvas, badge_w, row_h, BADGE_RADIUS, bg)

            if id_badge_text:
                # 이슈 id를 알약(pill) 모양 뱃지로 강조 표시하고, 그 옆에 제목 1줄째를 이어 붙인다.
                line_h = sub_font_obj.metrics("linespace")
                row1_h = max(ISSUE_BADGE_H, line_h)
                row1_y1 = ISSUE_ROW_PAD_Y
                row1_y2 = row1_y1 + row1_h
                row1_cy = (row1_y1 + row1_y2) / 2

                pill_bg = BG_COLOR  # 진한 포인트 컬러로 채운 뱃지
                pill_fg = "#FFFFFF"  # 안쪽 글자는 연하게(흰색)
                pill_w = sub_font_obj.measure(id_badge_text) + ISSUE_BADGE_PAD_X * 2
                pill_y1 = row1_cy - ISSUE_BADGE_H / 2
                pill_y2 = row1_cy + ISSUE_BADGE_H / 2
                draw_rounded_rect(
                    canvas, content_left, pill_y1, content_left + pill_w, pill_y2, ISSUE_BADGE_H / 2,
                    fill=pill_bg, outline="", tags="badge",
                )
                canvas.create_text(
                    content_left + pill_w / 2, row1_cy, text=id_badge_text, fill=pill_fg,
                    font=sub_font, tags="badge",
                )
                # 제목: 뱃지 오른쪽 칸에서만 표시(1줄째는 뱃지와 같은 줄, 2줄째도 같은 x에서 아래로)
                canvas.create_text(
                    title_indent_x, row1_cy, anchor="w", text=title_lines[0],
                    fill=fg, font=sub_font, tags="badge",
                )
                if len(title_lines) > 1:
                    line2_cy = row1_y2 + ISSUE_LINE_GAP + line_h / 2
                    canvas.create_text(
                        title_indent_x, line2_cy, anchor="w", text=title_lines[1],
                        fill=fg, font=sub_font, tags="badge",
                    )
                return

            # 왼쪽 정렬: (즐겨찾기 별) + 이름(+하위 항목 있으면 화살표)
            left_x = 12
            if is_favorite_node:
                # 즐겨찾기 별은 포인트 컬러로 강조한다.
                # (선택 상태처럼 배경이 포인트 컬러일 땐 별도 흰색으로 맞춰 묻히지 않게 한다)
                star_color = fg if bg == BADGE_SELECTED_BG else BG_COLOR
                canvas.create_text(
                    left_x, cy, anchor="w", text="★ ", fill=star_color,
                    font=sub_font, tags="badge",
                )
                left_x += star_w
            canvas.create_text(left_x, cy, anchor="w", text=label, fill=fg, font=sub_font, tags="badge")

            if has_children:
                # 오른쪽 끝: 하위 목록을 펼치지 않고 이 프로젝트 자체 페이지로 바로 이동하는 버튼
                canvas.create_image(
                    badge_w - 1 - SHADOW_OFFSET - GO_ZONE_W / 2, cy,
                    image=self.go_icon, tags="badge",
                )

        def restore_idle():
            # 이 뱃지가 현재 펼쳐진(depth+1을 연) 상태라면 선택 표시를 유지한다.
            active = self.active_flyout_badge.get(depth)
            if active and active[0] is canvas:
                render(BADGE_SELECTED_BG, BADGE_SELECTED_FG)
            else:
                render(BADGE_BG)

        render(BADGE_BG)

        if has_children:
            def click(e):
                if e.x >= badge_w - GO_ZONE_W:
                    # 오른쪽 끝 "↗" 버튼: 하위 목록을 펼치지 않고 이 프로젝트 자체 페이지로 바로 이동
                    self._open_and_close(url)
                    return
                # 하위 목록이 이슈 목록이면(즐겨찾기 프로젝트의 이슈들) 제목이 길 수 있어 더 넓게 열고,
                # 이 프로젝트의 id를 넘겨서 검색창이 레드마인 자체 검색을 쓸 수 있게 한다.
                is_issue_list = bool(children) and children[0].get("issue_id") is not None
                self.open_flyout_level(
                    depth + 1, children, MY_ISSUES_FLYOUT_W if is_issue_list else FLYOUT_W,
                    project_id=node.get("id") if is_issue_list else None,
                )
                # 새로 펼쳐짐 → 이 뱃지를 선택 표시하고, 이전에 선택돼 있던 다른 뱃지는 되돌린다.
                prev = self.active_flyout_badge.get(depth)
                if prev and prev[0] is not canvas and prev[0].winfo_exists():
                    prev[1](BADGE_BG)
                self.active_flyout_badge[depth] = (canvas, render)
                render(BADGE_SELECTED_BG, BADGE_SELECTED_FG)
        else:
            click = lambda e: self._open_and_close(url)

        canvas.bind("<Button-1>", click)
        canvas.bind("<Button-3>", lambda e, n=node: self.show_favorite_menu(e, n))
        canvas.bind("<Enter>", lambda e: render(BADGE_HOVER))
        canvas.bind("<Leave>", lambda e: restore_idle())
        return canvas

    def close_flyouts_from(self, depth):
        """depth번째(0-based) 이후에 열린 플라이아웃들을 전부 닫는다."""
        while len(self.flyouts) > depth:
            self.flyouts.pop().destroy()
        # 닫힌 플라이아웃 안에서 "펼쳐짐" 선택 표시였던 뱃지들의 참조도 함께 정리
        # (canvas가 이미 destroy됐으므로 남겨두면 나중에 잘못 렌더링을 시도할 수 있음)
        for d in [d for d in self.active_flyout_badge if d >= depth]:
            del self.active_flyout_badge[d]

    def close_all_flyouts(self):
        self.close_flyouts_from(0)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    AssistantWidget().run()