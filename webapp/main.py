"""
pywebview로 새로 만드는 위젯 셸 - 메인 아이콘 + 퀵 툴바 + 전사/팀 레드마인 프로젝트
트리(즐겨찾기 추가·해제 포함) + 내 일감/즐겨찾기 프로젝트 2단 창(검색/유형 필터/
스크롤 더 불러오기 포함) + 버전별 해결 일감 3단 창 + 로그인 아이디 설정 창 + 새 이슈
토스트 알림까지 구현했다. 패널은 전부 self.panel 슬롯 하나를 재사용해서 위젯 아이콘
바로 위, 같은 자리에만 뜬다(따로 팝업 안 튐). config.py/redmine_api.py는 기존
Tkinter 버전과 그대로 공유한다(순수 데이터 계층이라 프레임워크에 안 묶여 있음).
"""

import base64
import functools
import json
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
        self.icon_size = config.ICON_SIZE
        self.icon_x = config.MARGIN
        self.icon_y = screen.height - self.icon_size - config.MARGIN - 40

        shell_w = (
            self.icon_size + config.QUICK_TOOLBAR_MARGIN
            + config.QUICK_TOOLBAR_TOTAL_W + 20
        )
        self.shell = webview.create_window(
            "shell", html=bundle_html("shell.html"),
            width=shell_w, height=self.icon_size,
            x=self.icon_x, y=self.icon_y,
            frameless=True, on_top=True, transparent=True, resizable=False, shadow=False,
            easy_drag=False,  # 기본값 True면 창 아무 데나 눌러서 드래그가 돼 스크롤/클릭과 충돌한다
            min_size=(1, 1),  # 기본 최소 크기(200x100)보다 작은 창이 강제로 커지는 것을 막는다
            js_api=Api(self),
        )

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

    # ── 우클릭 메뉴 ──────────────────────────────
    def open_context_menu(self):
        if self.context_menu is not None:
            self.context_menu.destroy()
        w, h = 220, 108
        x = self.icon_x
        y = max(self.icon_y - 8 - h, 0)
        self.context_menu = webview.create_window(
            "context_menu", html=bundle_html("context_menu.html"),
            width=w, height=h, x=x, y=y,
            frameless=True, on_top=True, transparent=True, resizable=False, shadow=False,
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
        x = self.icon_x + self.icon_size + 12
        idx = len(self.toasts)
        base_y = self.icon_y + self.icon_size
        y = base_y - (idx + 1) * (config.TOAST_H + config.TOAST_GAP)
        toast = webview.create_window(
            f"toast-{toast_id}", html=bundle_html("toast.html"),
            width=config.TOAST_W, height=config.TOAST_H, x=x, y=y,
            frameless=True, on_top=True, transparent=True, resizable=False, shadow=False,
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
        x = self.icon_x + self.icon_size + 12
        base_y = self.icon_y + self.icon_size
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
        self.user_id_dialog = webview.create_window(
            "user_id_dialog", html=bundle_html("user_id_dialog.html"),
            width=w, height=h, x=x, y=y,
            frameless=True, on_top=True, transparent=True, resizable=False, shadow=False,
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
        self.panel = webview.create_window(
            "panel", html=bundle_html(template),
            width=panel_w, height=panel_h, x=x, y=y,
            frameless=True, on_top=True, transparent=True, resizable=False, shadow=False,
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
