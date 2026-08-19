// 파이썬(App._push_resolved_tree)이 호출하는 진입점: {tree} 형태의 데이터를 받는다.
// tree는 전사 레드마인 프로젝트 트리(회사 것만 - 원래 Tkinter 버전과 동일한 범위).
let selectedProjectRow = null;
let selectedProjectId = null;  // 지금 오른쪽에 펼쳐놓은 프로젝트의 id - updateVersionGroups가
                                // 그 사이 다른 걸 골랐으면(불일치) 백그라운드 새로고침 결과를 버리는 데 쓴다
let selectedVersionRow = null;
let selectedVersionGroup = null;
let versionGroups = [];
let yearFilter = null;  // null=전체, 그 외엔 연도(숫자) 또는 "none"(종료일 없는 버전)
let loadToken = 0;

// 프로젝트를 고를 때마다 연도 필터 기본값 - "지금 당장 뭐가 나가는지"가 제일 궁금한
// 화면이라, 처음엔 항상 올해 배지가 눌린 상태로 시작한다(전체를 보려면 눌러서 끄면 됨).
function currentYear() {
    return new Date().getFullYear();
}

// 상태 뱃지 색 - 일감 창의 유형/우선순위 뱃지와 같은 팔레트("연한 배경 + 진한 글자").
// 레드마인마다 상태 이름이 달라서 여기 없는 이름은 STATUS_FALLBACK으로 떨어진다.
const STATUS_COLORS = {
    "신규": ["#DCEBFB", "#2D5F8A"],
    "진행": ["#FBF0D2", "#93701B"],
    "진행중": ["#FBF0D2", "#93701B"],
    "피드백": ["#FDE7D3", "#9A5B22"],
    "검토": ["#FDE7D3", "#9A5B22"],
    "보류": ["#E9DFFB", "#6440A5"],
    "해결": ["#D9F3EC", "#1F7A63"],
    "완료": ["#E3F5D8", "#3F7D20"],
    "종료": ["#E3F5D8", "#3F7D20"],
    "거부": ["#EFEFF2", "#6B6B76"],
    "취소": ["#EFEFF2", "#6B6B76"],
};
const STATUS_FALLBACK = ["#E7E4F2", "#5C5470"];

function renderResolvedPanel(data) {
    const col = document.getElementById("colProject");
    col.innerHTML = "";
    selectedProjectRow = null;
    selectedProjectId = null;
    selectedVersionRow = null;
    selectedVersionGroup = null;
    versionGroups = [];
    yearFilter = null;
    document.getElementById("badgeVersion").innerHTML = "";
    renderPlaceholder("colVersion", "왼쪽에서 프로젝트를 선택하세요.");
    renderPlaceholder("colIssue", "프로젝트와 버전을 선택하세요.");

    if (!data.tree || data.tree.length === 0) {
        renderPlaceholder("colProject", "프로젝트 목록을 불러오는 중이거나 없습니다.");
        return;
    }
    data.tree.forEach((node) => col.appendChild(renderProjectNode(node, 0)));
}

function renderPlaceholder(colId, text) {
    const col = document.getElementById(colId);
    col.innerHTML = "";
    const p = document.createElement("div");
    p.className = "placeholder";
    p.textContent = text;
    col.appendChild(p);
}

function renderProjectNode(node, depth) {
    const wrap = document.createElement("div");

    const row = document.createElement("div");
    row.className = "row";
    row.style.paddingLeft = (depth * 16 + 4) + "px";

    const hasChildren = node.children && node.children.length > 0;
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = hasChildren ? "▸" : "";
    row.appendChild(arrow);

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = node.name;
    row.appendChild(label);

    const childWrap = document.createElement("div");
    childWrap.className = "children collapsed";
    if (hasChildren) {
        node.children.forEach((c) => childWrap.appendChild(renderProjectNode(c, depth + 1)));
    }

    let expanded = false;
    row.addEventListener("click", (e) => {
        if (hasChildren && e.target === arrow) {
            expanded = !expanded;
            arrow.textContent = expanded ? "▾" : "▸";
            childWrap.classList.toggle("collapsed", !expanded);
            return;
        }
        selectProject(node, row);
    });

    wrap.appendChild(row);
    wrap.appendChild(childWrap);
    return wrap;
}

function selectProject(node, row) {
    if (selectedProjectRow) selectedProjectRow.classList.remove("selected");
    row.classList.add("selected");
    selectedProjectRow = row;
    selectedProjectId = node.id;

    selectedVersionRow = null;
    selectedVersionGroup = null;
    versionGroups = [];
    yearFilter = currentYear();
    document.getElementById("badgeVersion").innerHTML = "";
    renderPlaceholder("colVersion", "불러오는 중...");
    renderPlaceholder("colIssue", "프로젝트와 버전을 선택하세요.");

    const token = ++loadToken;
    window.pywebview.api.get_resolved_by_version(node.id).then((groups) => {
        if (token !== loadToken) return;  // 그 사이 다른 프로젝트를 눌렀으면 버림
        versionGroups = groups || [];
        renderVersionCol();
    }).catch((err) => {
        if (token !== loadToken) return;
        renderPlaceholder("colVersion", "불러오기 실패: " + String(err));
    });
}

