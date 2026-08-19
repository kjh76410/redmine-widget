"""레드마인에 못 붙는 곳(집/외부망)에서 위젯 화면을 그대로 보기 위한 실행기.

    python webapp/demo.py

redmine_api의 조회 함수들만 가짜 데이터로 갈아끼우고 main.main()을 그대로 돌린다.
main.py는 한 줄도 안 건드린다 - 데모 분기를 실제 코드에 심어두면 나중에 진짜 앱에서
잘못 켜질 수 있다.

저장 계열(save_*)도 전부 막아둔다. 데모로 즐겨찾기를 지우거나 알림 기록을 덮어써서
진짜 데이터가 상하면 안 된다. 창 위치(widget_state)만은 진짜로 저장되게 두는데,
그건 "이 PC에서 위젯을 어디에 둘지"라 데모/실사용을 나눌 이유가 없다.
"""

import datetime
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import redmine_api

YEAR = datetime.date.today().year
TODAY = datetime.date.today()


def _day(offset):
    return (TODAY + datetime.timedelta(days=offset)).isoformat()


# ── 프로젝트 ──────────────────────────────────
# fetch_redmine_projects와 같은 평면 목록 형식({id, parent_id, name, url, source}).
# 트리로 묶는 건 진짜 build_project_tree가 하게 둔다.
def _project(pid, parent, name, source="company"):
    return {"id": pid, "parent_id": parent, "name": name,
            "url": f"http://demo/projects/{pid}/issues", "source": source}


COMPANY_PROJECTS = [
    _project(1, None, "데모 컴퍼니"),
    _project(10, 1, "MCX솔루션 개발팀"),
    _project(11, 10, "국내 프로젝트"),
    _project(12, 10, "해외 프로젝트"),
    _project(20, 1, "플랫폼 개발팀"),
    _project(21, 20, "관제 플랫폼"),
    _project(30, 1, "기구팀"),
    _project(100, None, "CASPER"),
    _project(101, 100, "CASPER 2차"),
    _project(110, None, "사내포털"),
]

TEAM_PROJECTS = [
    _project(500, None, "소방", source="team"),
    _project(501, 500, "소방 무전 연동", source="team"),
]

# ── 일감 ─────────────────────────────────────
TRACKERS = ["결함", "개발", "VoC", "디자인", "분석", "업무내용", "요구사항", "이슈", "기술문의", "접수", "기타"]
PRIORITIES = ["낮음", "보통", "높음", "긴급", "즉시"]

SUBJECTS = [
    "로그인 화면 비밀번호 찾기 링크 깨짐",
    "월 정산 리포트 엑셀 내려받기 추가",
    "고객사 문의 - 알림이 수신되지 않음",
    "관리자 페이지 좌측 메뉴 정렬 어긋남",
    "API 응답 지연 원인 분석",
    "배포 절차 문서 업데이트",
    "단말 펌웨어 v3.2 호환성 확인",
    "그룹 통화 중 음성 끊김 현상",
    "사용자 권한 그룹 신규 추가 요청",
    "대시보드 통계 집계 기준 변경",
    "모바일 앱 푸시 아이콘 교체",
    "야간 배치 실패 알림 메일 설정",
]


def _issue(n, project_name=None):
    """목록용 일감 하나. n으로 유형/우선순위/제목을 돌려가며 고른다."""
    subject = SUBJECTS[n % len(SUBJECTS)]
    return {
        "issue_id": 4700 + n,
        "title": f"[{project_name}] {subject}" if project_name else subject,
        "url": f"http://demo/issues/{4700 + n}",
        "tracker": TRACKERS[n % len(TRACKERS)],
        "priority": PRIORITIES[n % len(PRIORITIES)],
    }


# 개수는 창 높이(PANEL_SPEC 850px)에 들어가는 행 수보다 넉넉해야 한다 - 34px짜리
# 행이 22개쯤 들어가므로, 40건이면 스크롤과 "아래에 더 있다"가 확실히 확인된다.
MY_ISSUES = [_issue(n, ["CASPER", "사내포털", "관제 플랫폼"][n % 3]) for n in range(40)]
for _i, _issue_dict in enumerate(MY_ISSUES):
    _issue_dict["project_id"] = [100, 110, 21][_i % 3]


