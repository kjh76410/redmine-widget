"""
레드마인 REST API 호출/데이터 저장 함수 모음 - 프로젝트/이슈 조회, 검색, 즐겨찾기·확인한
이슈 목록 저장/불러오기 등. tkinter나 그리기 관련 코드는 없고 순수 데이터 계층이다.
"""

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    CALENDAR_CACHE_FILE,
    FAVORITE_ISSUES_CACHE_FILE,
    FAVORITES_FILE,
    MY_ISSUES_CACHE_FILE,
    PROJECTS_CACHE_FILE,
    REDMINE_API_KEY_FILE,
    REDMINE_API_KEY_PLACEHOLDER,
    REDMINE_BASE_URL,
    RESOLVED_BY_VERSION_CACHE_FILE,
    SEEN_ISSUES_FILE,
    TEAM_PROGRESS_CACHE_FILE,
    TEAM_REDMINE_API_KEY_FILE,
    TEAM_REDMINE_BASE_URL,
)

def load_redmine_api_key():
    if not REDMINE_API_KEY_FILE.exists():
        return None
    key = REDMINE_API_KEY_FILE.read_text(encoding="utf-8").strip()
    if not key or key == REDMINE_API_KEY_PLACEHOLDER:
        return None
    return key


def load_team_redmine_api_key():
    if not TEAM_REDMINE_API_KEY_FILE.exists():
        return None
    key = TEAM_REDMINE_API_KEY_FILE.read_text(encoding="utf-8").strip()
    return key or None


def save_redmine_api_key(value):
    REDMINE_API_KEY_FILE.write_text(value.strip(), encoding="utf-8")


def save_team_redmine_api_key(value):
    TEAM_REDMINE_API_KEY_FILE.write_text(value.strip(), encoding="utf-8")


def redmine_server(source):
    """즐겨찾기 프로젝트의 출처("company"=전사 레드마인, "team"=팀 레드마인)에 맞는
    (base_url, api_key)를 돌려준다. 두 서버가 별도 API 키를 쓰기 때문에 필요하다."""
    if source == "team":
        return TEAM_REDMINE_BASE_URL, load_team_redmine_api_key()
    return REDMINE_BASE_URL, load_redmine_api_key()


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
                "source": "company",
            })

        offset += limit
        if not batch or offset >= data.get("total_count", 0):
            break

    return projects


def fetch_team_redmine_projects():
    """팀 레드마인(전사 레드마인과 별도 서버) REST API로 프로젝트 목록(평면 리스트,
    parent_id 포함)을 가져온다. 실패/미설정 시 빈 리스트를 반환."""
    api_key = load_team_redmine_api_key()
    if not api_key:
        return []

    projects = []
    offset = 0
    limit = 100
    while True:
        url = f"{TEAM_REDMINE_BASE_URL}/projects.json?limit={limit}&offset={offset}"
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
                "url": f"{TEAM_REDMINE_BASE_URL}/projects/{p.get('identifier', '')}/issues",
                "source": "team",
            })

        offset += limit
        if not batch or offset >= data.get("total_count", 0):
            break

    return projects


