"""
AssistantWidget - 메인 아이콘/퀵 툴바/각종 플라이아웃(즐겨찾기, 내 일감, 전사·팀
레드마인 프로젝트, 버전별 해결 일감)과 새 이슈 알림 토스트를 관리하는 위젯 클래스.
"""

import queue
import re
import threading

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import config
from config import (
    BADGE_BG,
    BADGE_FG,
    BADGE_FG_MUTED,
    BADGE_HOVER,
    BADGE_RADIUS,
    BADGE_SELECTED_BG,
    BADGE_SELECTED_FG,
    BG_COLOR,
    BOOKMARK_ICON_FILE,
    CRITICAL_ICON_FILE,
    FLYOUT_W,
    FOLDER_ICON_FILE,
    GO_ZONE_W,
    HIGH_ICON_FILE,
    ICON_BUTTON_BG,
    ICON_BUTTON_FG,
    ICON_GLYPH_PAD,
    ICON_IMAGE,
    ICON_KEY_COLOR,
    ICON_RADIUS,
    ICON_SIZE,
    ISSUE_BADGE_GAP,
    ISSUE_BADGE_H,
    ISSUE_BADGE_PAD_X,
    ISSUE_LINE_GAP,
    ISSUE_ROW_PAD_Y,
    LINKS,
    LOW_ICON_FILE,
    MARGIN,
    MIDDLE_ICON_FILE,
    MY_ICON_FILE,
    MY_ISSUES_FLYOUT_W,
    NOTIFY_ALL_PROJECTS,
    NOTIFY_POLL_INTERVAL_MS,
    PANEL_BG,
    PANEL_GAP,
    PRIORITY_ICON_SIZE,
    QUICK_TOOLBAR_GAP,
    QUICK_TOOLBAR_GLYPH_PAD,
    QUICK_TOOLBAR_ICON_SIZE,
    QUICK_TOOLBAR_MARGIN,
    QUICK_TOOLBAR_RADIUS,
    QUICK_TOOLBAR_TOTAL_W,
    SEARCH_BOX_H,
    SEARCH_ICON_FILE,
    SEARCH_ICON_SIZE,
    SHADOW_COLOR,
    SHADOW_OFFSET,
    SUB_BADGE_H,
    TEAM_REDMINE_URL,
    TOAST_CHIP_RADIUS,
    TOAST_CHIP_SIZE,
    TOAST_DURATION_MS,
    TOAST_GAP,
    TOAST_H,
    TOAST_W,
    WIDGET_WINDOW_H,
    WINDOW_ICON_FILE,
)
from redmine_api import (
    build_project_tree,
    fetch_current_user_id,
    fetch_my_issues,
    fetch_project_issue_list,
    fetch_recent_issues,
    fetch_redmine_projects,
    fetch_resolved_issues_by_version,
    fetch_team_redmine_projects,
    load_favorites,
    load_redmine_user_id,
    load_seen_issues,
    save_favorites,
    save_redmine_user_id,
    save_seen_issues,
    search_project_issues,
    search_query_words,
)
from ui_common import (
    draw_card,
    draw_rounded_rect,
    issue_row_height,
    load_go_icon,
    load_icon_glyph,
    load_toast_icon,
    open_url,
    truncate_text,
    wrap_text_two_lines,
)


class AssistantWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # 메인 윈도우는 숨김
        config.load_app_font()  # Pretendard 폰트 등록 (실패 시 기본 한글 폰트로 자동 대체)

        # 화면 크기 파악 (좌측 하단 좌표 계산용)
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        self.panel_open = False  # 퀵 툴바(+플라이아웃)가 열려 있는 상태인지
        self.flyouts = []       # 레드마인 하위 프로젝트 플라이아웃 스택 (depth 순서, 열려 있을 때만 존재)
        self.active_flyout_badge = {}    # depth -> 그 플라이아웃에서 현재 펼쳐져 있는(depth+1을 연) 뱃지의 (canvas, render)

        self.favorites = load_favorites()  # 레드마인 프로젝트 뱃지를 우클릭해 즐겨찾기한 목록 (영구 저장됨)
        self.favorite_issues = {}  # 즐겨찾기 프로젝트id(str) -> 그 프로젝트의 열려있는 이슈 목록(최근 200건, 백그라운드로 채워짐)
        self.favorite_issue_totals = {}  # 즐겨찾기 프로젝트id(str) -> 그 프로젝트의 전체 이슈 개수 (200건보다 많으면 스크롤로 더 불러올 때 씀)
        self._favorite_issues_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달
        self.redmine_tree = []  # 전사 레드마인 최상위 프로젝트 트리 (children에 하위 프로젝트, 백그라운드로 채워짐)
        self._redmine_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달
        self.team_redmine_tree = []  # 팀 레드마인 최상위 프로젝트 트리 (children에 하위 프로젝트, 백그라운드로 채워짐)
        self._team_redmine_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달

        self.redmine_user_id = load_redmine_user_id()  # "내 일감" 조회에 쓸 레드마인 사용자 ID (영구 저장됨)
        self.my_issues = []  # 내게 할당된 이슈 목록 (백그라운드로 채워짐)
        self._my_issues_queue = queue.Queue()  # 백그라운드 스레드 → 메인 스레드로 결과 전달

        self.seen_issue_ids = load_seen_issues()  # 즐겨찾기 프로젝트별로 이미 알림을 보낸 이슈 id (영구 저장됨)
        self._notify_queue = queue.Queue()  # 이슈 조회 백그라운드 스레드 → 메인 스레드로 결과 전달
        self._notify_worker_running = False  # 이전 조회가 안 끝났는데 새로 겹쳐 시작하지 않기 위한 플래그
        self.toasts = []  # 화면에 떠 있는 새 이슈 알림 토스트 목록
        self.toast_icon = load_toast_icon()  # 참조 유지(GC 방지)
        self.go_icon = load_go_icon()  # 뱃지 "바로 이동" 버튼 아이콘, 참조 유지(GC 방지)

        # 퀵 툴바(내 일감 / 즐겨찾기 / 전체 프로젝트 / 팀 레드마인 / 버전별 해결 일감) 원형 아이콘, 참조 유지(GC 방지)
        quick_glyph_size = QUICK_TOOLBAR_ICON_SIZE - QUICK_TOOLBAR_GLYPH_PAD * 2
        self.quick_my_icon = load_icon_glyph(MY_ICON_FILE, quick_glyph_size, "#FFFFFF")
        self.quick_bookmark_icon = load_icon_glyph(BOOKMARK_ICON_FILE, quick_glyph_size, "#FFFFFF")
        self.quick_folder_icon = load_icon_glyph(FOLDER_ICON_FILE, quick_glyph_size, "#FFFFFF")
        self.quick_window_icon = load_icon_glyph(WINDOW_ICON_FILE, quick_glyph_size, "#FFFFFF")
        self.search_icon = load_icon_glyph(SEARCH_ICON_FILE, SEARCH_ICON_SIZE, "#FFFFFF")  # 검색 버튼 아이콘, 참조 유지(GC 방지)
        self.quick_toolbar = None  # 패널이 열려 있을 때만 존재하는 Toplevel

        self.resolved_by_version_win = None  # "버전별 해결 일감" 창 (열려 있을 때만 존재)
        self.my_issues_win = None    # "내 일감" 창 (열려 있을 때만 존재)
        self.favorites_win = None    # "즐겨찾기 프로젝트" 창 (열려 있을 때만 존재)

        self._build_icon()
        self._poll_redmine_queue()
        self.refresh_redmine_projects()
        self._poll_team_redmine_queue()
        self.refresh_team_redmine_projects()
        self._poll_my_issues_queue()
        self.refresh_my_issues()
        self._poll_favorite_issues_queue()
        self.refresh_favorite_project_issues()
        self._poll_notify_queue()
        self._notify_tick()

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

    # ── 팀 레드마인 프로젝트 목록 백그라운드 조회 ──
    def refresh_team_redmine_projects(self):
        def worker():
            tree = build_project_tree(fetch_team_redmine_projects())
            self._team_redmine_queue.put(tree)

        threading.Thread(target=worker, daemon=True).start()

    def _poll_team_redmine_queue(self):
        try:
            tree = self._team_redmine_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.team_redmine_tree = tree
            if self.panel_open:
                self.close_panel()
                self.open_panel()
        self.root.after(500, self._poll_team_redmine_queue)

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
            totals = {}
            for fav in favorites_snapshot:
                source = fav.get("source", "company")
                key = self._favorite_key(fav["id"], source)
                issues, total = fetch_project_issue_list(fav["id"], source)
                result[key] = issues
                totals[key] = total
            self._favorite_issues_queue.put((result, totals))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_favorite_issues_queue(self):
        try:
            result, totals = self._favorite_issues_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.favorite_issues.update(result)
            self.favorite_issue_totals.update(totals)
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
                    source = project.get("source", "company")
                    issues = fetch_recent_issues(project["id"], source)
                    if issues is None:
                        continue  # 조회 실패 → 이번 회차는 건너뛰고 기존 기록 유지
                    key = self._favorite_key(project["id"], source)
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
            fill=BG_COLOR, font=(config.FONT_FAMILY, 9, "bold"),
        )
        subject = issue["subject"]
        if len(subject) > 20:
            subject = subject[:19] + "…"
        canvas.create_text(
            text_x, 44, anchor="w", text=subject,
            fill=BADGE_FG, font=(config.FONT_FAMILY, 10, "bold"),
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
        menu.add_command(label="레드마인 프로젝트 새로고침", command=self.refresh_redmine_projects)
        menu.add_command(label="내 일감 새로고침", command=self.refresh_my_issues)
        menu.tk_popup(event.x_root, event.y_root)

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
            bg=PANEL_BG, fg=BADGE_FG, font=(config.FONT_FAMILY, 9), justify="left", anchor="w",
        ).pack(fill="x", **pad)
        id_entry = tk.Entry(dialog, font=(config.FONT_FAMILY, 10))
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
        self.panel_open = True
        self._build_quick_toolbar()

    def close_panel(self):
        self.close_all_flyouts()
        self.panel_open = False
        self._close_quick_toolbar()

    # ── 메인 아이콘 옆 퀵 툴바 (내 일감 / 즐겨찾기 / 전체 프로젝트 / 팀 레드마인 원형 아이콘) ──
    #    패널이 열려 있는 동안만 함께 떠 있다가, 패널이 닫히면 같이 사라진다.
    def _build_quick_toolbar(self):
        self._close_quick_toolbar()

        size = QUICK_TOOLBAR_ICON_SIZE
        buttons = [
            (self.quick_my_icon, self._open_my_issues_flyout),
            (self.quick_bookmark_icon, self._open_favorites_flyout),
            (self.quick_folder_icon, self._open_all_projects_flyout),
            (self.quick_folder_icon, self._open_team_redmine),
            (self.quick_window_icon, self._open_resolved_by_version_window),
        ]
        width = QUICK_TOOLBAR_TOTAL_W

        toolbar = tk.Toplevel(self.root)
        toolbar.overrideredirect(True)
        toolbar.attributes("-topmost", True)
        toolbar.configure(bg=ICON_KEY_COLOR)
        toolbar.attributes("-transparentcolor", ICON_KEY_COLOR)

        x = self.icon_x + ICON_SIZE + QUICK_TOOLBAR_MARGIN
        y = self.icon_y + (ICON_SIZE - size) // 2
        toolbar.geometry(f"{width}x{size}+{x}+{y}")

        canvas = tk.Canvas(
            toolbar, width=width, height=size,
            bg=ICON_KEY_COLOR, highlightthickness=0,
        )
        canvas.pack(expand=True, fill="both")

        for i, (glyph, handler) in enumerate(buttons):
            cx0 = i * (size + QUICK_TOOLBAR_GAP)
            draw_rounded_rect(
                canvas, cx0, 0, cx0 + size - 1, size - 1, QUICK_TOOLBAR_RADIUS,
                fill=ICON_BUTTON_BG, outline="",
            )
            canvas.create_image(cx0 + size / 2, size / 2, image=glyph)
            tag = f"quick_btn_{i}"
            canvas.create_rectangle(
                cx0, 0, cx0 + size, size, fill="", outline="", tags=tag,
            )
            canvas.tag_bind(tag, "<Button-1>", lambda _e, h=handler: h())

            # "내 일감" 아이콘 오른쪽 위 모서리에 개수 뱃지 표시
            # (테두리 스트로크는 색상키/배경과 얽혀 흰 테두리로 보이는 문제가 있어 안 씀.
            #  퀵 툴바 캔버스 높이가 아이콘 높이(size)와 딱 맞아서, 모서리 밖으로 튀어나오게
            #  그리면 캔버스 밖으로 잘리므로 캔버스 안쪽에 완전히 들어오게 그린다)
            if i == 0 and self.my_issues:
                count_text = str(len(self.my_issues)) if len(self.my_issues) <= 99 else "99+"
                badge_r = 9
                badge_cx, badge_cy = cx0 + size - badge_r - 2, badge_r + 2
                canvas.create_oval(
                    badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r,
                    fill="#E5484D", outline="",
                )
                canvas.create_text(
                    badge_cx, badge_cy, text=count_text, fill="#FFFFFF",
                    font=(config.FONT_FAMILY, 8, "bold"),
                )

        canvas.configure(cursor="hand2")
        self.quick_toolbar = toolbar

    def _close_quick_toolbar(self):
        if self.quick_toolbar is not None:
            self.quick_toolbar.destroy()
            self.quick_toolbar = None

    def _open_my_issues_flyout(self):
        if not self.redmine_user_id:
            self.open_set_user_id_dialog()
            return
        # "[프로젝트명] 제목" 형태인 내 일감 제목에서 프로젝트명을 뽑아 프로젝트별로 묶는다.
        groups = {}
        order = []
        for issue in self.my_issues:
            m = re.match(r"^\[(.+?)\]\s*(.*)$", issue["title"])
            project_name, subject = (m.group(1), m.group(2)) if m else ("프로젝트 미상", issue["title"])
            if project_name not in groups:
                groups[project_name] = []
                order.append(project_name)
            groups[project_name].append(
                {
                    "issue_id": issue["issue_id"], "title": subject, "url": issue["url"],
                    "tracker": issue.get("tracker", ""), "priority": issue.get("priority", ""),
                }
            )
        self._open_project_issue_window(
            "my_issues_win", "내 일감",
            sorted(
                [{"project": p, "issues": groups[p]} for p in order],
                key=lambda g: g["project"],
            ),
        )

    def _open_favorites_flyout(self):
        section_label = {"company": "레드마인(150)", "team": "레드마인(20)"}
        section_order = {"company": 0, "team": 1}

        def to_group(f):
            source = f.get("source", "company")
            key = self._favorite_key(f["id"], source)
            issues = self.favorite_issues.get(key, [])
            return {
                "project": f["name"],
                "issues": issues,
                "section": section_label.get(source, source),
                "_order": section_order.get(source, 99),
                # 스크롤로 더 불러오기에 필요한 정보 - 처음엔 200건까지만 캐시돼 있고,
                # total이 그보다 크면 아래로 스크롤할 때 이어서 더 가져온다.
                "project_id": f["id"],
                "source": source,
                "total": self.favorite_issue_totals.get(key, len(issues)),
            }

        groups = sorted(
            [to_group(f) for f in self.favorites],
            key=lambda g: (g["_order"], g["project"]),
        )
        self._open_project_issue_window("favorites_win", "즐겨찾기 프로젝트", groups)

    # ── "내 일감" / "즐겨찾기 프로젝트" 공용 2단(4:6) 창 ─────
    #    윈도우 11 시작 메뉴처럼 고정된 크기로 뜨고, 왼쪽엔 프로젝트, 오른쪽엔
    #    선택한 프로젝트의 일감을 보여준다. groups: [{"project": str, "issues": [...]}]
    #    group에 "section"이 있으면(예: 즐겨찾기의 전사/팀 레드마인 구분) 그 값이
    #    바뀔 때마다 프로젝트 목록 위에 구분자 문구를 넣어 보여준다.
    def _open_project_issue_window(self, slot_attr, title, groups):
        existing = getattr(self, slot_attr)
        if existing is not None and existing.winfo_exists():
            # 아이콘을 다시 누른 것 → 다른 위젯 패널들처럼 토글로 닫는다.
            existing.destroy()
            return

        win_w, win_h = 800, WIDGET_WINDOW_H  # 윈도우 11 시작 메뉴와 비슷한 고정 크기(내용에 따라 안 늘어남)
        pad = 12

        win_bg, left_bg, right_bg = "#ECEAF2", "#F0F0F0", "#FFFFFF"
        text_fg, muted_fg = "#332C46", "#585070"
        card_bg, card_hover = "#FFFFFF", "#DEE1F5"  # 카드 기본/호버(포인트 색 파스텔 톤)
        issue_row_divider = "#8C8C8C"  # 일감 사이 구분선(진한 회색)
        accent_dark, selected_fg = "#5C6BC0", "#FFFFFF"  # 선택 시 포인트 색 배경 + 흰 글자
        divider_color = "#D6D2E2"

        # 유형(트래커)별 파스텔 색 - (배경, 글자). 이슈 카드의 유형 뱃지와 검색창 아래
        # 유형 필터 뱃지가 같은 색을 쓴다. 목록에 없는 유형은 muted 톤으로 대체.
        TRACKER_BADGE_COLORS = {
            "VoC": ("#FBE0E9", "#A23F63"),
            "결함": ("#FBDBDB", "#B3382E"),
            "개발": ("#DCEBFB", "#2D5F8A"),
            "디자인": ("#E9DFFB", "#6440A5"),
            "분석": ("#D9F3EC", "#1F7A63"),
            "업무내용": ("#FBF0D2", "#93701B"),
            "요구사항": ("#E1E6FB", "#3D4FA0"),
            "이슈": ("#FDE7D3", "#9A5B22"),
        }
        TRACKER_BADGE_FALLBACK = ("#E7E4F2", "#5C5470")

        # 우선순위 뱃지 - 낮음/보통은 차분한 회색·파랑 톤으로, 높음부터는 빨간 계열로
        # 점점 진하게 해서 급한 정도가 한눈에 보이게 한다.
        PRIORITY_BADGE_COLORS = {
            "낮음": ("#E7ECF5", "#5A6B85"),
            "보통": ("#E9E7EE", "#5C5470"),
            "높음": ("#FBDCDA", "#C1392B"),
            "긴급": ("#F8C9C5", "#A8281A"),
            "즉시": ("#F3B0AA", "#7A160C"),
        }
        PRIORITY_BADGE_FALLBACK = ("#E7E4F2", "#5C5470")
        PRIORITY_ICON_FILES = {
            "낮음": LOW_ICON_FILE, "보통": MIDDLE_ICON_FILE, "높음": HIGH_ICON_FILE,
            "긴급": CRITICAL_ICON_FILE, "즉시": CRITICAL_ICON_FILE,
        }
        # 뱃지 색(글자색)으로 물들인 우선순위 아이콘 - 뱃지 배경마다 톤이 달라서 미리 다 만들어둔다.
        PRIORITY_ICONS = {
            name: load_icon_glyph(file, PRIORITY_ICON_SIZE, PRIORITY_BADGE_COLORS[name][1])
            for name, file in PRIORITY_ICON_FILES.items()
        }

        win = tk.Toplevel(self.root)
        win._priority_icons = PRIORITY_ICONS  # 참조 유지(GC 방지)
        win.overrideredirect(True)  # 팝업창이 아니라 다른 위젯 패널들처럼 테두리/타이틀바 없이
        # 창 네 모서리를 살짝 둥글게 깎기 위해, 창 배경 자체를 색상키로 투명 처리해두고
        # (실제 내용은 아래에서 각 프레임이 자기 색으로 완전히 덮으므로 평소엔 안 보임)
        # 맨 마지막에 모서리 4곳에만 둥근 "마스크"를 얹어 그 부분만 배경이 비치게 한다.
        win.configure(bg=ICON_KEY_COLOR)
        win.attributes("-transparentcolor", ICON_KEY_COLOR)
        win.attributes("-topmost", True)
        # 위젯 바로 위, 아이콘 기준선에 딱 붙여서 뜨게 한다(다른 플라이아웃과 같은 기준).
        base_y = self.icon_y - 8
        win.geometry(f"{win_w}x{win_h}+{self.icon_x}+{base_y - win_h}")
        win.grid_rowconfigure(0, weight=0)
        win.grid_rowconfigure(1, weight=1)
        win.grid_columnconfigure(0, weight=3)  # 왼쪽 30%: 프로젝트
        win.grid_columnconfigure(1, weight=0)  # 구분선
        win.grid_columnconfigure(2, weight=7)  # 오른쪽 70%: 일감

        # 창 배경이 색상키(투명)라서, header_row 바깥에 padx/pady로 여백을 두면 그 여백
        # 부분이 안 덮여서 구멍(투명)이 뚫려 보인다. 그래서 header_row는 셀을 여백 없이
        # 꽉 채우고, 여백은 그 안쪽 자식 위젯들의 grid pad로 준다.
        header_row = tk.Frame(win, bg=win_bg)
        header_row.grid(row=0, column=0, columnspan=3, sticky="nsew")
        header_row.grid_columnconfigure(0, weight=1)

        tk.Label(
            header_row, text=title, bg=win_bg, fg=text_fg, font=(config.FONT_FAMILY, 12, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(pad, 0), pady=(pad, 6))

        # 윈도우 11 시작 메뉴 검색창처럼: 완전히 둥근 알약 모양 안에 돋보기 아이콘 + 입력칸.
        # tk.Entry 자체는 모서리를 못 둥글게 하므로, 둥근 사각형을 그린 캔버스 위에
        # 테두리/배경 없는 Entry를 겹쳐서 마치 하나의 둥근 입력창처럼 보이게 만든다.
        search_placeholder = "제목 검색..."
        pill_w, pill_h = 320, 34
        search_icon_muted = load_icon_glyph(SEARCH_ICON_FILE, 14, muted_fg)
        search_icon_active = load_icon_glyph(SEARCH_ICON_FILE, 14, text_fg)

        search_area = tk.Frame(header_row, bg=win_bg)
        search_area.grid(row=0, column=1, sticky="e", padx=(0, pad), pady=(pad, 6))
        search_canvas = tk.Canvas(
            search_area, width=pill_w, height=pill_h, bg=win_bg, highlightthickness=0,
        )
        search_canvas.pack(side="left")
        draw_rounded_rect(
            search_canvas, 0, 0, pill_w - 1, pill_h - 1, pill_h / 2,
            fill=card_bg, outline=divider_color,
        )
        icon_x = 18
        icon_id = search_canvas.create_image(icon_x, pill_h / 2, image=search_icon_muted)

        entry_x = icon_x + 16
        entry_w = pill_w - entry_x - 16
        search_entry = tk.Entry(
            search_canvas, font=(config.FONT_FAMILY, 9), bg=card_bg, fg=muted_fg,
            relief="flat", bd=0, highlightthickness=0, insertbackground=text_fg,
        )
        search_entry.insert(0, search_placeholder)
        search_canvas.create_window(
            entry_x, pill_h / 2, window=search_entry, anchor="w", width=entry_w, height=pill_h - 10,
        )

        def on_search_focus_in(_e):
            search_canvas.itemconfigure(icon_id, image=search_icon_active)
            if search_entry.get() == search_placeholder:
                search_entry.delete(0, "end")
                search_entry.config(fg=text_fg)

        def on_search_focus_out(_e):
            search_canvas.itemconfigure(icon_id, image=search_icon_muted)
            if not search_entry.get():
                search_entry.insert(0, search_placeholder)
                search_entry.config(fg=muted_fg)

        search_entry.bind("<FocusIn>", on_search_focus_in)
        search_entry.bind("<FocusOut>", on_search_focus_out)
        # 참조 유지(GC 방지) - 창이 열려 있는 동안만 필요하므로 창 자체에 매달아 둔다.
        win._search_icons = (search_icon_muted, search_icon_active)

        # 검색란 바로 아래에 유형(트래커) 필터 뱃지 - 누르면 그 유형만, 다시 누르면 해제.
        # 실제 필터링 동작(toggle_type)은 오른쪽 목록 렌더링 함수들이 갖춰진 뒤 아래에서 정의한다.
        filter_row = tk.Frame(header_row, bg=win_bg)
        filter_row.grid(row=1, column=1, sticky="e", padx=(0, pad), pady=(0, 6))
        type_filter_buttons = {}

        # toggle_type은 오른쪽 목록 렌더링 함수들이 갖춰진 뒤 아래에서 실제 구현으로 정의된다
        # (버튼의 command 람다는 호출 시점에 이 이름을 다시 찾으므로 정의 순서는 문제없다).
        for type_name in TRACKER_BADGE_COLORS:
            badge_bg, badge_fg = TRACKER_BADGE_COLORS[type_name]
            btn = tk.Button(
                filter_row, text=type_name, font=(config.FONT_FAMILY, 8, "bold"),
                bg=badge_bg, fg=badge_fg, relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                activebackground=badge_bg, activeforeground=badge_fg,
                command=lambda t=type_name: toggle_type(t),
            )
            btn.pack(side="left", padx=(4, 0))
            type_filter_buttons[type_name] = btn

        # 기본 스크롤바(양 끝 화살표 버튼 있는 투박한 모양) 대신, 화살표 없이 얇은
        # 진한 보라 막대만 보이는 플랫 스크롤바로 새로 스타일을 정의한다.
        # (트러프 색이 배경마다 달라서 왼쪽/오른쪽 패널용 스타일을 따로 둠)
        style = ttk.Style(win)
        style.theme_use("clam")

        def define_scrollbar_style(name, trough_bg):
            style.layout(name, [
                ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                    ("Vertical.Scrollbar.thumb", {"expand": True, "sticky": "nswe"}),
                ]}),
            ])
            style.configure(
                name, troughcolor=trough_bg, background=accent_dark,
                bordercolor=trough_bg, lightcolor=accent_dark, darkcolor=accent_dark,
                relief="flat", gripcount=0, arrowsize=0, width=8,
            )
            style.map(name, background=[("active", "#7E5CBB")])

        define_scrollbar_style("Left.Vertical.TScrollbar", left_bg)
        define_scrollbar_style("Right.Vertical.TScrollbar", right_bg)

        def make_pane(col, bg, scrollbar_style):
            frame = tk.Frame(win, bg=bg)
            frame.grid(row=1, column=col, sticky="nsew")
            # width/height=1: Canvas의 기본 요청 크기(기본값이 꽤 커서 grid weight
            # 비율을 깨뜨림)를 없애야 3:7 비율이 실제로 지켜진다. fill="both"+expand=True가
            # 어차피 실제 렌더링 크기를 그리드가 배분한 만큼으로 늘려준다.
            canvas = tk.Canvas(frame, bg=bg, highlightthickness=0, width=1, height=1)
            scrollbar = ttk.Scrollbar(
                frame, orient="vertical", command=canvas.yview, style=scrollbar_style,
            )
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            body = tk.Frame(canvas, bg=bg)
            window_id = canvas.create_window((0, 0), window=body, anchor="nw")
            body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
            return canvas, body, scrollbar

        left_canvas, left_body, left_scrollbar = make_pane(0, left_bg, "Left.Vertical.TScrollbar")
        tk.Frame(win, bg=divider_color, width=1).grid(row=1, column=1, sticky="ns")
        right_canvas, right_body, right_scrollbar = make_pane(2, right_bg, "Right.Vertical.TScrollbar")
        pane_canvases = [left_canvas, right_canvas]

        # 창 크기가 고정이라 픽셀 폭을 미리 계산해도 어긋나지 않는다.
        # (스크롤바 실제 폭은 테마/DPI에 따라 다를 수 있어 직접 측정한다)
        win.update_idletasks()
        left_pane_w = int(win_w * 0.3) - 1
        right_pane_w = win_w - left_pane_w - 1
        left_badge_w = left_pane_w - pad * 2 - left_scrollbar.winfo_reqwidth()
        right_badge_w = right_pane_w - pad * 2 - right_scrollbar.winfo_reqwidth()

        def on_mousewheel(e):
            for c in pane_canvases:
                if c.winfo_exists() and str(e.widget).startswith(str(c)):
                    c.yview_scroll(int(-1 * (e.delta / 120)), "units")
                    return

        left_canvas.bind_all("<MouseWheel>", on_mousewheel)

        def cleanup(_e=None):
            left_canvas.unbind_all("<MouseWheel>")
            setattr(self, slot_attr, None)

        win.bind("<Destroy>", lambda e: cleanup() if e.widget is win else None)

        def render_right_placeholder(text):
            for w in right_body.winfo_children():
                w.destroy()
            tk.Label(
                right_body, text=text, bg=right_bg, fg=muted_fg, font=(config.FONT_FAMILY, 10),
            ).pack(padx=pad, pady=pad, anchor="w")

        issue_font = tkfont.Font(family=config.FONT_FAMILY, size=9, weight="bold")
        tracker_font = tkfont.Font(family=config.FONT_FAMILY, size=8, weight="bold")

        def add_issue_card(issue):
            row_h = 34
            tracker = issue.get("tracker")
            priority = issue.get("priority")
            id_text = f"#{issue['issue_id']}"
            label_text = f"{id_text}  {issue['title']}"

            canvas = tk.Canvas(
                right_body, width=right_badge_w, height=row_h,
                bg=right_bg, highlightthickness=0, cursor="hand2",
            )
            canvas.pack(padx=pad, pady=2)

            def render(hover=False):
                canvas.delete("card")
                bg = card_hover if hover else right_bg
                canvas.create_rectangle(0, 0, right_badge_w, row_h, fill=bg, outline="", tags="card")
                canvas.create_line(
                    0, row_h - 1, right_badge_w, row_h - 1, fill=issue_row_divider, tags="card",
                )
                cy = (row_h - 1) / 2

                left_x = 12
                if tracker:
                    badge_bg, badge_fg = TRACKER_BADGE_COLORS.get(tracker, TRACKER_BADGE_FALLBACK)
                    badge_h = 18
                    badge_w = tracker_font.measure(tracker) + 14
                    draw_rounded_rect(
                        canvas, left_x, cy - badge_h / 2, left_x + badge_w, cy + badge_h / 2,
                        badge_h / 2, fill=badge_bg, outline="", tags="card",
                    )
                    canvas.create_text(
                        left_x + badge_w / 2, cy, text=tracker, fill=badge_fg,
                        font=tracker_font, tags="card",
                    )
                    left_x += badge_w + 6

                if priority:
                    badge_bg, _ = PRIORITY_BADGE_COLORS.get(priority, PRIORITY_BADGE_FALLBACK)
                    icon = PRIORITY_ICONS.get(priority)
                    badge_d = 20
                    draw_rounded_rect(
                        canvas, left_x, cy - badge_d / 2, left_x + badge_d, cy + badge_d / 2,
                        badge_d / 2, fill=badge_bg, outline="", tags="card",
                    )
                    if icon:
                        canvas.create_image(left_x + badge_d / 2, cy, image=icon, tags="card")
                    left_x += badge_d + 8

                text = truncate_text(issue_font, label_text, right_badge_w - left_x - 12)
                canvas.create_text(left_x, cy, anchor="w", text=text, fill=text_fg, font=issue_font, tags="card")

            canvas.bind("<Configure>", lambda e: render())
            canvas.bind("<Enter>", lambda e: render(hover=True))
            canvas.bind("<Leave>", lambda e: render())
            canvas.bind("<Button-1>", lambda e, url=issue["url"]: open_url(url))
            render()

        def render_right_issues(issues):
            for w in right_body.winfo_children():
                w.destroy()
            if not issues:
                render_right_placeholder("일감이 없습니다.")
                return
            for issue in issues:
                add_issue_card(issue)

        # ── 즐겨찾기 프로젝트는 처음엔 최근 200건만 캐시돼 있고, 오른쪽 목록을 아래로
        #    끝까지 스크롤하면 이어서(offset) 더 불러와 뒤에 이어붙인다.
        right_state = {"group": None, "loading": False, "issues": [], "filter": None}
        load_more_queue = queue.Queue()

        def apply_right_filter():
            active = right_state["filter"]
            base = right_state["issues"]
            render_right_issues([i for i in base if i.get("tracker") == active] if active else base)

        def toggle_type(type_name):
            right_state["filter"] = None if right_state["filter"] == type_name else type_name
            for label, btn in type_filter_buttons.items():
                badge_bg, badge_fg = TRACKER_BADGE_COLORS[label]
                if label == right_state["filter"]:
                    btn.config(bg=badge_fg, fg="#FFFFFF", activebackground=badge_fg, activeforeground="#FFFFFF")
                else:
                    btn.config(bg=badge_bg, fg=badge_fg, activebackground=badge_bg, activeforeground=badge_fg)
            apply_right_filter()

        def show_group_issues(group):
            right_state["group"] = group
            right_state["loading"] = False
            right_state["issues"] = group["issues"]
            apply_right_filter()

        def try_load_more_issues():
            group = right_state["group"]
            if group is None or right_state["loading"]:
                return
            project_id = group.get("project_id")
            source = group.get("source")
            if project_id is None:
                return
            loaded = len(group["issues"])
            if loaded >= group.get("total", loaded):
                return
            right_state["loading"] = True

            def worker():
                more, _ = fetch_project_issue_list(project_id, source, offset=loaded)
                load_more_queue.put((group, more))

            threading.Thread(target=worker, daemon=True).start()

        def poll_load_more_queue():
            if not win.winfo_exists():
                return
            try:
                group, more = load_more_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                right_state["loading"] = False
                if more and right_state["group"] is group:
                    group["issues"].extend(more)
                    # 스크롤로 이어붙일 땐 화면을 통째로 다시 그리지 않고(스크롤 위치 유지)
                    # 새로 온 항목만 뒤에 붙이므로, 활성 필터가 있으면 그 유형만 걸러서 붙인다.
                    active = right_state["filter"]
                    display_more = [i for i in more if i.get("tracker") == active] if active else more
                    for issue in display_more:
                        add_issue_card(issue)
            win.after(150, poll_load_more_queue)

        poll_load_more_queue()

        def on_right_scroll(*args):
            right_scrollbar.set(*args)
            if len(args) >= 2 and float(args[1]) > 0.97:
                try_load_more_issues()

        right_canvas.configure(yscrollcommand=on_right_scroll)

        selected = {"render": None, "state": None}
        project_font = tkfont.Font(family=config.FONT_FAMILY, size=9, weight="bold")

        count_font = tkfont.Font(family=config.FONT_FAMILY, size=8, weight="bold")

        def add_project_card(group):
            project_name, issues = group["project"], group["issues"]
            row_h = SUB_BADGE_H
            count_text = str(group.get("total", len(issues)))
            # 원(지름=텍스트 폭)으로 그리면 숫자 자릿수가 늘수록 세로로도 같이 커져서
            # 뱃지 높이를 넘어 깨져 보이므로, 높이는 고정하고 폭만 늘어나는 둥근 네모로 그린다.
            count_h = ISSUE_BADGE_H
            count_w = max(count_font.measure(count_text) + 12, count_h)

            canvas = tk.Canvas(
                left_body, width=left_badge_w, height=row_h,
                bg=left_bg, highlightthickness=0, cursor="hand2",
            )
            canvas.pack(padx=pad, pady=2)

            state = {"selected": False}

            def render(hover=False):
                canvas.delete("badge")
                if state["selected"]:
                    bg, fg, circle_bg, circle_fg = accent_dark, selected_fg, selected_fg, accent_dark
                else:
                    bg, fg = (card_hover if hover else card_bg), text_fg
                    circle_bg, circle_fg = accent_dark, "#FFFFFF"
                draw_rounded_rect(canvas, 0, 0, left_badge_w - 1, row_h - 1, 8, fill=bg, outline="")
                # 개수 뱃지(둥근 네모)를 카드 오른쪽 끝에 붙이고, 프로젝트명은 그 왼쪽 칸에서만 표시
                circle_x2 = left_badge_w - 10
                circle_x1 = circle_x2 - count_w
                circle_y1, circle_y2 = row_h / 2 - count_h / 2, row_h / 2 + count_h / 2
                draw_rounded_rect(
                    canvas, circle_x1, circle_y1, circle_x2, circle_y2, 6,
                    fill=circle_bg, outline="", tags="badge",
                )
                canvas.create_text(
                    (circle_x1 + circle_x2) / 2, row_h / 2, text=count_text, fill=circle_fg,
                    font=count_font, tags="badge",
                )
                name_max_w = circle_x1 - 12 - 6
                text = truncate_text(project_font, project_name, name_max_w)
                canvas.create_text(
                    12, row_h / 2, anchor="w", text=text, fill=fg, font=project_font, tags="badge",
                )

            def on_click(_e):
                if selected["render"] is not None and selected["render"] is not render:
                    selected["state"]["selected"] = False
                    selected["render"]()
                state["selected"] = True
                render()
                selected["state"] = state
                selected["render"] = render
                show_group_issues(group)

            canvas.bind("<Button-1>", on_click)
            canvas.bind("<Enter>", lambda e: render(hover=True))
            canvas.bind("<Leave>", lambda e: render())
            render()

        if not groups:
            tk.Label(
                left_body, text="표시할 프로젝트가 없습니다.",
                bg=left_bg, fg=muted_fg, font=(config.FONT_FAMILY, 9), anchor="w", justify="left",
                wraplength=left_badge_w,
            ).pack(padx=pad, pady=pad, anchor="w")
        else:
            last_section = None
            for group in groups:
                section = group.get("section")
                if section and section != last_section:
                    tk.Label(
                        left_body, text=section, bg=left_bg, fg=muted_fg,
                        font=(config.FONT_FAMILY, 8, "bold"), anchor="w",
                    ).pack(fill="x", padx=pad, pady=(pad if last_section is None else 12, 2))
                    last_section = section
                add_project_card(group)

        # 헤더 검색: 선택된 프로젝트와 상관없이 전체 일감 제목에서 찾는다.
        def clear_project_selection():
            if selected["render"] is not None:
                selected["state"]["selected"] = False
                selected["render"]()
                selected["state"] = None
                selected["render"] = None

        # 즐겨찾기(그룹마다 project_id가 있음)는 캐시된(최근/스크롤로 불러온 것만) 제목에서만
        # 찾으면 아직 안 불러온 오래된 완료 이슈 등을 놓칠 수 있으므로, 레드마인 자체 검색
        # API(본문·댓글·완료 이슈까지 포함)로 프로젝트별로 찾아 합친다. "내 일감"처럼
        # project_id가 없는 목록은 기존처럼 이미 불러온 제목 안에서만 찾는다.
        search_token = {"n": 0}
        search_result_queue = queue.Queue()

        def poll_search_queue():
            if not win.winfo_exists():
                return
            try:
                token, matches = search_result_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                if token == search_token["n"]:
                    right_state["issues"] = matches
                    apply_right_filter()
            win.after(100, poll_search_queue)

        poll_search_queue()

        def run_remote_search(query, token):
            def worker():
                matches = []
                for group in groups:
                    project_id = group.get("project_id")
                    if project_id is None:
                        continue
                    results = search_project_issues(project_id, query, group.get("source", "company"))
                    if not results:
                        continue
                    cached_by_id = {i["issue_id"]: i for i in group["issues"]}
                    for r in results:
                        cached = cached_by_id.get(r["issue_id"])
                        matches.append({
                            "issue_id": r["issue_id"], "url": r["url"],
                            "title": f"[{group['project']}] {r['title']}",
                            # 검색 API 자체는 유형/우선순위를 안 주므로, 이미 불러와둔 캐시에 있으면 거기서 채운다
                            # (필터 뱃지·우선순위 뱃지가 검색 결과에도 적용되게 하기 위함. 캐시에 없으면 빈 값).
                            "tracker": cached.get("tracker", "") if cached else "",
                            "priority": cached.get("priority", "") if cached else "",
                        })
                search_result_queue.put((token, matches))

            threading.Thread(target=worker, daemon=True).start()

        def fire_search():
            query = search_entry.get().strip()
            if query == search_placeholder:
                query = ""
            clear_project_selection()
            right_state["group"] = None  # 검색 결과는 여러 프로젝트에 걸치므로 스크롤 더 불러오기 대상에서 제외
            search_token["n"] += 1
            if not query:
                right_state["issues"] = []
                render_right_placeholder("왼쪽에서 프로젝트를 선택하세요.")
                return

            has_project_ids = any(g.get("project_id") is not None for g in groups)
            if not has_project_ids:
                # 공백/슬래시 등으로 여러 단어를 넣으면(예: "VoLTE 수신", "VoLTE/PSVT")
                # 하나만 있어도 걸리는 게 아니라 전부 포함된 제목만 찾는다.
                words = [w.lower() for w in search_query_words(query)]
                matches = [
                    {"issue_id": issue["issue_id"], "url": issue["url"],
                     "title": f"[{group['project']}] {issue['title']}",
                     "tracker": issue.get("tracker", ""), "priority": issue.get("priority", "")}
                    for group in groups for issue in group["issues"]
                    if all(w in issue["title"].lower() for w in words)
                ]
                right_state["issues"] = matches
                apply_right_filter()
                return

            right_state["issues"] = []
            render_right_placeholder("검색 중...")
            run_remote_search(query, search_token["n"])

        search_debounce = {"job": None}

        def on_search_key(_e=None):
            if search_debounce["job"] is not None:
                win.after_cancel(search_debounce["job"])
            search_debounce["job"] = win.after(350, fire_search)

        search_entry.bind("<KeyRelease>", lambda e: on_search_key())
        search_entry.bind("<Return>", lambda e: fire_search())
        search_canvas.tag_bind(icon_id, "<Button-1>", lambda e: fire_search())
        search_canvas.tag_bind(icon_id, "<Enter>", lambda e: search_canvas.config(cursor="hand2"))
        search_canvas.tag_bind(icon_id, "<Leave>", lambda e: search_canvas.config(cursor=""))

        render_right_placeholder("왼쪽에서 프로젝트를 선택하세요.")

        # 창 네 모서리를 둥글게: 각 모서리에 작은 정사각형 캔버스를 겹쳐 올리고,
        # 안쪽(창 중심 방향)으로 치우친 원을 그려서 바깥쪽 뾰족한 부분만 색상키로
        # 남겨 투명(둥글게 깎인 것처럼) 되게 한다.
        corner_r = 14

        def add_corner_mask(x, y, circle_bbox, fill):
            c = tk.Canvas(win, width=corner_r, height=corner_r, bg=ICON_KEY_COLOR, highlightthickness=0)
            c.place(x=x, y=y)
            c.create_oval(*circle_bbox, fill=fill, outline="")

        add_corner_mask(0, 0, (0, 0, corner_r * 2, corner_r * 2), win_bg)
        add_corner_mask(win_w - corner_r, 0, (-corner_r, 0, corner_r, corner_r * 2), win_bg)
        add_corner_mask(0, win_h - corner_r, (0, -corner_r, corner_r * 2, corner_r), left_bg)
        add_corner_mask(
            win_w - corner_r, win_h - corner_r, (-corner_r, -corner_r, corner_r, corner_r), right_bg,
        )

        setattr(self, slot_attr, win)

    def _open_all_projects_flyout(self):
        self.toggle_redmine_flyout(LINKS[0][1], self.redmine_tree, FLYOUT_W, title="전사 프로젝트")

    def _open_team_redmine(self):
        self.toggle_redmine_flyout(TEAM_REDMINE_URL, self.team_redmine_tree, FLYOUT_W, title="팀 레드마인")

    # ── "버전별 해결 일감" 창 (왼쪽 30% 프로젝트 트리 / 오른쪽 70% 선택한 프로젝트의 버전별 해결 이슈) ──
    #    지금은 레이아웃 확인용이라 상태 기준(status_id=closed)은 나중에 조정될 수 있다.
    def _open_resolved_by_version_window(self):
        if self.resolved_by_version_win is not None and self.resolved_by_version_win.winfo_exists():
            self.resolved_by_version_win.lift()
            self.resolved_by_version_win.focus_force()
            return

        win_bg = "#F3F1FA"
        text_fg, muted_fg, accent = "#38304F", "#5E5379", "#6B54B0"
        selected_bg, selected_fg = accent, "#FFFFFF"
        card_bg, card_hover = "#FFFFFF", "#EAE4F7"  # 카드 기본/호버 배경
        guide_color = "#B8AED0"  # depth를 나타내는 점선 가이드 색
        divider_color = "#DCD5EE"

        win = tk.Toplevel(self.root)
        win.title("버전별 해결 일감")
        win.configure(bg=win_bg)
        win.attributes("-topmost", True)
        win.geometry(f"1000x600+{self.icon_x}+{max(self.icon_y - 600, 0)}")
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=3)  # 프로젝트 30%
        win.grid_columnconfigure(1, weight=0)  # 구분선
        win.grid_columnconfigure(2, weight=3)  # 버전 30%
        win.grid_columnconfigure(3, weight=0)  # 구분선
        win.grid_columnconfigure(4, weight=4)  # 이슈 40%

        # 기본 스크롤바(양 끝 화살표 버튼 있는 투박한 모양) 대신, 화살표 없이 얇은
        # 포인트 컬러 막대만 보이는 플랫 스크롤바로 새로 스타일을 정의한다.
        scroll_style = ttk.Style(win)
        scroll_style.theme_use("clam")
        scroll_style.layout("Resolved.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": True, "sticky": "nswe"}),
            ]}),
        ])
        scroll_style.configure(
            "Resolved.Vertical.TScrollbar", troughcolor=win_bg, background=accent,
            bordercolor=win_bg, lightcolor=accent, darkcolor=accent,
            relief="flat", gripcount=0, arrowsize=0, width=8,
        )
        scroll_style.map("Resolved.Vertical.TScrollbar", background=[("active", "#7E5CBB")])

        def make_pane(col):
            frame = tk.Frame(win, bg=win_bg)
            frame.grid(row=0, column=col, sticky="nsew")
            # width/height=1: Canvas 기본 요청 크기가 grid weight 비율(3:3:4)을 깨뜨리는 걸 막는다.
            canvas = tk.Canvas(frame, bg=win_bg, highlightthickness=0, width=1, height=1)
            scrollbar = ttk.Scrollbar(
                frame, orient="vertical", command=canvas.yview, style="Resolved.Vertical.TScrollbar",
            )
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            body = tk.Frame(canvas, bg=win_bg)
            window_id = canvas.create_window((0, 0), window=body, anchor="nw")
            body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
            return canvas, body

        project_canvas, project_body = make_pane(0)
        tk.Frame(win, bg=divider_color, width=1).grid(row=0, column=1, sticky="ns")
        version_canvas, version_body = make_pane(2)
        tk.Frame(win, bg=divider_color, width=1).grid(row=0, column=3, sticky="ns")
        issue_canvas, issue_body = make_pane(4)
        pane_canvases = [project_canvas, version_canvas, issue_canvas]

        def on_mousewheel(e):
            for c in pane_canvases:
                if c.winfo_exists() and str(e.widget).startswith(str(c)):
                    c.yview_scroll(int(-1 * (e.delta / 120)), "units")
                    return

        project_canvas.bind_all("<MouseWheel>", on_mousewheel)

        def cleanup(_e=None):
            project_canvas.unbind_all("<MouseWheel>")
            self.resolved_by_version_win = None

        win.bind("<Destroy>", lambda e: cleanup() if e.widget is win else None)

        selected_project = {"render": None, "state": None}
        selected_version = {"render": None, "state": None}
        load_token = {"value": 0}  # 버전 목록 결과가 최신 클릭에 대한 것인지 확인하는 토큰

        def render_placeholder(body, text):
            for w in body.winfo_children():
                w.destroy()
            tk.Label(
                body, text=text, bg=win_bg, fg=muted_fg, font=(config.FONT_FAMILY, 10),
            ).pack(padx=16, pady=16, anchor="w")

        # 이슈 하나를 그림자 없는 둥근 카드로 그린다. (프로젝트/버전 카드와 같은 스타일)
        def add_issue_card(issue):
            row_h = 32
            issue_font = tkfont.Font(family=config.FONT_FAMILY, size=9)
            label_text = f"#{issue['id']}  {issue['subject']}"

            canvas = tk.Canvas(issue_body, height=row_h, bg=win_bg, highlightthickness=0, cursor="hand2")
            canvas.pack(fill="x", padx=8, pady=2)

            def render(hover=False):
                canvas.delete("card")
                w = canvas.winfo_width()
                if w <= 1:
                    return
                bg = card_hover if hover else card_bg
                draw_rounded_rect(canvas, 0, 0, w - 1, row_h - 1, 8, fill=bg, outline="", tags="card")
                cy = (row_h - 1) / 2
                max_text_w = (w - 1) - 24
                text = truncate_text(issue_font, label_text, max_text_w)
                canvas.create_text(12, cy, anchor="w", text=text, fill=text_fg, font=issue_font, tags="card")

            canvas.bind("<Configure>", lambda e: render())
            canvas.bind("<Enter>", lambda e: render(hover=True))
            canvas.bind("<Leave>", lambda e: render())
            canvas.bind("<Button-1>", lambda e, url=issue["url"]: open_url(url))

        def render_issue_list(issues):
            for w in issue_body.winfo_children():
                w.destroy()
            if not issues:
                render_placeholder(issue_body, "이슈가 없습니다.")
                return
            for issue in issues:
                add_issue_card(issue)

        # 버전 하나를 둥근 카드로 그린다. 클릭하면 오른쪽 이슈 패널을 그 버전 기준으로 채운다.
        def add_version_card(group):
            row_h = 34
            version_font = tkfont.Font(family=config.FONT_FAMILY, size=9, weight="bold")
            label_text = f"{group['version']} ({len(group['issues'])})"

            canvas = tk.Canvas(version_body, height=row_h, bg=win_bg, highlightthickness=0, cursor="hand2")
            canvas.pack(fill="x", padx=8, pady=3)

            state = {"selected": False}

            def render(hover=False):
                canvas.delete("card")
                w = canvas.winfo_width()
                if w <= 1:
                    return
                if state["selected"]:
                    bg, fg = selected_bg, selected_fg
                else:
                    bg, fg = (card_hover if hover else card_bg), text_fg
                draw_rounded_rect(canvas, 0, 0, w - 1, row_h - 1, 8, fill=bg, outline="", tags="card")
                cy = (row_h - 1) / 2
                max_text_w = (w - 1) - 24
                text = truncate_text(version_font, label_text, max_text_w)
                canvas.create_text(12, cy, anchor="w", text=text, fill=fg, font=version_font, tags="card")

            canvas.bind("<Configure>", lambda e: render())
            canvas.bind("<Enter>", lambda e: render(hover=True))
            canvas.bind("<Leave>", lambda e: render())

            def on_click(_e):
                if selected_version["render"] is not None and selected_version["render"] is not render:
                    selected_version["state"]["selected"] = False
                    selected_version["render"]()
                state["selected"] = True
                render()
                selected_version["state"] = state
                selected_version["render"] = render
                render_issue_list(group["issues"])

            canvas.bind("<Button-1>", on_click)

        def render_version_groups(groups):
            for w in version_body.winfo_children():
                w.destroy()
            selected_version["render"] = None
            selected_version["state"] = None
            render_placeholder(issue_body, "왼쪽에서 버전을 선택하세요.")
            if not groups:
                render_placeholder(version_body, "해결된 이슈가 없거나 불러오지 못했습니다.")
                return
            for group in groups:
                add_version_card(group)

        def select_project(project_id):
            load_token["value"] += 1
            token = load_token["value"]

            render_placeholder(version_body, "불러오는 중...")
            render_placeholder(issue_body, "왼쪽에서 버전을 선택하세요.")
            result_queue = queue.Queue()

            def worker():
                result_queue.put(fetch_resolved_issues_by_version(project_id))

            threading.Thread(target=worker, daemon=True).start()

            def poll():
                if not win.winfo_exists():
                    return
                try:
                    groups = result_queue.get_nowait()
                except queue.Empty:
                    win.after(200, poll)
                    return
                # 그 사이 다른 프로젝트를 클릭했으면(선택이 바뀌었으면) 이 결과는 버린다.
                if load_token["value"] == token:
                    render_version_groups(groups)

            poll()

        # 프로젝트 하나를 웹 리스트처럼 둥근 카드(호버 + 선택 강조)로 그린다.
        # depth가 깊을수록 카드를 왼쪽에서 더 들여써서 계층을 표현한다. 최상위(depth 0)
        # 프로젝트만 접고 펼 수 있다 - 처음엔 접혀 있어서 최상위 프로젝트만 보이고,
        # 화살표를 누르면 그 아래 하위 프로젝트가 전부(더 깊은 단계까지) 펼쳐진다.
        TOGGLE_ZONE_W = 20

        def add_project_row(node, depth, container):
            label_text = node["name"]
            indent = depth * 18  # 카드 자체를 이만큼 오른쪽으로 밀어서 depth를 표현
            row_h = 34
            children = node.get("children") or []
            has_toggle = depth == 0 and bool(children)
            # 최상위 프로젝트는 하위 프로젝트가 있든 없든(화살표가 있든 없든) 이름 시작
            # 위치가 같도록, 화살표 자리를 항상 확보해둔다.
            text_extra_indent = TOGGLE_ZONE_W if depth == 0 else 0
            card_font = tkfont.Font(
                family=config.FONT_FAMILY, size=9, weight="bold" if depth == 0 else "normal",
            )

            canvas = tk.Canvas(container, height=row_h, bg=win_bg, highlightthickness=0, cursor="hand2")
            canvas.pack(fill="x", padx=(8, 10), pady=3)

            state = {"selected": False}
            expand_state = {"value": False}
            child_container = tk.Frame(container, bg=win_bg) if has_toggle else None

            def render(hover=False):
                canvas.delete("card")
                w = canvas.winfo_width()
                if w <= 1:
                    return
                # depth가 0보다 크면, 바로 위 부모 레벨에서 세로+가로로 꺾이는
                # "ㄴ" 모양(점선) 하나만 그려 이 카드로 이어준다. (조상 레벨을 잇는
                # 트렁크 세로선은 그리지 않음 - 바로 위/아래 관계만 표시)
                if depth > 0:
                    elbow_x = (depth - 1) * 18 + 9
                    elbow_y = row_h / 2
                    canvas.create_line(
                        elbow_x, 0, elbow_x, elbow_y, dash=(2, 2), fill=guide_color, tags="card",
                    )
                    canvas.create_line(
                        elbow_x, elbow_y, indent, elbow_y, dash=(2, 2), fill=guide_color, tags="card",
                    )
                if state["selected"]:
                    bg, fg = selected_bg, selected_fg
                else:
                    bg, fg = (card_hover if hover else card_bg), text_fg
                draw_rounded_rect(
                    canvas, indent, 0, w - 1, row_h - 1, 8,
                    fill=bg, outline="", tags="card",
                )
                cy = (row_h - 1) / 2
                if has_toggle:
                    arrow = "▾" if expand_state["value"] else "▸"
                    canvas.create_text(
                        indent + 10, cy, text=arrow, fill=fg, font=card_font, tags="card",
                    )
                text_x = indent + 12 + text_extra_indent
                max_text_w = (w - 1) - text_x - 12
                text = truncate_text(card_font, label_text, max_text_w)
                canvas.create_text(text_x, cy, anchor="w", text=text, fill=fg, font=card_font, tags="card")

            canvas.bind("<Configure>", lambda e: render())
            canvas.bind("<Enter>", lambda e: render(hover=True))
            canvas.bind("<Leave>", lambda e: render())

            def toggle_expand():
                expand_state["value"] = not expand_state["value"]
                if expand_state["value"]:
                    if not child_container.winfo_children():
                        # 처음 펼칠 때만 하위 프로젝트 행을 만든다(그 전엔 안 그려서 가볍게).
                        for child in children:
                            add_project_row(child, depth + 1, child_container)
                    child_container.pack(fill="x", after=canvas)
                else:
                    child_container.pack_forget()
                render()

            def on_click(e, pid=node["id"]):
                if has_toggle and e.x < indent + TOGGLE_ZONE_W:
                    toggle_expand()
                    return
                if selected_project["render"] is not None and selected_project["render"] is not render:
                    selected_project["state"]["selected"] = False
                    selected_project["render"]()
                state["selected"] = True
                render()
                selected_project["state"] = state
                selected_project["render"] = render
                select_project(pid)

            canvas.bind("<Button-1>", on_click)

            if not has_toggle:
                for child in children:
                    add_project_row(child, depth + 1, container)

        if not self.redmine_tree:
            tk.Label(
                project_body, text="프로젝트 목록을 불러오는 중이거나 없습니다.",
                bg=win_bg, fg=muted_fg, font=(config.FONT_FAMILY, 9), anchor="w", justify="left", wraplength=200,
            ).pack(padx=8, pady=8, anchor="w")
        else:
            for root_node in self.redmine_tree:
                add_project_row(root_node, 0, project_body)

        render_placeholder(version_body, "왼쪽에서 프로젝트를 선택하세요.")
        render_placeholder(issue_body, "프로젝트와 버전을 선택하세요.")

        self.resolved_by_version_win = win

    def _open_and_close(self, url):
        open_url(url)
        self.close_panel()

    # ── 즐겨찾기 (레드마인 프로젝트 뱃지 우클릭) ─────
    #    전사/팀 레드마인은 서로 다른 서버라 프로젝트 id가 우연히 겹칠 수 있으므로,
    #    즐겨찾기 식별/캐시 키는 항상 (source, id) 조합으로 다룬다.
    def _favorite_key(self, project_id, source):
        return f"{source}:{project_id}"

    def is_favorite(self, project_id, source="company"):
        return any(f["id"] == project_id and f.get("source", "company") == source for f in self.favorites)

    def toggle_favorite(self, node):
        project_id = node["id"]
        source = node.get("source", "company")
        if self.is_favorite(project_id, source):
            self.favorites = [
                f for f in self.favorites
                if not (f["id"] == project_id and f.get("source", "company") == source)
            ]
            # 즐겨찾기 해제 시 해당 프로젝트의 "확인한 이슈" 기록/이슈 목록 캐시도 함께 정리
            key = self._favorite_key(project_id, source)
            if self.seen_issue_ids.pop(key, None) is not None:
                save_seen_issues(self.seen_issue_ids)
            self.favorite_issues.pop(key, None)
        else:
            self.favorites.append(
                {"id": project_id, "name": node["name"], "url": node["url"], "source": source}
            )
            self.refresh_favorite_project_issues()  # 새로 즐겨찾기된 프로젝트의 이슈 목록을 바로 조회
        save_favorites(self.favorites)
        self.close_panel()

    def show_favorite_menu(self, event, node):
        if node.get("id") is None:
            return
        menu = tk.Menu(self.root, tearoff=0)
        is_fav = self.is_favorite(node["id"], node.get("source", "company"))
        label = "즐겨찾기 제거" if is_fav else "즐겨찾기 추가"
        menu.add_command(label=label, command=lambda: self.toggle_favorite(node))
        menu.tk_popup(event.x_root, event.y_root)

    # ── 레드마인 프로젝트 플라이아웃 (최상위 → 하위로 depth별 오른쪽에 펼침) ──
    def toggle_redmine_flyout(self, fallback_url, top_level_nodes, width=FLYOUT_W, title=None):
        if self.flyouts:
            self.close_all_flyouts()
            return
        if not top_level_nodes:
            # 아직 못 불러왔거나 등록된 프로젝트가 없으면 기본 링크로 이동
            self._open_and_close(fallback_url)
            return
        self.open_flyout_level(0, top_level_nodes, width, title=title)

    def open_flyout_level(self, depth, nodes, width=FLYOUT_W, project_id=None, title=None, type_filter=False):
        # 같은 depth를 다시 열 때는 그보다 깊은 플라이아웃부터 정리
        self.close_flyouts_from(depth)

        flyout = tk.Toplevel(self.root)
        flyout.overrideredirect(True)
        flyout.attributes("-topmost", True)
        # 창 네 모서리를 살짝 둥글게 깎기 위해, 창 배경 자체는 색상키로 투명 처리해두고
        # (아래 bg_fill이 안쪽 전체를 PANEL_BG로 완전히 덮으므로 평소엔 안 보임)
        # 맨 마지막에 모서리 4곳에만 둥근 "마스크"를 얹어 그 부분만 배경이 비치게 한다.
        flyout.configure(bg=ICON_KEY_COLOR)
        flyout.attributes("-transparentcolor", ICON_KEY_COLOR)

        pad = 12  # 뱃지 안쪽 텍스트 여백(12px)과 맞춰서, 플라이아웃 바깥 여백도 통일
        # 이슈 목록(아이디 뱃지 + 제목 2줄)은 일반 프로젝트 항목보다 뱃지가 더 높고, 검색창도 붙는다.
        is_issue_list = bool(nodes) and nodes[0].get("issue_id") is not None
        if is_issue_list:
            row_h = issue_row_height(tkfont.Font(family=config.FONT_FAMILY, size=9, weight="bold"))
        else:
            row_h = SUB_BADGE_H
        item_h = row_h + 4  # 배지 높이 + 위아래 pady(2)*2
        search_h = SEARCH_BOX_H if is_issue_list else 0
        # depth 0(제목 있음)이든 하위 depth(제목 없음)든 항상 같은 높이를 확보해야,
        # 오른쪽으로 펼쳐지는 하위 프로젝트 목록의 시작 위치가 최상위 목록과 맞는다.
        title_h = 36
        type_filter_h = 34 if type_filter else 0  # 일감 유형(트래커) 필터 뱃지 줄 높이
        content_h = pad * 2 + title_h + type_filter_h + search_h + len(nodes) * item_h
        # 내용量과 상관없이 "내 일감"/"즐겨찾기 프로젝트" 창과 높이를 맞춘다(너비는 그대로 FLYOUT_W).
        panel_h = min(WIDGET_WINDOW_H, self.sh - 160)
        needs_scroll = content_h > panel_h

        # 퀵 툴바(원형 아이콘들) 바로 위에, depth가 깊을수록 오른쪽 칸으로 쌓아 표시
        # (아이콘이 화면 맨 아래에 있으므로 위→아래가 아니라 아래→위로 쌓아야 안 잘림)
        base_y = self.icon_y - 8
        x = self.icon_x + (PANEL_GAP + FLYOUT_W) * depth
        y = base_y - panel_h
        flyout.geometry(f"{width}x{panel_h}+{x}+{y}")

        # 창 안쪽 전체를 PANEL_BG로 미리 덮는다(패딩 틈까지 포함) - 이게 없으면 색상키
        # 투명 배경이 그 틈으로 그대로 비쳐서 구멍이 뚫린 것처럼 보인다.
        bg_fill = tk.Frame(flyout, bg=PANEL_BG)
        bg_fill.place(x=0, y=0, width=width, height=panel_h)

        # 제목이 없어도(하위 depth) 같은 높이의 빈 칸을 확보해 목록 시작 위치를 맞춘다.
        title_area = tk.Frame(flyout, bg=PANEL_BG, height=title_h)
        title_area.pack(fill="x")
        title_area.pack_propagate(False)
        if title:
            tk.Label(
                title_area, text=title, bg=PANEL_BG, fg=BADGE_FG,
                font=(config.FONT_FAMILY, 10, "bold"), anchor="w",
            ).pack(fill="x", padx=pad, pady=(pad, 4))

        if type_filter:
            # 일감 유형(레드마인 트래커) 뱃지: 누르면 그 유형으로만 필터링, 다시 누르면 해제.
            ISSUE_TYPES = ("개발", "이슈")
            type_filter_state = {"active": None}
            type_filter_buttons = {}

            def apply_type_filter():
                active = type_filter_state["active"]
                render_nodes([n for n in nodes if n.get("tracker") == active] if active else nodes)

            def toggle_type(type_name):
                type_filter_state["active"] = (
                    None if type_filter_state["active"] == type_name else type_name
                )
                for label, btn in type_filter_buttons.items():
                    selected = label == type_filter_state["active"]
                    btn.config(
                        bg=BG_COLOR if selected else BADGE_BG,
                        fg="#FFFFFF" if selected else BADGE_FG_MUTED,
                    )
                apply_type_filter()

            filter_row = tk.Frame(flyout, bg=PANEL_BG)
            filter_row.pack(fill="x", padx=pad, pady=(0, 4))
            for type_name in ISSUE_TYPES:
                btn = tk.Button(
                    filter_row, text=type_name, font=(config.FONT_FAMILY, 9), bg=BADGE_BG, fg=BADGE_FG_MUTED,
                    relief="flat", bd=0, padx=12, pady=3, cursor="hand2",
                    activebackground=BADGE_HOVER, activeforeground=BADGE_FG,
                    command=lambda t=type_name: toggle_type(t),
                )
                btn.pack(side="left", padx=(0, 6))
                type_filter_buttons[type_name] = btn

        search_entry = None
        search_button = None
        search_placeholder = "제목 검색..."
        if is_issue_list:
            # 이슈 제목으로 검색할 수 있는 검색창 + 검색 버튼을 목록 위에 둔다.
            search_row = tk.Frame(flyout, bg=PANEL_BG)
            search_row.pack(fill="x", padx=pad, pady=(pad, 4))

            search_entry = tk.Entry(
                search_row, font=(config.FONT_FAMILY, 9), bg=BADGE_BG, fg=BADGE_FG_MUTED,
                relief="flat", insertbackground=BADGE_FG,
                highlightthickness=1, highlightbackground=SHADOW_COLOR, highlightcolor=BG_COLOR,
            )
            search_entry.insert(0, search_placeholder)
            search_entry.pack(side="left", fill="both", expand=True, ipady=3)

            search_button = tk.Button(
                search_row, image=self.search_icon, bg=BG_COLOR,
                relief="flat", activebackground=BADGE_HOVER,
                cursor="hand2", bd=0, padx=16,
            )
            search_button.pack(side="left", fill="y", padx=(6, 0))

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

            # 기본 스크롤바(양 끝 화살표 버튼 있는 투박한 모양) 대신, 화살표 없이 얇은
            # 포인트 컬러 막대만 보이는 플랫 스크롤바로 새로 스타일을 정의한다.
            scrollbar_style = ttk.Style(flyout)
            scrollbar_style.theme_use("clam")
            scrollbar_style.layout("Flyout.Vertical.TScrollbar", [
                ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                    ("Vertical.Scrollbar.thumb", {"expand": True, "sticky": "nswe"}),
                ]}),
            ])
            scrollbar_style.configure(
                "Flyout.Vertical.TScrollbar", troughcolor=PANEL_BG, background=BG_COLOR,
                bordercolor=PANEL_BG, lightcolor=BG_COLOR, darkcolor=BG_COLOR,
                relief="flat", gripcount=0, arrowsize=0, width=8,
            )
            scrollbar_style.map("Flyout.Vertical.TScrollbar", background=[("active", "#89A8D6")])

            scrollbar = ttk.Scrollbar(
                flyout, orient="vertical", command=scroll_canvas.yview,
                style="Flyout.Vertical.TScrollbar",
            )
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
            search_entry.bind("<Return>", lambda e: fire_search())
            search_button.config(command=fire_search)
        elif search_entry is not None:
            def on_search_change(_e=None):
                query = search_entry.get().strip()
                if query == search_placeholder:
                    query = ""
                query = query.lower()
                render_nodes([n for n in nodes if query in n["name"].lower()] if query else nodes)

            search_entry.bind("<KeyRelease>", on_search_change)
            search_entry.bind("<Return>", on_search_change)
            search_button.config(command=on_search_change)

        corner_r = 14

        def add_corner_mask(cx, cy, circle_bbox):
            c = tk.Canvas(flyout, width=corner_r, height=corner_r, bg=ICON_KEY_COLOR, highlightthickness=0)
            c.place(x=cx, y=cy)
            c.create_oval(*circle_bbox, fill=PANEL_BG, outline="")

        add_corner_mask(0, 0, (0, 0, corner_r * 2, corner_r * 2))
        add_corner_mask(width - corner_r, 0, (-corner_r, 0, corner_r, corner_r * 2))
        add_corner_mask(0, panel_h - corner_r, (0, -corner_r, corner_r * 2, corner_r))
        add_corner_mask(width - corner_r, panel_h - corner_r, (-corner_r, -corner_r, corner_r, corner_r))

        self.flyouts.append(flyout)

    def _make_flyout_badge(self, flyout, node, badge_w, pad, depth):
        name, url = node["name"], node["url"]
        children = node.get("children") or []
        has_children = bool(children)
        is_favorite_node = self.is_favorite(node.get("id"), node.get("source", "company"))
        issue_id = node.get("issue_id")
        id_badge_text = f"#{issue_id}" if issue_id is not None else None
        sub_font = (config.FONT_FAMILY, 9, "bold")
        sub_font_obj = tkfont.Font(family=config.FONT_FAMILY, size=9, weight="bold")

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
                # 이 프로젝트의 id를 넘겨서 검색창이 레드마인 자체 검색을 쓸 수 있게 하고,
                # 프로젝트 이름을 제목으로, 일감 유형(트래커) 필터 뱃지도 같이 보여준다.
                is_issue_list = bool(children) and children[0].get("issue_id") is not None
                self.open_flyout_level(
                    depth + 1, children, MY_ISSUES_FLYOUT_W if is_issue_list else FLYOUT_W,
                    project_id=node.get("id") if is_issue_list else None,
                    title=node["name"] if is_issue_list else None,
                    type_filter=is_issue_list,
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