def _project_issues(project_id, count):
    return [_issue(project_id + n) for n in range(count)]


# ── 갈아끼우기 ─────────────────────────────────
def _fake_fetch_my_issues(identifier):
    return list(MY_ISSUES)


def _fake_fetch_project_issue_list(project_id, source="company", offset=0, limit=200):
    all_issues = _project_issues(int(project_id), 45)
    return all_issues[offset:offset + limit], len(all_issues)


_TOAST_TICK_S = 180  # 이 시간마다 한 칸씩 - 아래 설명 참고


def _fake_fetch_recent_issues(project_id, source="company"):
    """알림(토스트) 판정에 쓰인다. 매번 같은 목록을 주면 "새 일감"이 없어서 토스트를
    한 번도 못 보고, 반대로 매번 새 id를 주면 즐겨찾기 개수만큼 한꺼번에 쏟아진다.

    그래서 프로젝트마다 카운터가 오르는 시점을 어긋나게 뒀다((tick + pid) // 4).
    한 프로젝트당 12분에 하나씩, 프로젝트끼리는 번갈아 - 대충 몇 분에 하나씩
    토스트가 뜬다."""
    pid = int(project_id)
    tick = int(time.time() // _TOAST_TICK_S)
    newest = pid * 1000 + (tick + pid) // 4
    return [{"id": 90000 + newest - n,
             "subject": SUBJECTS[(newest + n) % len(SUBJECTS)],
             "url": f"http://demo/issues/{90000 + newest - n}"}
            for n in range(5)]


def _fake_fetch_issue(issue_id, source="company"):
    if source != "company":
        return None  # 번호 검색이 전사 -> 팀 순으로 찾는 흐름을 그대로 타보게
    n = int(issue_id)
    return {"issue_id": n, "title": SUBJECTS[n % len(SUBJECTS)],
            "url": f"http://demo/issues/{n}",
            "tracker": TRACKERS[n % len(TRACKERS)],
            "priority": PRIORITIES[n % len(PRIORITIES)]}


def _fake_fetch_issues_by_version(project_id):
    """버전별 연결된 일감.
    반환 형식은 [{"version":, "due_date":, "issues":[{"id","subject","url"}]}]."""
    labels = ["정기배포", "긴급패치", "기능추가", "안정화", "성능개선", "보안패치"]
    # 끝난 상태(closed=True로 칠 것)와 진행 중 상태를 섞어 둔다
    OPEN_STATUSES = ["신규", "진행", "피드백", "보류"]
    DONE_STATUSES = ["완료", "종료", "거부"]

    groups = []
    # 버전 6개 - 850px 창에 36px 행이 21개쯤 들어가는데, 6개면 일감이 33건이라
    # 목록이 확실히 넘쳐서 스크롤까지 같이 확인된다.
    for v in range(1, 7):
        count = 3 + v
        # 첫 버전은 전부 끝난 것으로 - 완료된 버전의 초록 뱃지도 같이 보이게
        done_upto = count if v == 1 else v
        issues = []
        for n in range(count):
            closed = n < done_upto
            issues.append({
                "id": 4700 + v * 10 + n,
                "subject": SUBJECTS[(v + n) % len(SUBJECTS)],
                "url": f"http://demo/issues/{4700 + v * 10 + n}",
                "status": (DONE_STATUSES[n % len(DONE_STATUSES)] if closed
                           else OPEN_STATUSES[n % len(OPEN_STATUSES)]),
                "closed": closed,
            })
        groups.append({
            "version": f"v2.{v}.0 {labels[v - 1]}",
            # 마지막 하나는 종료일을 비워 둔다 - 뱃지가 안 붙는 경우도 같이 보이게
            "due_date": None if v == 4 else _day(-40 + v * 45),
            "issues": issues,
        })
    return groups


def _fake_fetch_org_progress(pairs):
    """팀별 진행상황. (project_id, name) 목록을 받아 같은 순서로 돌려준다."""
    result = []
    for idx, (pid, name) in enumerate(pairs):
        versions = []
        # 팀당 5개 - 즐겨찾기 4팀 x 5 = 20행(27px)이라 850px 창을 거의 채운다.
        # Month 그리드도 그만큼 겹쳐서 막대가 촘촘하게 깔린 모습을 볼 수 있다.
        for v in range(5):
            total = 8 + v * 4
            percent = [100, 60, 20][(idx + v) % 3]
            start_month = 1 + ((idx + v * 3) % 8)
            end_month = min(12, start_month + 2 + v)
            versions.append({
                "version": f"v{2 + v}.{idx}.0 {'정기배포' if v else '긴급패치'}",
                "created_on": f"{YEAR}-{start_month:02d}-05",
                "due_date": f"{YEAR}-{end_month:02d}-28",
                "total": total,
                "closed": round(total * percent / 100),
                "percent": percent,
                "url": f"http://demo/versions/{pid}{v}",
            })
        result.append({"team": name, "team_id": pid, "versions": versions})
    return result


def _fake_search_project_issues(project_id, query, source="company"):
    words = [w.lower() for w in redmine_api.search_query_words(query)]
    hits = []
    for n in range(40):
        issue = _issue(int(project_id) + n)
        if all(w in issue["title"].lower() for w in words):
            hits.append({"issue_id": issue["issue_id"], "title": issue["title"],
                         "url": issue["url"]})
    return hits


def _fake_search_all_projects_issues(query, source="company"):
    words = [w.lower() for w in redmine_api.search_query_words(query)]
    names = ["CASPER", "사내포털", "관제 플랫폼"] if source == "company" else ["소방"]
    hits = []
    for n in range(30):
        issue = _issue(n)
        if not all(w in issue["title"].lower() for w in words):
            continue
        hits.append({"issue_id": issue["issue_id"], "title": issue["title"],
                     "url": issue["url"], "project_name": names[n % len(names)],
                     "tracker": issue["tracker"], "priority": issue["priority"]})
    return hits


# ── 배포 달력 ────────────────────────────────
# 즐겨찾기 프로젝트별 배포 버전. (버전id, 이름, 오늘로부터 며칠, 버전상태)
# 달력이 보여줘야 하는 경우가 한 화면에 다 나오도록 일부러 골라 뒀다:
#   - 지연 3건을 최근/오래된 것 섞어서 (왼쪽 목록이 "최근 놓친 순"으로 서는지)
#   - 오늘 나가는 배포 1건 (D-DAY 배지)
#   - 같은 날(D+2)에 4건 몰림 (달력 칸이 MAX_CHIPS개만 보여주고 나머지를 "+N건 더"로
#     접는지 - 지금은 3개까지 보여주므로 "+1건 더"가 된다)
#   - 이미 닫힌 버전 2건 (초록 "배포됨", 왼쪽 목록에는 안 뜨는 게 맞다)
#   - 60일 밖 1건 ("그 이후 1건은 달력에서..." 안내)
CALENDAR_VERSIONS = {
    100: [  # CASPER
        (9101, "v3.1.0 정기배포", -38, "closed"),
        (9102, "v3.2.0 정기배포", -6, "open"),
        (9103, "v3.3.0 기능추가", 2, "open"),
        (9104, "v4.0.0 차세대 아키텍처 전환", 74, "open"),
    ],
    21: [  # 관제 플랫폼
        (9201, "v2.8.1 긴급패치", -120, "open"),
        (9202, "v2.9.0 정기배포", 0, "open"),
        (9203, "v3.0.0 관제 화면 개편", 2, "open"),
        (9204, "v3.0.1 안정화", 21, "open"),
        (9205, "v3.0.2 긴급패치", 38, "open"),  # 추석 당일 - 공휴일 배포 경고 확인용
    ],
    110: [  # 사내포털
        (9301, "v1.4.0 정기배포", -15, "closed"),
        (9302, "v1.5.0 전자결재 연동", 2, "open"),
        (9303, "v1.6.0 모바일 대응", 2, "open"),
        (9304, "v1.7.0 정기배포", 40, "open"),
    ],
    500: [  # 소방 (팀 레드마인)
        (9401, "v0.8 시범적용", -200, "open"),
        (9402, "v0.9 파일럿", 9, "open"),
        (9403, "v1.0 1차 납품", 35, "open"),
    ],
}


def _fake_fetch_calendar_versions(projects):
    """배포 달력. (project_id, 이름, source) 목록을 받아 종료일 오름차순 평면 목록으로.
    진짜 함수와 같이, 종료일이 없는 버전은 애초에 담지 않는다."""
    rows = []
    for project_id, project_name, source in projects:
        for version_id, name, offset, status in CALENDAR_VERSIONS.get(project_id, []):
            rows.append({
                "version_id": version_id,
                "version": name,
                "project": project_name,
                "project_id": project_id,
                "source": source,
                "due_date": _day(offset),
                "status": status,
                "url": f"http://demo/versions/{version_id}",
            })
    rows.sort(key=lambda r: (r["due_date"], r["project"], r["version"]))
    return rows


# 닫힌 버전은 진행률도 100%여야 앞뒤가 맞는다(위 표에서 status가 "closed"인 것들).
CLOSED_VERSION_IDS = {
    vid for versions in CALENDAR_VERSIONS.values()
    for vid, _name, _offset, status in versions if status == "closed"
}


def _fake_fetch_version_issue_counts(version_id, source="company"):
    """날짜를 눌렀을 때 카드에 채워지는 진행률. 달력이 다뤄야 하는 세 갈래를 다 낸다:
    정상 집계 / 연결된 일감 0건 / 조회 실패(None)."""
    time.sleep(0.25)  # 진짜처럼 살짝 늦게 와야 "진행률 확인 중..." 자리가 보인다
    n = int(version_id)
    if n == 9203:
        return None                       # 조회 실패 - 카드가 진행률만 빼고 멀쩡히 남는지
    if n == 9302:
        return {"total": 0, "closed": 0}  # 버전만 만들고 일감을 안 붙인 경우
    total = 6 + (n % 5) * 4
    closed = total if n in CLOSED_VERSION_IDS else round(total * ((n % 4) + 1) / 5)
    return {"total": total, "closed": closed}


FAVORITES = [
    {"id": 100, "name": "CASPER", "url": "http://demo/projects/100/issues",
     "source": "company", "notify": True},
    {"id": 21, "name": "관제 플랫폼", "url": "http://demo/projects/21/issues",
     "source": "company", "notify": True},
    {"id": 110, "name": "사내포털", "url": "http://demo/projects/110/issues",
     "source": "company", "notify": False},
    {"id": 500, "name": "소방", "url": "http://demo/projects/500/issues",
     "source": "team", "notify": True},
]

_seen = {}


def install():
    """redmine_api의 조회/저장 함수를 데모용으로 갈아끼운다."""
    redmine_api.fetch_redmine_projects = lambda: list(COMPANY_PROJECTS)
    redmine_api.fetch_team_redmine_projects = lambda: list(TEAM_PROJECTS)
    redmine_api.fetch_my_issues = _fake_fetch_my_issues
    redmine_api.fetch_project_issue_list = _fake_fetch_project_issue_list
    redmine_api.fetch_recent_issues = _fake_fetch_recent_issues
    redmine_api.fetch_issue = _fake_fetch_issue
    redmine_api.fetch_issues_by_version = _fake_fetch_issues_by_version
    redmine_api.fetch_org_progress = _fake_fetch_org_progress
    redmine_api.fetch_calendar_versions = _fake_fetch_calendar_versions
    redmine_api.fetch_version_issue_counts = _fake_fetch_version_issue_counts
    redmine_api.fetch_current_user_id = lambda: 1
    redmine_api.resolve_user_id = lambda identifier: 1
    redmine_api.load_redmine_user_id = lambda: "demo"
    redmine_api.search_project_issues = _fake_search_project_issues
    redmine_api.search_all_projects_issues = _fake_search_all_projects_issues

    # 저장 계열은 전부 막는다 - 데모가 진짜 즐겨찾기/알림 기록/아이디 파일을 건드리면 안 된다.
    redmine_api.load_favorites = lambda: [dict(f) for f in FAVORITES]
    redmine_api.save_favorites = lambda favorites: None
    redmine_api.load_seen_issues = lambda: dict(_seen)
    redmine_api.save_seen_issues = lambda seen: _seen.update(seen)
    redmine_api.save_redmine_user_id = lambda value: None


def main():
    install()
    import main as widget  # install() 뒤에 불러야 갈아끼운 함수를 쓴다
    print("데모 모드로 실행합니다 - 레드마인에 접속하지 않고 가짜 데이터를 씁니다.", flush=True)
    widget.main()


if __name__ == "__main__":
    main()