def fetch_recent_issues(project_id, source="company"):
    """레드마인 REST API로 특정 프로젝트의 최근 이슈 목록(id, 제목, url, 소속 프로젝트명)을
    가져온다. source로 전사/팀 레드마인 중 어느 서버에서 가져올지 정한다.

    project_id만 주고 물으면 레드마인이 그 프로젝트뿐 아니라 하위 프로젝트의 이슈까지
    같이 돌려준다(subproject_id로 좁히지 않음) - 그래서 각 이슈가 실제로 어느 프로젝트
    소속인지("project")를 같이 담아 돌려준다. 최상위와 하위 프로젝트를 둘 다 즐겨찾기해
    같은 이슈가 양쪽 조회에 다 걸리는 경우(main.py의 App._check_new_issues 참고), 이
    project 값으로 "진짜 소속 프로젝트" 이름을 토스트에 붙일 수 있다.
    실패/미설정 시 None을 반환(빈 목록과 구분해 이번 회차는 건너뛰기 위함)."""
    base_url, api_key = redmine_server(source)
    if not api_key:
        return None

    url = (
        f"{base_url}/issues.json"
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
            "url": f"{base_url}/issues/{i.get('id')}",
            "project": i.get("project", {}).get("name", ""),
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


def fetch_my_issues():
    """레드마인 REST API로 API 키 계정("나") 자신에게 할당된 이슈 목록(id 내림차순)을
    가져온다. 상태가 "완료"인 이슈는 목록에서 제외한다. API 키가 아직 없으면(설정 전)
    빈 리스트를 반환한다.

    조회에 실패하면 fetch_recent_issues와 같이 None을 반환한다 - 빈 목록과 꼭
    구분해야 한다. 잠깐의 실패를 "할당된 일감 없음"으로 받아들이면 배지가 0으로
    깜빡일 뿐 아니라, 알림 기준이 되는 "이미 본 일감" 목록까지 비워져서 다음
    회차에 갖고 있던 일감 전부가 새로 할당된 것처럼 토스트로 쏟아진다
    (main.py의 _notify_new_my_issues 참고)."""
    api_key = load_redmine_api_key()
    if not api_key:
        return []

    user_id = fetch_current_user_id()
    if not user_id:
        return None  # 계정 조회 자체가 HTTP 호출이라, 일시적인 실패일 수 있다

    url = (
        f"{REDMINE_BASE_URL}/issues.json"
        f"?assigned_to_id={user_id}&status_id=*&sort=id:desc&limit=100"
    )
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    issues = []
    for i in data.get("issues", []):
        if i.get("status", {}).get("name") == "완료":
            continue
        project_name = i.get("project", {}).get("name", "")
        subject = i.get("subject", "")
        issue_id = i.get("id")
        title = f"[{project_name}] {subject}" if project_name else subject
        issues.append({
            "issue_id": issue_id,
            "title": title,
            "url": f"{REDMINE_BASE_URL}/issues/{issue_id}",
            "tracker": i.get("tracker", {}).get("name", ""),
            "priority": i.get("priority", {}).get("name", ""),
            "project_id": i.get("project", {}).get("id"),
        })
    return issues


def fetch_issue(issue_id, source="company"):
    """이슈 번호 하나로 그 이슈만 가져온다(검색창에 번호를 쳤을 때 쓴다).
    없는 번호거나 볼 권한이 없거나 조회에 실패하면 None."""
    base_url, api_key = redmine_server(source)
    if not api_key:
        return None

    url = f"{base_url}/issues/{int(issue_id)}.json"
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return None  # 404(없는 번호)도 여기로 온다 - HTTPError가 URLError의 하위 클래스

    issue = data.get("issue")
    if not issue:
        return None
    return {
        "issue_id": issue.get("id"),
        "title": issue.get("subject", ""),
        "url": f"{base_url}/issues/{issue.get('id')}",
        "tracker": issue.get("tracker", {}).get("name", ""),
        "priority": issue.get("priority", {}).get("name", ""),
    }


def fetch_project_issue_list(project_id, source="company", offset=0, limit=200):
    """레드마인 REST API로 특정 프로젝트의 이슈 목록(열림/닫힘 모두, id 내림차순)을
    offset부터 limit개 가져온다. source로 전사/팀 레드마인 중 어느 서버에서 가져올지
    정한다. 열린 것만 따로 구분하지 않는 이유는, 목록 위 검색창에서 닫힌 이슈까지 같이
    검색되게 하기 위함이다. (issues 리스트, 전체 이슈 개수) 튜플을 반환하며, 실패/미설정
    시 ([], 0)을 반환한다."""
    base_url, api_key = redmine_server(source)
    if not api_key:
        return [], 0

    url = (
        f"{base_url}/issues.json"
        f"?project_id={project_id}&status_id=*&sort=id:desc&limit={limit}&offset={offset}"
    )
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return [], 0

    issues = [
        {
            "issue_id": i.get("id"),
            "title": i.get("subject", ""),
            "url": f"{base_url}/issues/{i.get('id')}",
            "tracker": i.get("tracker", {}).get("name", ""),
            "priority": i.get("priority", {}).get("name", ""),
        }
        for i in data.get("issues", [])
    ]
    return issues, data.get("total_count", len(issues))


def fetch_versions_meta(project_id, api_key=None):
    """{버전id: {"name":, "due_date":, "created_on":, "status":}} 를 돌려준다.

    이슈 조회(issues.json)가 딸려 보내주는 fixed_version에는 id와 이름밖에 없어서,
    종료일/생성일/상태는 프로젝트의 버전 목록을 따로 받아야 알 수 있다. created_on은
    타임스탬프("2026-01-05T02:00:00Z")로 오길래 날짜만 잘라 쓴다(team_progress
    간트차트가 날짜 단위로만 쓴다). 실패하면 빈 dict - 날짜만 못 붙을 뿐 나머지는
    그대로 나오게 한다."""
    api_key = api_key or load_redmine_api_key()
    if not api_key:
        return {}

    url = f"{REDMINE_BASE_URL}/projects/{project_id}/versions.json"
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return {}

    return {
        v.get("id"): {
            "name": v.get("name", ""),
            "due_date": v.get("due_date"),
            "created_on": (v.get("created_on") or "")[:10] or None,
            "status": v.get("status", "open"),
        }
        for v in data.get("versions", [])
    }


def fetch_issues_by_version(project_id):
    """레드마인 REST API로 특정 프로젝트의 배포 버전(fixed_version)마다 연결된 이슈를
    가져와 묶어 반환한다. 상태는 가리지 않고(status_id=*) 닫힌 이슈까지 다 포함한다.

    버전 목록을 먼저 받고 버전마다 그 버전에 연결된 이슈를 따로 조회하는 방식이다.
    예전엔 그 프로젝트의 "최근 갱신된 이슈 300건"만 훑어서 거기 걸린 버전만 화면에
    보여줬는데, 완료(닫힘)된 버전은 이슈가 오래전에 멈춰 있어 그 300건 밖으로 밀려나
    로드맵 자체가 통째로 안 보이는 문제가 있었다 - 버전을 기준으로 조회하면 이슈가
    얼마나 오래됐든 다 잡힌다.
    실패/미설정 시 빈 리스트를 반환.
    반환 형식: [{"version": str, "due_date": str|None,
                 "issues": [{"id":, "subject":, "url":, "status":, "closed":}, ...]}, ...]"""
    api_key = load_redmine_api_key()
    if not api_key:
        return []

    versions_meta = fetch_versions_meta(project_id, api_key)
    if not versions_meta:
        return []

    # 버전마다 순서대로 이슈를 조회하면 버전 개수만큼 시간이 곱해져 너무 느려진다
    # (버전이 많은 프로젝트는 실제로 몇십 초씩 걸렸다) - 몇 개씩 동시에 물어서
    # 기다리는 시간을 줄인다. 그렇다고 전부 한꺼번에 쏘면 레드마인 서버에 부담이라
    # 동시 개수는 적당히 제한한다.
    issues_by_id = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_fetch_version_issues, vid, project_id, api_key): vid
            for vid in versions_meta
        }
        for future in as_completed(futures):
            issues_by_id[futures[future]] = future.result()

    result = []
    for vid in sorted(versions_meta):
        issues = issues_by_id.get(vid) or []
        if not issues:
            continue  # 이 프로젝트에 연결된 일감이 없는 버전은 이 화면 대상이 아니다
        meta = versions_meta[vid]
        result.append({
            "version": meta.get("name", ""),
            "due_date": meta.get("due_date"),
            "issues": issues,
        })
    return result