// 파이썬(App._refresh_resolved_by_version)이 캐시를 먼저 보여준 뒤 백그라운드로 새로
// 받아온 최신 데이터를 밀어줄 때 부르는 진입점. 그 사이 다른 프로젝트를 골랐으면 조용히
// 버린다. 버전을 하나 펼쳐 보고 있었으면(selectedVersionGroup) 새 목록에서 같은 버전을
// 이름으로 다시 찾아 선택/일감 칸도 그대로 이어간다 - 새로 받아온 객체는 참조가 달라져서
// 그냥 두면 renderVersionRow의 참조 비교(group === selectedVersionGroup)가 깨진다.
function updateVersionGroups(projectId, groups) {
    if (projectId !== selectedProjectId) return;
    const selectedVersionName = selectedVersionGroup ? selectedVersionGroup.version : null;
    versionGroups = groups || [];
    selectedVersionGroup = selectedVersionName
        ? versionGroups.find((g) => g.version === selectedVersionName) || null
        : null;
    renderVersionCol();
    if (selectedVersionGroup) {
        renderIssueCol(selectedVersionGroup);
    } else if (selectedVersionName) {
        renderPlaceholder("colIssue", "프로젝트와 버전을 선택하세요.");
    }
}

// 버전의 종료일 연도(없으면 "none") - 배지 묶음을 만들 때와 필터링할 때 같은 기준으로 쓴다.
function versionYearKey(group) {
    return group.due_date ? parseInt(group.due_date.slice(0, 4), 10) : "none";
}

function renderVersionCol() {
    const col = document.getElementById("colVersion");
    col.innerHTML = "";
    renderVersionBadges();
    if (versionGroups.length === 0) {
        renderPlaceholder("colVersion", "해결된 이슈가 없습니다.");
        return;
    }

    // 최신 버전이 위로 오도록 종료일 내림차순으로 죽 늘어놓는다 - yearFilter가
    // 걸려 있으면 그 연도(또는 종료일 없는 "미정")만 남기고 거른다. 연도 배지 자체는
    // #badgeRow(고정 헤더)에 따로 그려서, 목록을 스크롤해도 항상 맨 위에 남는다.
    const groups = versionGroups
        .filter((g) => yearFilter === null || versionYearKey(g) === yearFilter)
        .sort((a, b) => (a.due_date || "") > (b.due_date || "") ? -1 : (a.due_date || "") < (b.due_date || "") ? 1 : 0);

    // 기본값이 "올해"로 걸려 있는 경우가 많아서(currentYear 참고), 정작 그 프로젝트에
    // 올해 버전이 없으면 목록이 빈 채로 아무 설명도 없이 비어 보인다 - 실제로는 필터
    // 때문이라고 알려준다(위 "해결된 이슈가 없습니다"는 필터와 무관하게 버전 자체가
    // 하나도 없을 때만 쓴다).
    if (groups.length === 0) {
        const label = yearFilter === "none" ? "종료일 미정" : `${yearFilter}년`;
        renderPlaceholder("colVersion", `${label} 버전이 없습니다.`);
        return;
    }

    // 최상위를 골라 하위 프로젝트를 모아 보여줄 때만(project 필드가 붙어 있을 때만)
    // 하위 프로젝트별로 섹션을 나눈다 - 단일 프로젝트를 골랐을 땐 project 필드 자체가
    // 없으니(App._fetch_resolved_by_version 참고) 예전처럼 그냥 평평한 목록 그대로.
    if (groups.some((g) => g.project)) {
        renderVersionsGroupedByProject(col, groups);
    } else {
        groups.forEach((group) => col.appendChild(renderVersionRow(group)));
    }
}

// 하위 프로젝트마다 섹션을 나눠서 그 프로젝트의 버전들을 묶어 보여준다(각 섹션 안
// 순서는 위에서 이미 정렬해 둔 종료일 내림차순 그대로). 섹션 순서는 프로젝트 이름
// 가나다순 - 여러 프로젝트를 한꺼번에 조회하는 순서(스레드가 끝나는 순서)는 매번
// 달라져서, 이름순으로 고정해야 다시 그릴 때마다(연도 필터를 바꿀 때 등) 섹션
// 위치가 안 흔들린다.
function renderVersionsGroupedByProject(col, groups) {
    const byProject = new Map();
    groups.forEach((g) => {
        const key = g.project || "";
        if (!byProject.has(key)) byProject.set(key, []);
        byProject.get(key).push(g);
    });

    [...byProject.keys()].sort((a, b) => a.localeCompare(b, "ko")).forEach((project, i) => {
        const section = document.createElement("div");
        section.className = "project-section" + (i > 0 ? " with-divider" : "");

        const heading = document.createElement("div");
        heading.className = "project-heading";
        heading.textContent = project;
        section.appendChild(heading);

        byProject.get(project).forEach((group) => section.appendChild(renderVersionRow(group)));
        col.appendChild(section);
    });
}

