// 파이썬(App._push_resolved_tree)이 호출하는 진입점: {tree} 형태의 데이터를 받는다.
// tree는 전사 레드마인 프로젝트 트리(회사 것만 - 원래 Tkinter 버전과 동일한 범위).
let selectedProjectRow = null;
let selectedVersionRow = null;
let versionGroups = [];
let loadToken = 0;

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
    selectedVersionRow = null;
    versionGroups = [];
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

    selectedVersionRow = null;
    versionGroups = [];
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

function renderVersionCol() {
    const col = document.getElementById("colVersion");
    col.innerHTML = "";
    if (versionGroups.length === 0) {
        renderPlaceholder("colVersion", "해결된 이슈가 없습니다.");
        return;
    }
    versionGroups.forEach((group) => {
        const row = document.createElement("div");
        row.className = "row";

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

        // 개수 뱃지에 진행률을 같이 담는다("완료/전체") - 좁은 칸에 뱃지를 하나 더
        // 붙이는 대신, 이미 있던 자리를 정보량만 늘려서 쓴다. 끝난 일감 판정은
        // closed_on 기준이다(redmine_api.fetch_issues_by_version 참고).
        const total = group.issues.length;
        const done = group.issues.filter((i) => i.closed).length;
        const count = document.createElement("span");
        count.className = "count" + (total > 0 && done === total ? " done" : "");
        count.textContent = `${done}/${total}`;
        count.title = `전체 ${total}건 중 ${done}건 완료`
            + (total ? ` (${Math.round((done / total) * 100)}%)` : "");
        row.appendChild(count);

        row.addEventListener("click", () => {
            if (selectedVersionRow) selectedVersionRow.classList.remove("selected");
            row.classList.add("selected");
            selectedVersionRow = row;
            renderIssueCol(group.issues);
        });

        col.appendChild(row);
    });
}

// "2026-05-31" -> "26.05.31". 가운데 칸이 좁아서(창 너비의 30%) 연도 네 자리를 다
// 쓰면 버전명이 밀린다 - 뱃지에 마우스를 올리면 원래 날짜가 그대로 보인다.
function formatDue(dueDate) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dueDate);
    return m ? `${m[1].slice(2)}.${m[2]}.${m[3]}` : dueDate;
}

function renderIssueCol(issues) {
    const col = document.getElementById("colIssue");
    col.innerHTML = "";
    if (!issues || issues.length === 0) {
        renderPlaceholder("colIssue", "이슈가 없습니다.");
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
