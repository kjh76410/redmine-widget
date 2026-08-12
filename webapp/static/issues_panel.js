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
let searchDebounceTimer = null;
let searchToken = 0;

const TRACKER_COLORS = {
    "VoC": ["#FBE0E9", "#A23F63"],
    "결함": ["#FBDBDB", "#B3382E"],
    "개발": ["#DCEBFB", "#2D5F8A"],
    "디자인": ["#E9DFFB", "#6440A5"],
    "분석": ["#D9F3EC", "#1F7A63"],
    "업무내용": ["#FBF0D2", "#93701B"],
    "요구사항": ["#E1E6FB", "#3D4FA0"],
    "이슈": ["#FDE7D3", "#9A5B22"],
};
const TRACKER_FALLBACK = ["#E7E4F2", "#5C5470"];
const PRIORITY_COLORS = {
    "낮음": ["#E7ECF5", "#5A6B85"],
    "보통": ["#E9E7EE", "#5C5470"],
    "높음": ["#FBDCDA", "#C1392B"],
    "긴급": ["#F8C9C5", "#A8281A"],
    "즉시": ["#F3B0AA", "#7A160C"],
};

function renderIssuesPanel(data) {
    currentKind = data.kind;
    document.getElementById("title").textContent = data.title;
    currentGroups = data.groups || [];
    selectedIndex = -1;
    activeFilter = null;
    searchMode = false;
    rightIssuesBase = [];
    document.getElementById("searchInput").value = "";
    renderFilterRow();
    renderLeft();
    renderRight();
}

function renderFilterRow() {
    const row = document.getElementById("filterRow");
    row.innerHTML = "";
    Object.keys(TRACKER_COLORS).forEach((name) => {
        const [bg, fg] = TRACKER_COLORS[name];
        const btn = document.createElement("button");
        btn.className = "filter-btn" + (name === activeFilter ? " active" : "");
        btn.style.background = bg;
        btn.style.color = fg;
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
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = g.project;
        const count = document.createElement("span");
        count.className = "count";
        count.textContent = String(g.total != null ? g.total : g.issues.length);
        card.appendChild(name);
        card.appendChild(count);
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
    text.textContent = `#${issue.issue_id}  ${issue.title}`;
    row.appendChild(text);

    row.addEventListener("click", () => window.pywebview.api.open_url(issue.url));
    return row;
}

function makePill(text, bg, fg) {
    const span = document.createElement("span");
    span.className = "pill";
    span.style.background = bg;
    span.style.color = fg;
    span.textContent = text;
    return span;
}

// ── 검색(디바운스 350ms) ──────────────────────
const searchInput = document.getElementById("searchInput");
searchInput.addEventListener("keyup", () => {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(fireSearch, 350);
});

function fireSearch() {
    const query = searchInput.value.trim();
    const token = ++searchToken;
    if (!query) {
        searchMode = false;
        renderLeft();
        renderRight();
        return;
    }
    document.getElementById("right").innerHTML = '<div class="placeholder">검색 중...</div>';
    try {
        window.pywebview.api.search_issues(currentKind, query).then((matches) => {
            if (token !== searchToken) return;  // 그 사이 다른 검색이 시작됐으면 버림
            searchMode = true;
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