def _fetch_version_issues(version_id, project_id, api_key):
    """버전 하나에 연결된 이슈 중 이 프로젝트 "자신" 소속인 것만 전부(닫힌 것 포함,
    페이징 없이 끝까지) 가져온다.

    project_id로 좁히는 이유: 공유 범위가 "모든 프로젝트"인 버전은 다른 프로젝트의
    이슈도 같은 버전에 걸릴 수 있어서, project_id 없이 fixed_version_id만 물으면
    그 버전을 실제로 만든/쓰는 다른 프로젝트의 이슈까지 섞여 들어온다.

    subproject_id=!*를 붙이는 이유: 레드마인 REST API는 project_id만 주면 기본으로
    "하위 프로젝트의 이슈까지" 같이 돌려준다. App._resolved_targets가 최상위를
    고르면 하위 프로젝트를 이미 하나하나 따로 훑고 있어서, 여기서 하위까지 같이
    받으면 그 이슈가 자기 프로젝트 몫과 조상 프로젝트 몫 양쪽에 중복으로 잡히고,
    "어느 프로젝트 건지" 표시도 조상 이름으로 잘못 붙는다 - 그게 로드맵/프로젝트
    표시가 뒤섞여 보이던 원인이었다."""
    issues = []
    offset = 0
    limit = 100
    while True:
        url = (
            f"{REDMINE_BASE_URL}/issues.json"
            f"?project_id={project_id}&subproject_id=!*&fixed_version_id={version_id}"
            f"&status_id=*&sort=id:desc&limit={limit}&offset={offset}"
        )
        req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError):
            break

        batch = data.get("issues", [])
        issues.extend(batch)
        offset += limit
        if not batch or offset >= data.get("total_count", 0):
            break

    return [
        {
            "id": i.get("id"),
            "subject": i.get("subject", ""),
            "url": f"{REDMINE_BASE_URL}/issues/{i.get('id')}",
            "status": i.get("status", {}).get("name", ""),
            # 상태 "이름"만으로는 끝난 일감인지 알 수 없다(레드마인마다 완료 상태
            # 이름이 다름) - closed_on이 찍혔는지로 판단해서 버전 진행률을 센다.
            "closed": bool(i.get("closed_on")),
        }
        for i in issues
    ]


