// 파이썬(App._push_issues)이 호출하는 진입점.
// data: {kind, title, groups: [{project, issues:[{issue_id,title,url,tracker,priority}],
//                                section?, project_id?, source?, total?}]}
let currentKind = null;
let currentGroups = [];
let selectedIndex = -1;
let activeFilter = null;
let searchMode = false;
let rightIssuesBase = [];  // 현재 오른쪽에 보여줄 "필터 적용 전" 원본 목록
let loadingMore = false;
let searchToken = 0;
let searchWords = [];  // 검색 중일 때 결과 제목에서 <mark>로 강조할 단어들

const TRACKER_COLORS = {
    "VoC": ["#FBE0E9", "#A23F63"],
    "결함": ["#FBDBDB", "#B3382E"],
    "개발": ["#DCEBFB", "#2D5F8A"],
    "기술문의": ["#D6F0FB", "#1D6E8C"],
    "기타": ["#EFEFF2", "#6B6B76"],
    "디자인": ["#E9DFFB", "#6440A5"],
    "분석": ["#D9F3EC", "#1F7A63"],
    "업무내용": ["#FBF0D2", "#93701B"],
    "요구사항": ["#E1E6FB", "#3D4FA0"],
    "이슈": ["#FDE7D3", "#9A5B22"],
    "접수": ["#E3F5D8", "#3F7D20"],
};
const TRACKER_FALLBACK = ["#E7E4F2", "#5C5470"];
// 검색 결과가 전사/팀 레드마인 두 서버 결과를 한 목록에 섞어 보여줄 때, 어느 서버에서
// 온 이슈인지 구분해주는 뱃지 색(파이썬 main.py SECTION_LABEL과 문구를 맞춘다).
const SOURCE_COLORS = {
    "레드마인(150)": ["#DCE4F5", "#1F3864"],
    "레드마인(20)": ["#DCF5E4", "#1F5C3A"],
};
const PRIORITY_COLORS = {
    "낮음": ["#E7ECF5", "#5A6B85"],
    "보통": ["#E9E7EE", "#5C5470"],
    "높음": ["#FBDCDA", "#C1392B"],
    "긴급": ["#F8C9C5", "#A8281A"],
    "즉시": ["#F3B0AA", "#7A160C"],
};

function renderIssuesPanel(data) {
    currentKind = data.kind;
    currentGroups = data.groups || [];
    selectedIndex = -1;
    activeFilter = null;
    searchMode = false;
    searchWords = [];
    rightIssuesBase = [];
    document.getElementById("searchInput").value = "";
    // "전체 프로젝트" 토글은 즐겨찾기 검색에서만 의미가 있다("할당된 일감"은 이미
    // 전체 프로젝트 대상의 내 일감 목록이라 좁히고 넓힐 대상이 없다).
    const allProjectsToggle = document.getElementById("allProjectsToggle");
    allProjectsToggle.classList.toggle("hidden", currentKind !== "favorites");
    document.getElementById("allProjectsCheck").checked = false;
    renderFilterRow();
    renderLeft();
    renderRight();
}

function renderFilterRow() {
    const row = document.getElementById("filterRow");
    row.innerHTML = "";
    // 색은 CSS(.filter-btn)에서만 준다 - 뱃지는 회색, 고른 것만 강조색.
    // 유형별 고유색(TRACKER_COLORS)은 일감 목록의 뱃지에만 쓰고 여기선 이름만 가져다 쓴다.
    Object.keys(TRACKER_COLORS).forEach((name) => {
        const btn = document.createElement("button");
        btn.className = "filter-btn" + (name === activeFilter ? " active" : "");
        btn.textContent = name;
        btn.addEventListener("click", () => {
            activeFilter = activeFilter === name ? null : name;
            renderFilterRow();
            renderRight();
        });
        row.appendChild(btn);
    });
}