// 로드맵 칸의 연도 배지 - #badgeVersion(#badgeRow 안, 일감 칸 배지와 구분선 없이
// 이어지는 자리)에 그린다. 최신 연도가 왼쪽에 오도록 내림차순, 종료일 없는 버전의
// "미정" 배지는 맨 뒤에 둔다. 눌러서 그 연도만 거를 수 있고, 이미 걸려 있는 배지를
// 다시 누르면 필터가 풀리고 전체가 다시 보인다.
function renderVersionBadges() {
    const bar = document.getElementById("badgeVersion");
    bar.innerHTML = "";
    if (versionGroups.length === 0) return;

    const years = [...new Set(versionGroups.map(versionYearKey))]
        .sort((a, b) => (a === "none" ? 1 : b === "none" ? -1 : b - a));

    years.forEach((year) => {
        const badge = document.createElement("span");
        badge.className = "year-badge" + (yearFilter === year ? " active" : "");
        badge.textContent = year === "none" ? "미정" : `${year}`;
        badge.addEventListener("click", () => {
            yearFilter = (yearFilter === year) ? null : year;
            renderVersionCol();
        });
        bar.appendChild(badge);
    });
}

function renderVersionRow(group) {
    const row = document.createElement("div");
    // 연도 배지로 필터를 바꾸면 목록 전체가 다시 그려지는데, 그때도 이미 골라 둔
    // 버전의 선택 표시가 살아있게 group 참조(selectedVersionGroup)로 비교한다 -
    // DOM 요소(selectedVersionRow)는 다시 그릴 때마다 새로 만들어져 못 미덥다.
    row.className = "row" + (group === selectedVersionGroup ? " selected" : "");
    if (group === selectedVersionGroup) selectedVersionRow = row;

    // 종료일은 버전명 앞에 - 목록을 세로로 훑을 때 날짜가 한 줄로 정렬돼서
    // "언제까지인지"가 먼저 읽힌다. 종료일이 없는 버전도 빈 자리를 남겨서
    // (.due.none) 버전명 시작 위치는 모든 행이 같게 맞춘다.
    const due = document.createElement("span");
    due.className = group.due_date ? "due" : "due none";
    if (group.due_date) {
        due.textContent = formatDue(group.due_date);
        due.title = `종료일 ${group.due_date}`;
    }
    row.appendChild(due);

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = group.version;
    row.appendChild(label);

    // 뱃지엔 진행률 퍼센트만 - 몇 건 중 몇 건인지는 툴팁으로 미룬다. 끝난 일감
    // 판정은 closed_on 기준이다(redmine_api.fetch_issues_by_version 참고).
    const total = group.issues.length;
    const done = group.issues.filter((i) => i.closed).length;
    const percent = total ? Math.round((done / total) * 100) : 0;
    const count = document.createElement("span");
    count.className = "count" + (total > 0 && done === total ? " done" : "");
    count.textContent = `${percent}%`;
    count.title = `전체 ${total}건 중 ${done}건 완료 (${percent}%)`;
    row.appendChild(count);

    row.addEventListener("click", () => {
        if (selectedVersionRow) selectedVersionRow.classList.remove("selected");
        row.classList.add("selected");
        selectedVersionRow = row;
        selectedVersionGroup = group;
        renderIssueCol(group);
    });

    return row;
}

// "2026-05-31" -> "26.05.31". 가운데 칸이 좁아서(창 너비의 30%) 연도 네 자리를 다
// 쓰면 버전명이 밀린다 - 뱃지에 마우스를 올리면 원래 날짜가 그대로 보인다.
function formatDue(dueDate) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dueDate);
    return m ? `${m[1].slice(2)}.${m[2]}.${m[3]}` : dueDate;
}

function renderIssueCol(group) {
    const col = document.getElementById("colIssue");
    col.innerHTML = "";

    const issues = group.issues;
    if (!issues || issues.length === 0) {
        const p = document.createElement("div");
        p.className = "placeholder";
        p.textContent = "이슈가 없습니다.";
        col.appendChild(p);
        return;
    }
    issues.forEach((issue) => {
        const row = document.createElement("div");
        row.className = "issue-row";

        // 상태 뱃지는 번호/제목 앞에 - 일감 창(issues_panel.js)에서 유형·우선순위
        // 뱃지를 다는 자리와 같아서, 두 창을 오가도 눈이 같은 곳을 본다.
        if (issue.status) {
            const [bg, fg] = STATUS_COLORS[issue.status] || STATUS_FALLBACK;
            const pill = document.createElement("span");
            pill.className = "pill";
            pill.style.background = bg;
            pill.style.color = fg;
            pill.textContent = issue.status;
            row.appendChild(pill);
        }

        const text = document.createElement("span");
        text.className = "issue-text";
        text.textContent = `#${issue.id}  ${issue.subject}`;
        row.appendChild(text);

        row.addEventListener("click", () => window.pywebview.api.open_url(issue.url));
        col.appendChild(row);
    });
}