def fetch_org_progress(pairs):
    """팀별 진행상황 화면(team_progress.js)에서 쓴다. (project_id, 팀/프로젝트명)
    목록을 받아 프로젝트마다 배포 버전(fixed_version)에 연결된 이슈를 모아 버전별
    진행률을 계산해 돌려준다 - fetch_issues_by_version과 같은 소스(이슈 목록)를
    보되, 일감 하나하나가 아니라 버전 단위 집계(완료 건수/퍼센트)로 쓴다는 점이 다르다.
    반환 형식: [{"team": str, "team_id": int, "versions": [
        {"version":, "created_on":, "due_date":, "total":, "closed":, "percent":, "url":},
        ...]}, ...] (main.py App.get_team_progress가 팀 depth 2 소그룹으로 다시 쪼갠다).
    실패/미설정 시 프로젝트마다 versions: [] 로 채워서 화면이 죽지 않게 한다."""
    api_key = load_redmine_api_key()
    return [
        {"team": name, "team_id": pid, "versions": _fetch_version_progress(pid, api_key)}
        for pid, name in pairs
    ]


def _fetch_version_progress(project_id, api_key):
    if not api_key:
        return []

    issues = []
    offset = 0
    limit = 100
    max_issues = 300
    while offset < max_issues:
        url = (
            f"{REDMINE_BASE_URL}/issues.json"
            f"?project_id={project_id}&status_id=*&limit={limit}&offset={offset}"
        )
        req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError):
            break

        batch = data.get("issues", [])
        issues.extend(batch)
        offset += limit
        if not batch or offset >= data.get("total_count", 0):
            break

    versions_meta = fetch_versions_meta(project_id, api_key)

    groups = {}  # 버전id -> {"name":, "total":, "closed":}
    order = []
    for i in issues:
        version = i.get("fixed_version") or {}
        vid = version.get("id")
        if not vid or not version.get("name"):
            continue  # 버전에 연결 안 된 일감은 이 화면 대상이 아니다
        if vid not in groups:
            groups[vid] = {"name": version.get("name"), "total": 0, "closed": 0}
            order.append(vid)
        groups[vid]["total"] += 1
        if i.get("closed_on"):
            groups[vid]["closed"] += 1

    result = []
    for vid in order:
        g = groups[vid]
        meta = versions_meta.get(vid, {})
        total = g["total"]
        closed = g["closed"]
        result.append({
            "version": g["name"],
            "created_on": meta.get("created_on"),
            "due_date": meta.get("due_date"),
            "total": total,
            "closed": closed,
            "percent": round(closed / total * 100) if total else 0,
            "url": f"{REDMINE_BASE_URL}/versions/{vid}",
        })
    return result