function renderLeft() {
    const left = document.getElementById("left");
    left.innerHTML = "";
    if (currentGroups.length === 0) {
        left.innerHTML = '<div class="placeholder">표시할 프로젝트가 없습니다.</div>';
        return;
    }
    let lastSection = null;
    currentGroups.forEach((g, i) => {
        if (g.section && g.section !== lastSection) {
            const head = document.createElement("div");
            head.className = "section";
            head.textContent = g.section;
            left.appendChild(head);
            lastSection = g.section;
        }
        const card = document.createElement("div");
        card.className = "project-card" + (!searchMode && i === selectedIndex ? " selected" : "");
        // 즐겨찾기 창에서만 이름 앞에 별을 붙인다 - 여기 뜨는 프로젝트는 전부 이미 즐겨찾기된
        // 것들이라 항상 채워진 별로 보여주고, 누르면 해제한다("할당된 일감" 창은 즐겨찾기와
        // 무관한 목록이라 별이 없다).
        if (currentKind === "favorites" && g.project_id != null && g.source) {
            card.appendChild(makeFavStar(g));
        }
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = g.project;
        const count = document.createElement("span");
        count.className = "count";
        count.textContent = String(g.total != null ? g.total : g.issues.length);
        card.appendChild(name);
        card.appendChild(count);
        if (g.project_id != null && g.notify != null) {
            card.appendChild(makeBell(g));
        }
        card.addEventListener("click", () => {
            searchMode = false;
            selectedIndex = i;
            rightIssuesBase = currentGroups[i].issues;
            renderLeft();
            renderRight();
        });
        left.appendChild(card);
    });
}

// 즐겨찾기 프로젝트 카드 왼쪽의 별 - 누르면 즐겨찾기 해제. toggle_favorite이 해제되면
// 파이썬 쪽에서 곧바로 _push_issues()로 패널 전체를 다시 그려주므로(App.toggle_favorite
// 참고), 여기선 목록에서 직접 빼지 않고 API만 호출한다.
function makeFavStar(group) {
    const star = document.createElement("span");
    star.className = "fav-star";
    star.textContent = "★";
    star.title = "즐겨찾기 해제";
    star.addEventListener("click", (event) => {
        event.stopPropagation();  // 카드 클릭(프로젝트 선택)까지 같이 먹지 않게
        window.pywebview.api.toggle_favorite(group.project_id, group.project, group.url || "", group.source);
    });
    return star;
}

// 즐겨찾기 프로젝트 카드 오른쪽의 종 - 그 프로젝트의 새 이슈 토스트 알림을 켜고 끈다
// (파이썬 App._check_new_issues가 이 값을 보고 조회 대상에서 뺀다).
function makeBell(group) {
    const bell = document.createElement("span");

    function paint() {
        bell.className = "bell " + (group.notify ? "on" : "off");
        bell.title = group.notify ? "새 일감 알림 켜짐 - 누르면 끕니다" : "새 일감 알림 꺼짐 - 누르면 켭니다";
    }
    paint();

    bell.addEventListener("click", (event) => {
        event.stopPropagation();  // 카드 클릭(프로젝트 선택)까지 같이 먹지 않게
        window.pywebview.api.toggle_notify(group.project_id, group.source).then((on) => {
            group.notify = on;
            paint();
        });
    });
    return bell;
}

function filteredIssues() {
    if (!activeFilter) return rightIssuesBase;
    return rightIssuesBase.filter((issue) => issue.tracker === activeFilter);
}

function renderRight() {
    const right = document.getElementById("right");
    right.innerHTML = "";
    right.onscroll = null;

    if (!searchMode && selectedIndex < 0) {
        right.innerHTML = '<div class="placeholder">왼쪽에서 프로젝트를 선택하세요.</div>';
        return;
    }
    const issues = filteredIssues();
    if (issues.length === 0) {
        right.innerHTML = '<div class="placeholder">일감이 없습니다.</div>';
        return;
    }
    issues.forEach((issue) => right.appendChild(renderIssueRow(issue)));

    // 즐겨찾기 프로젝트 하나를 보고 있고(검색 중 아님), 아직 다 안 불러온 상태면
    // 스크롤이 바닥에 닿을 때 다음 페이지를 이어서 불러온다.
    if (!searchMode && selectedIndex >= 0) {
        const group = currentGroups[selectedIndex];
        if (group.project_id != null && group.total != null && group.issues.length < group.total) {
            right.onscroll = () => {
                if (loadingMore) return;
                if (right.scrollTop + right.clientHeight >= right.scrollHeight - 40) {
                    loadMore(group);
                }
            };
        }
    }
}

