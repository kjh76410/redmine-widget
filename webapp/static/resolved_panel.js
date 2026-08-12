// 파이썬(App._push_resolved_tree)이 호출하는 진입점: {title, tree} 형태의 데이터를 받는다.
// tree는 전사 레드마인 프로젝트 트리(회사 것만 - 원래 Tkinter 버전과 동일한 범위).
let selectedProjectRow = null;
let selectedVersionRow = null;
let versionGroups = [];
let loadToken = 0;

function renderResolvedPanel(data) {
    document.getElementById("title").textContent = data.title || "버전별 해결 일감";
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

        const label = document.createElement("span");
        label.className = "label";
        label.textContent = group.version;
        row.appendChild(label);

        const count = document.createElement("span");
        count.className = "count";
        count.textContent = String(group.issues.length);
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
        row.textContent = `#${issue.id}  ${issue.subject}`;
        row.addEventListener("click", () => window.pywebview.api.open_url(issue.url));
        col.appendChild(row);
    });
}