def fetch_calendar_versions(pairs):
    """배포 달력 화면이 쓴다. (project_id, project_name, source) 목록을 받아
    프로젝트마다 버전 목록을 조회해 종료일이 잡힌 것만 종료일 오름차순 평면
    목록으로 돌려준다(종료일 없는 버전은 달력에 찍을 자리가 없어 아예 뺀다).
    조회에 실패한 프로젝트는 조용히 건너뛴다 - 달력은 일부만이라도 보이는 게
    통째로 비는 것보다 낫다.

    프로젝트마다 순서대로 조회하면 즐겨찾기 개수만큼 시간이 곱해져 느려지므로,
    fetch_issues_by_version과 같은 방식으로 몇 개씩 동시에 물어서 기다리는 시간을 줄인다.
    반환 형식: [{"version_id":, "version":, "project":, "project_id":, "source":,
                 "due_date":, "status": "open"/"locked"/"closed", "url":}, ...]"""
    rows = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch_calendar_versions_for_project, pair) for pair in pairs]
        for future in as_completed(futures):
            rows.extend(future.result())

    rows.sort(key=lambda r: (r["due_date"], r["project"], r["version"]))
    return rows


def _fetch_calendar_versions_for_project(pair):
    project_id, project_name, source = pair
    base_url, api_key = redmine_server(source)
    if not api_key:
        return []

    url = f"{base_url}/projects/{project_id}/versions.json"
    req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return []

    rows = []
    for v in data.get("versions", []):
        # /projects/:id/versions.json은 이 프로젝트가 만든 버전뿐 아니라, 공유
        # 범위(sharing)가 "모든 프로젝트"인 다른 프로젝트의 버전까지 같이 돌려준다.
        # 그대로 쓰면 즐겨찾기한 프로젝트마다 같은 버전이 중복으로(그것도 엉뚱한
        # project_name을 달고) 찍히니, 실제로 그 버전을 만든 프로젝트일 때만 담는다.
        owner_id = (v.get("project") or {}).get("id")
        if owner_id is not None and owner_id != project_id:
            continue
        due_date = v.get("due_date")
        if not due_date:
            continue
        rows.append({
            "version_id": v.get("id"),
            "version": v.get("name", ""),
            "project": project_name,
            "project_id": project_id,
            "source": source,
            "due_date": due_date,
            "status": v.get("status", "open"),
            "url": f"{base_url}/versions/{v.get('id')}",
        })
    return rows