function loadMore(group) {
    loadingMore = true;
    window.pywebview.api.load_more_issues(group.project_id, group.source, group.issues.length)
        .then((result) => {
            loadingMore = false;
            if (!result || !result.issues || result.issues.length === 0) return;
            group.issues = group.issues.concat(result.issues);
            group.total = result.total;
            if (currentGroups[selectedIndex] === group) {
                rightIssuesBase = group.issues;
                const right = document.getElementById("right");
                const filtered = activeFilter
                    ? result.issues.filter((i) => i.tracker === activeFilter)
                    : result.issues;
                filtered.forEach((issue) => right.appendChild(renderIssueRow(issue)));
                if (group.issues.length >= group.total) {
                    right.onscroll = null;
                }
            }
        })
        .catch(() => { loadingMore = false; });
}

function renderIssueRow(issue) {
    const row = document.createElement("div");
    row.className = "issue-row";

    if (issue.source_label) {
        const [bg, fg] = SOURCE_COLORS[issue.source_label] || TRACKER_FALLBACK;
        row.appendChild(makePill(issue.source_label, bg, fg));
    }
    if (issue.tracker) {
        const [bg, fg] = TRACKER_COLORS[issue.tracker] || TRACKER_FALLBACK;
        row.appendChild(makePill(issue.tracker, bg, fg));
    }
    if (issue.priority && PRIORITY_COLORS[issue.priority]) {
        const [bg, fg] = PRIORITY_COLORS[issue.priority];
        row.appendChild(makePill(issue.priority, bg, fg));
    }

    const text = document.createElement("span");
    text.className = "issue-text";
    text.appendChild(document.createTextNode(`#${issue.issue_id}  `));
    if (searchMode && searchWords.length) {
        // 검색 중일 때만 검색어를 <mark>로 감싼다 - 레드마인에서 온 제목이라
        // innerHTML을 쓰는 부분은 반드시 escapeHtml을 거쳐야 한다(XSS 방지).
        const titlePart = document.createElement("span");
        titlePart.innerHTML = highlightText(issue.title, searchWords);
        text.appendChild(titlePart);
    } else {
        text.appendChild(document.createTextNode(issue.title));
    }
    row.appendChild(text);

    row.addEventListener("click", () => window.pywebview.api.open_url(issue.url));
    return row;
}

function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

function escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// 검색창의 단어 구분 규칙(공백/"/"/",")과 맞춰서 하이라이트 대상 단어를 뽑는다
// (파이썬 search_query_words와 동일한 규칙 - "VoLTE/PSVT"도 두 단어로 각각 강조).
function splitQueryWords(query) {
    return query.split(/[\s/,]+/).filter(Boolean);
}

function highlightText(text, words) {
    const escaped = escapeHtml(text);
    if (!words.length) return escaped;
    const pattern = words.map(escapeRegExp).join("|");
    const re = new RegExp(`(${pattern})`, "gi");
    return escaped.replace(re, "<mark>$1</mark>");
}

function makePill(text, bg, fg) {
    const span = document.createElement("span");
    span.className = "pill";
    span.style.background = bg;
    span.style.color = fg;
    span.textContent = text;
    return span;
}

// ── 검색(검색 버튼을 눌러야 실행 - 입력 중에는 검색하지 않는다) ──
const searchInput = document.getElementById("searchInput");
document.getElementById("searchBtn").addEventListener("click", fireSearch);
searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") fireSearch();
});
document.getElementById("allProjectsCheck").addEventListener("change", () => {
    if (searchInput.value.trim()) fireSearch();  // 검색 중이면 토글 즉시 반영
});

function fireSearch() {
    const query = searchInput.value.trim();
    const allProjects = document.getElementById("allProjectsCheck").checked;
    const token = ++searchToken;
    if (!query) {
        searchMode = false;
        searchWords = [];
        renderLeft();
        renderRight();
        return;
    }
    document.getElementById("right").innerHTML = '<div class="placeholder">검색 중...</div>';
    try {
        window.pywebview.api.search_issues(currentKind, query, allProjects).then((matches) => {
            if (token !== searchToken) return;  // 그 사이 다른 검색이 시작됐으면 버림
            searchMode = true;
            searchWords = splitQueryWords(query);
            selectedIndex = -1;
            rightIssuesBase = matches || [];
            renderLeft();
            renderRight();
        }).catch((err) => {
            document.getElementById("right").innerHTML =
                '<div class="placeholder">검색 오류: ' + String(err) + '</div>';
        });
    } catch (err) {
        document.getElementById("right").innerHTML =
            '<div class="placeholder">검색 호출 실패: ' + String(err) + '</div>';
    }
}
