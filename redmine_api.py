"""
레드마인 REST API 호출/데이터 저장 함수 모음 - 프로젝트/이슈 조회, 검색, 즐겨찾기·확인한
이슈 목록 저장/불러오기 등. tkinter나 그리기 관련 코드는 없고 순수 데이터 계층이다.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from config import (
    FAVORITES_FILE,
    REDMINE_API_KEY_FILE,
    REDMINE_API_KEY_PLACEHOLDER,
    REDMINE_BASE_URL,
    REDMINE_USER_ID_FILE,
    SEEN_ISSUES_FILE,
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


def redmine_server(source):
    """즐겨찾기 프로젝트의 출처("company"=전사 레드마인, "team"=팀 레드마인)에 맞는
    (base_url, api_key)를 돌려준다. 두 서버가 별도 API 키를 쓰기 때문에 필요하다."""
    if source == "team":
        return TEAM_REDMINE_BASE_URL, load_team_redmine_api_key()
    return REDMINE_BASE_URL, load_redmine_api_key()


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
    """레드마인 REST API로 특정 프로젝트의 최근 이슈 목록(id, 제목, url)을 가져온다.
    source로 전사/팀 레드마인 중 어느 서버에서 가져올지 정한다.
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
    이슈 목록(id 내림차순)을 가져온다. 상태가 "완료"인 이슈는 목록에서 제외한다.
    identifier가 없으면(아직 설정 전) 빈 리스트를 반환.

    조회에 실패하면 fetch_recent_issues와 같이 None을 반환한다 - 빈 목록과 꼭
    구분해야 한다. 잠깐의 실패를 "할당된 일감 없음"으로 받아들이면 배지가 0으로
    깜빡일 뿐 아니라, 알림 기준이 되는 "이미 본 일감" 목록까지 비워져서 다음
    회차에 갖고 있던 일감 전부가 새로 할당된 것처럼 토스트로 쏟아진다
    (main.py의 _notify_new_my_issues 참고)."""
    if not identifier:
        return []
    api_key = load_redmine_api_key()
    if not api_key:
        return None

    user_id = resolve_user_id(identifier)
    if not user_id:
        return None  # 아이디 조회 자체가 HTTP 호출이라, 일시적인 실패일 수 있다

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


def fetch_version_due_dates(project_id, api_key=None):
    """{버전id: 종료일("YYYY-MM-DD" 또는 None)} 를 돌려준다.

    이슈 조회(issues.json)가 딸려 보내주는 fixed_version에는 id와 이름밖에 없어서,
    종료일은 프로젝트의 버전 목록을 따로 받아야 알 수 있다. 실패하면 빈 dict -
    종료일만 못 붙을 뿐 일감 목록은 그대로 나오게 한다."""
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

    return {v.get("id"): v.get("due_date") for v in data.get("versions", [])}


def fetch_issues_by_version(project_id):
    """레드마인 REST API로 특정 프로젝트에서 배포 버전(fixed_version)에 연결된 이슈를
    가져와 버전별로 묶어 반환한다. 상태는 가리지 않고(status_id=*) 진행 중인 것까지 다
    포함하며, 버전이 지정 안 된 이슈는 아예 제외한다("버전별 연결된 일감"이라는 화면
    이름 그대로). 실패/미설정 시 빈 리스트를 반환.
    반환 형식: [{"version": str, "due_date": str|None,
                 "issues": [{"id":, "subject":, "url":, "status":, "closed":}, ...]}, ...]"""
    api_key = load_redmine_api_key()
    if not api_key:
        return []

    issues = []
    offset = 0
    limit = 100
    max_issues = 300
    while offset < max_issues:
        url = (
            f"{REDMINE_BASE_URL}/issues.json"
            f"?project_id={project_id}&status_id=*&sort=updated_on:desc&limit={limit}&offset={offset}"
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

    due_by_version_id = fetch_version_due_dates(project_id, api_key)

    groups = {}
    version_ids = {}  # 버전명 -> 버전id (종료일을 붙이는 데 쓴다)
    order = []
    for i in issues:
        # fixed_version 키 자체가 없을 수도, 값이 null일 수도 있어서 양쪽 다 대비한다
        version = i.get("fixed_version") or {}
        version_name = version.get("name")
        if not version_name:
            continue  # 버전에 연결 안 된 일감은 이 화면 대상이 아니다
        if version_name not in groups:
            groups[version_name] = []
            version_ids[version_name] = version.get("id")
            order.append(version_name)
        groups[version_name].append({
            "id": i.get("id"),
            "subject": i.get("subject", ""),
            "url": f"{REDMINE_BASE_URL}/issues/{i.get('id')}",
            "status": i.get("status", {}).get("name", ""),
            # 상태 "이름"만으로는 끝난 일감인지 알 수 없다(레드마인마다 완료 상태
            # 이름이 다름) - closed_on이 찍혔는지로 판단해서 버전 진행률을 센다.
            "closed": bool(i.get("closed_on")),
        })

    return [
        {
            "version": version_name,
            "due_date": due_by_version_id.get(version_ids[version_name]),
            "issues": groups[version_name],
        }
        for version_name in order
    ]


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