def fetch_version_issue_counts(version_id, source="company"):
    """배포 달력에서 날짜를 눌렀을 때 그 날 나가는 버전에 연결된 일감 진행률을
    센다. 반환 형식: {"total":, "closed":}. 실패하면 None을 반환한다(빈 결과와
    구분해 화면이 진행률 자리만 빼고 나머지는 그대로 보여주게 한다)."""
    base_url, api_key = redmine_server(source)
    if not api_key:
        return None

    issues = []
    total_count = 0
    offset = 0
    limit = 100
    max_issues = 300
    while offset < max_issues:
        url = (
            f"{base_url}/issues.json"
            f"?fixed_version_id={version_id}&status_id=*&limit={limit}&offset={offset}"
        )
        req = urllib.request.Request(url, headers={"X-Redmine-API-Key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError):
            return None

        batch = data.get("issues", [])
        issues.extend(batch)
        total_count = data.get("total_count", len(issues))
        offset += limit
        if not batch or offset >= total_count:
            break

    closed = sum(1 for i in issues if i.get("closed_on"))
    return {"total": total_count, "closed": closed}


def search_query_words(query):
    """검색어를 단어 단위로 쪼갠다. 공백뿐 아니라 "/", "," 같은 구분자도 단어 경계로
    본다 - "VoLTE/PSVT"처럼 붙여 쓴 검색어도 "VoLTE"와 "PSVT"를 각각의 단어로 다뤄서
    (all_words) 둘 다 포함된 이슈를 찾을 수 있게 하기 위함이다."""
    return [w for w in re.split(r"[\s/,]+", query) if w]


def search_project_issues(project_id, query, source="company"):
    """레드마인 자체 검색(/projects/:id/search.json)으로 해당 프로젝트의 이슈를
    "제목"만 대상으로 검색한다(titles_only=1). 완료/닫힌 이슈까지 포함한다.
    source로 전사/팀 레드마인 중 어느 서버에서 검색할지 정한다.
    실패 시 None을 반환(빈 결과와 구분해 이번 검색은 건너뛰기 위함)."""
    base_url, api_key = redmine_server(source)
    if not api_key or not query:
        return None

    # "/", "," 등도 단어 구분자로 보고 공백으로 바꿔서 보낸다("VoLTE/PSVT"도
    # "VoLTE"와 "PSVT"가 따로 다 들어간 이슈를 찾을 수 있게).
    # open_issues 파라미터를 아예 안 보내면 레드마인 기본값(열림+닫힘 모두 검색)이 적용된다.
    # all_words=1: 검색어에 공백으로 여러 단어가 있으면 "하나라도 포함(OR)"이 아니라
    # "전부 포함(AND)"인 것만 찾는다(레드마인 웹 검색창의 "All words" 체크와 동일).
    # titles_only=1: 본문·댓글까지 뒤지면 제목엔 없는 단어가 본문/댓글에만 있어도 걸려서
    # (검색창은 "제목 검색"이라고 안내하는데) 결과가 제목과 안 맞아 보이는 문제가 있었다 -
    # 레드마인 웹 검색창의 "Titles only" 체크와 동일하게 제목만 대상으로 좁힌다.
    normalized_query = " ".join(search_query_words(query))
    url = (
        f"{base_url}/projects/{project_id}/search.json"
        f"?q={urllib.parse.quote(normalized_query)}&issues=1&all_words=1&titles_only=1&limit=100"
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
            "url": f"{base_url}/issues/{match.group(1)}",
        })
    return results


def build_project_tree(projects):
    """평면 프로젝트 리스트를 parent_id 기준으로 최상위→하위 트리로 묶는다.
    각 레벨은 이름 기준 오름차순으로 정렬한다."""
    by_parent = {}
    for p in projects:
        by_parent.setdefault(p["parent_id"], []).append(p)

    def attach(node):
        node["children"] = sorted(by_parent.get(node["id"], []), key=lambda n: n["name"])
        for child in node["children"]:
            attach(child)
        return node

    roots = sorted(by_parent.get(None, []), key=lambda n: n["name"])
    return [attach(root) for root in roots]


def load_favorites():
    if not FAVORITES_FILE.exists():
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            favorites = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    # "source"가 아직 없는 예전 즐겨찾기 항목(팀 레드마인 구분 기능 도입 전)은
    # 저장된 url로 어느 서버 것인지 추론해 채워 넣는다.
    for f in favorites:
        if "source" not in f:
            f["source"] = "team" if f.get("url", "").startswith(TEAM_REDMINE_BASE_URL) else "company"
    return favorites


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


def _load_json_cache(path):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json_cache(path, cache):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 캐시 저장 실패로 화면이 멈출 이유는 없다 - 이번 회차만 캐시 없이 다시 받는다


def load_resolved_by_version_cache():
    """{프로젝트id(str): fetch_issues_by_version 반환값} - "버전별 연결된 일감" 패널이
    프로젝트를 고를 때마다 레드마인 응답을 기다리지 않고 지난 결과부터 보여주는 데 쓴다."""
    return _load_json_cache(RESOLVED_BY_VERSION_CACHE_FILE)


def save_resolved_by_version_cache(cache):
    _save_json_cache(RESOLVED_BY_VERSION_CACHE_FILE, cache)


def load_team_progress_cache():
    """{프로젝트id(str): get_team_progress 반환값} - "팀별 진행상황" 패널이 조직/팀을
    고를 때마다 레드마인 응답을 기다리지 않고 지난 결과부터 보여주는 데 쓴다."""
    return _load_json_cache(TEAM_PROGRESS_CACHE_FILE)


def save_team_progress_cache(cache):
    _save_json_cache(TEAM_PROGRESS_CACHE_FILE, cache)


def load_calendar_cache():
    """배포 달력이 마지막으로 받아온 결과 - "버전별 연결된 일감"/"팀별 진행상황"과
    달리 프로젝트별로 나누지 않고 즐겨찾기 전체를 한 번에 다루므로 리스트 하나만
    저장한다. 파일이 없으면(한 번도 저장한 적 없음) None을 돌려줘서, 빈 리스트("배포
    예정 없음"으로 이미 확인됨)와 구분한다 - main.py의 App._render_calendar가 이
    구분으로 "불러오는 중"과 "없음"을 가른다."""
    if not CALENDAR_CACHE_FILE.exists():
        return None
    try:
        with open(CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_calendar_cache(versions):
    try:
        with open(CALENDAR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(versions, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_my_issues_cache():
    """"할당된 일감"이 마지막으로 받아온 목록(fetch_my_issues 반환값과 같은 모양).
    달력과 달리 "아직 못 받아옴"과 "없음"을 화면에서 구분하지 않으므로(빈 목록이면
    그냥 비어 보인다) 파일이 없으면 빈 리스트를 돌려준다."""
    if not MY_ISSUES_CACHE_FILE.exists():
        return []
    try:
        with open(MY_ISSUES_CACHE_FILE, "r", encoding="utf-8") as f:
            cached = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return cached if isinstance(cached, list) else []


def save_my_issues_cache(issues):
    try:
        with open(MY_ISSUES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_favorite_issues_cache():
    """즐겨찾기 프로젝트별 이슈 목록/전체 개수를 (issues, totals) 튜플로 돌려준다.
    둘 다 f"{source}:{id}" 키를 쓰는 dict다(main.py App.favorite_issues /
    favorite_issue_totals 와 같은 모양). 개수는 목록보다 클 수 있어서(처음엔 최근
    200건만 받는다) 같이 저장해야 "더 보기"가 캐시만으로도 제대로 뜬다."""
    cache = _load_json_cache(FAVORITE_ISSUES_CACHE_FILE)
    issues = cache.get("issues")
    totals = cache.get("totals")
    return (
        issues if isinstance(issues, dict) else {},
        totals if isinstance(totals, dict) else {},
    )


# 즐겨찾기 이슈 캐시도 여러 스레드가 같이 쓴다 - 배경 조회(refresh_favorite_issues의
# worker)와 화면에서 부르는 "더 보기"/즐겨찾기 해제가 겹칠 수 있어, 쓰다 만 파일이
# 남지 않게 잠금을 건다.
_favorite_issues_cache_lock = threading.Lock()


def save_favorite_issues_cache(issues, totals):
    with _favorite_issues_cache_lock:
        _save_json_cache(FAVORITE_ISSUES_CACHE_FILE, {"issues": issues, "totals": totals})


# 전사/팀 프로젝트 목록은 서로 다른 스레드가 각자 받아와 같은 파일에 쓴다
# (main.py App.refresh_trees의 worker_company / worker_team) - 한쪽이 읽고 쓰는
# 사이에 다른 쪽이 끼어들면 먼저 쓴 결과가 통째로 날아가므로 잠금을 건다.
_projects_cache_lock = threading.Lock()


def load_projects_cache():
    """{"company": [평면 프로젝트 리스트], "team": [...]} - 트리로 묶기 전 모양
    그대로 저장해 둔다(build_project_tree가 children을 붙이면서 같은 dict를 다시
    쓰기 때문에, 트리째 저장하면 같은 프로젝트가 중첩돼 파일이 커진다)."""
    cache = _load_json_cache(PROJECTS_CACHE_FILE)
    return {
        source: cache.get(source) if isinstance(cache.get(source), list) else []
        for source in ("company", "team")
    }


def save_projects_cache(source, projects):
    """한쪽(전사 또는 팀)만 갱신한다 - 다른 쪽 조회가 아직이거나 실패했어도 그쪽
    캐시는 그대로 남겨야 한다."""
    # build_project_tree는 넘겨받은 dict에 children을 직접 달아둔다 - 트리를 만든
    # 뒤의 리스트를 그대로 저장하면 같은 프로젝트가 children 안에 통째로 또 들어가
    # 파일이 몇 배로 부푼다. 저장할 때 children만 떼어낸다.
    flat = [{k: v for k, v in p.items() if k != "children"} for p in projects]
    with _projects_cache_lock:
        cache = _load_json_cache(PROJECTS_CACHE_FILE)
        cache[source] = flat
        _save_json_cache(PROJECTS_CACHE_FILE, cache)
