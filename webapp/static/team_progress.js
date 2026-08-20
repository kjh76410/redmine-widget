// 파이썬(App._push_team_progress_tree)이 호출하는 진입점: {teams} 형태의 데이터를
// 받는다. teams는 전사 레드마인 최상위(루트) 프로젝트 목록("Cybertel Bridge" 같은 회사/
// 조직 단위) - 실제 "팀"은 대체로 이 바로 아래 자식 프로젝트라서(예: Cybertel Bridge 밑의
// "MCX솔루션 개발팀", "기구팀" 등), 왼쪽 트리에서 최상위뿐 아니라 depth 1 자식(팀 자신)도
// 펼쳐서 바로 고를 수 있다(더 깊이는 안 보여준다 - "팀" 단위는 딱 이 depth라서). 최상위를
// 고르면 그 자식 전체를, 자식을 직접 고르면 그 하나만 get_team_progress가 돌려주는데,
// 각 팀은 다시 그 팀의 depth 2 자식 프로젝트별로 나뉜 subgroups를 갖는다(예:
// "MCX솔루션 개발팀" 밑의 "국내 프로젝트"/"해외 프로젝트"처럼 성격이 다른 프로젝트가
// 섞여 있어서 - main.py App.get_team_progress 설명 참고):
// [{"team":, "team_id":, "subgroups": [{"team":, "team_id":, "is_subproject":, "versions":[...]}, ...]}, ...]
// 팀마다 섹션을, 그 안에 depth 2 프로젝트마다 구분자를 넣은 소그룹을 그린다.
// 이 화면은 "무엇이 진행 중인지" 간트차트로만 훑어보는 용도라 일감 목록/진행률 막대/
// 클릭 상호작용은 없다.
let selectedTeamRow = null;
let selectedProjectId = null;  // 지금 오른쪽에 펼쳐놓은 조직/팀의 id - updateOrgCol이 그 사이
                                // 다른 걸 골랐으면(불일치) 백그라운드 새로고침 결과를 버리는 데 쓴다
let loadToken = 0;

// 새로고침 아이콘 - 지금 고른 조직/팀을 캐시 없이 곧바로 다시 받아온다. 아직 고른 게
// 없으면(selectedProjectId 없음) 할 일이 없으니 조용히 무시한다.
document.getElementById("refreshBtn").addEventListener("click", () => {
    if (selectedProjectId != null) {
        window.pywebview.api.refresh_team_progress(selectedProjectId);
    }
});

function renderTeamProgressPanel(data) {
    const col = document.getElementById("colTeam");
    col.innerHTML = "";
    selectedTeamRow = null;
    selectedProjectId = null;
    renderPlaceholder("colVersion", "왼쪽에서 조직/팀을 선택하세요.");

    const teams = data.teams || [];
    if (teams.length === 0) {
        renderPlaceholder("colTeam", "목록을 불러오는 중이거나 없습니다.");
        return;
    }
    teams.forEach((node) => col.appendChild(renderTeamRow(node, 0)));
}

function renderPlaceholder(colId, text) {
    const col = document.getElementById(colId);
    col.innerHTML = "";
    const p = document.createElement("div");
    p.className = "placeholder";
    p.textContent = text;
    col.appendChild(p);
}

// depth 0(최상위)까지만 펼침 화살표를 둔다 - "팀"은 최상위 아니면 그 바로 아래(depth 1)
// 둘 중 하나라서, depth 1보다 더 깊이 들어갈 필요가 없다.
function renderTeamRow(node, depth) {
    const wrap = document.createElement("div");

    const row = document.createElement("div");
    row.className = "row";
    row.style.paddingLeft = (depth * 14 + 10) + "px";

    const hasChildren = depth === 0 && node.children && node.children.length > 0;
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
        node.children.forEach((c) => childWrap.appendChild(renderTeamRow(c, depth + 1)));
    }

    let expanded = false;
    row.addEventListener("click", (e) => {
        if (hasChildren && e.target === arrow) {
            expanded = !expanded;
            arrow.textContent = expanded ? "▾" : "▸";
            childWrap.classList.toggle("collapsed", !expanded);
            return;
        }
        selectOrg(node, row);
    });

    wrap.appendChild(row);
    wrap.appendChild(childWrap);
    return wrap;
}

function selectOrg(node, row) {
    if (selectedTeamRow) selectedTeamRow.classList.remove("selected");
    row.classList.add("selected");
    selectedTeamRow = row;
    selectedProjectId = node.id;

    renderPlaceholder("colVersion", "불러오는 중...");

    const token = ++loadToken;
    window.pywebview.api.get_team_progress(node.id).then((orgTeams) => {
        if (token !== loadToken) return;  // 그 사이 다른 항목을 눌렀으면 버림
        renderOrgCol(orgTeams || []);
    }).catch((err) => {
        if (token !== loadToken) return;
        renderPlaceholder("colVersion", "불러오기 실패: " + String(err));
    });
}

// 파이썬(App._refresh_team_progress)이 캐시를 먼저 보여준 뒤 백그라운드로 새로 받아온
// 최신 데이터를 밀어줄 때 부르는 진입점. 그 사이 다른 조직/팀을 골랐으면 조용히 버린다.
function updateOrgCol(projectId, orgTeams) {
    if (projectId !== selectedProjectId) return;
    renderOrgCol(orgTeams || []);
}

function renderOrgCol(orgTeams) {
    const col = document.getElementById("colVersion");
    col.innerHTML = "";
    if (orgTeams.length === 0) {
        renderPlaceholder("colVersion", "하위 프로젝트가 없습니다.");
        return;
    }

    // 로드맵(버전)이 하나도 없는 팀/프로젝트는 "버전이 없습니다" 같은 빈 안내문 대신
    // 통째로 건너뛴다 - 보여줄 게 없으면 아예 안 보이는 쪽이, 팀마다 빈 칸이 죽
    // 늘어서는 것보다 낫다(renderTeamSection이 보여줄 게 없으면 null을 돌려준다).
    const sections = orgTeams.map((team) => renderTeamSection(team)).filter((s) => s !== null);
    if (sections.length === 0) {
        renderPlaceholder("colVersion", "버전이 지정된 로드맵이 없습니다.");
        return;
    }
    sections.forEach((section, i) => {
        if (i > 0) section.classList.add("with-divider");
        col.appendChild(section);
    });
}

const MONTH_NAMES = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];

// 팀 섹션 하나를 만들어 돌려준다. 이번 연도 마감 예정 버전이 하나도 없는 하위
// 프로젝트는 renderSubgroup이 null을 돌려주니 그런 것만 걸러내고, 남는 게 없으면
// 이 팀 섹션 자체도 null로 돌려서(보여줄 게 없다) 위(renderOrgCol)에서 건너뛰게 한다.
function renderTeamSection(team) {
    const subgroups = (team.subgroups || []).map(renderSubgroup).filter((el) => el !== null);
    if (subgroups.length === 0) return null;

    const section = document.createElement("div");
    section.className = "team-section";

    const heading = document.createElement("div");
    heading.className = "team-heading";
    heading.textContent = team.team;
    section.appendChild(heading);

    subgroups.forEach((el, i) => {
        if (i > 0) el.classList.add("with-divider");
        section.appendChild(el);
    });
    return section;
}

// 팀(depth 1) 섹션 안에서 depth 2 프로젝트마다 나뉘는 소그룹 하나(예: "MCX솔루션
// 개발팀" 섹션 안의 "국내 프로젝트"/"해외 프로젝트"). 이 화면은 올해 마감인 버전만
// Month 그리드에 올리는데(그 외는 그리드에 놓을 축 좌표가 없어서 뺀다 - 진행률
// 막대 같은 대체 표시는 안 둔다), 올해 마감인 게 하나도 없으면 "없습니다" 안내문
// 대신 이 소그룹 자체를 안 보여준다(null 반환) - 보여줄 게 없으면 아예 안 보이는
// 쪽이 팀마다 빈 칸이 죽 늘어서는 것보다 낫다.
function renderSubgroup(sub) {
    const thisYear = new Date().getFullYear();
    const ganttGroups = (sub.versions || []).filter(
        (g) => g.due_date && new Date(g.due_date + "T00:00:00").getFullYear() === thisYear
    );
    if (ganttGroups.length === 0) return null;
    ganttGroups.sort((a, b) => (a.due_date < b.due_date ? -1 : a.due_date > b.due_date ? 1 : 0));

    const wrap = document.createElement("div");
    wrap.className = "subgroup";

    // depth 2 자식이 없는 팀은 파이썬이 팀 자신을 이 그룹으로 대신 채워서
    // sub.team이 위 team-heading과 똑같은 이름이 된다(main.py _fetch_team_progress
    // 참고) - 그 경우 뱃지를 또 붙이면 같은 이름이 중복으로 보이니 생략한다.
    if (sub.is_subproject) {
        const heading = document.createElement("div");
        heading.className = "subgroup-heading";
        heading.textContent = sub.team;
        wrap.appendChild(heading);
    }

    wrap.appendChild(renderGanttHeader(thisYear));
    ganttGroups.forEach((group) => wrap.appendChild(renderGanttRow(group, thisYear)));

    return wrap;
}

function renderGanttHeader(year) {
    const header = document.createElement("div");
    header.className = "gantt-header";
    header.title = `${year}년`;

    const spacer = document.createElement("div");
    spacer.className = "label-spacer";
    header.appendChild(spacer);

    const currentMonth = new Date().getMonth();
    const months = document.createElement("div");
    months.className = "months";
    MONTH_NAMES.forEach((m, i) => {
        const span = document.createElement("span");
        span.textContent = m;
        if (i === currentMonth) span.className = "current";
        months.appendChild(span);
    });
    header.appendChild(months);

    return header;
}

// 버전의 진행 기간(시작월~마감월, 0~11)을 계산한다. 레드마인 버전엔 시작일 필드
// 자체가 없어서 created_on(그 버전이 만들어진 날)을 시작으로 근사한다 - 이 값은
// 항상 due_date와 같은 해에 있다고 보장되지 않고(과거에 미리 만들어 둔 버전 등),
// 심지어 마감일보다 나중일 수도 있어(데이터 정리 시점에 재생성된 경우 등) 안전하게
// 자른다: 시작이 올해보다 이전이면 1월부터, 마감보다 나중이면 마감월 한 칸만.
function computeMonthRange(group, year) {
    const endMonth = new Date(group.due_date + "T00:00:00").getMonth();
    if (!group.created_on) return [endMonth, endMonth];

    const start = new Date(group.created_on + "T00:00:00");
    let startMonth;
    if (start.getFullYear() < year) {
        startMonth = 0;
    } else if (start.getFullYear() === year) {
        startMonth = start.getMonth();
    } else {
        startMonth = endMonth;  // 시작이 마감 해보다 미래인 이상 데이터 - 무시
    }
    return [Math.min(startMonth, endMonth), endMonth];
}

function renderGanttRow(group, year) {
    const row = document.createElement("div");
    row.className = "gantt-row";
    const period = group.created_on ? `${group.created_on} ~ ${group.due_date}` : `~ ${group.due_date}`;
    row.title = `${group.version} (${period}) - ${group.closed}/${group.total}건 완료 (${group.percent}%)`;

    const label = document.createElement("span");
    label.className = "label clickable";
    label.textContent = group.version;
    if (group.url) {
        label.addEventListener("click", () => window.pywebview.api.open_url(group.url));
    }
    row.appendChild(label);

    const cells = document.createElement("div");
    cells.className = "cells";
    const [startMonth, endMonth] = computeMonthRange(group, year);
    const currentMonth = new Date().getMonth();
    const doneClass = group.percent >= 100 ? " done" : "";
    for (let m = 0; m < 12; m++) {
        const cell = document.createElement("span");
        let cls = "month-cell";
        if (m >= startMonth && m <= endMonth) {
            cls += " filled" + doneClass;
            if (m === startMonth) cls += " range-start";
            if (m === endMonth) cls += " range-end";
        } else if (m === currentMonth) {
            cls += " current";
        }
        cell.className = cls;
        cells.appendChild(cell);
    }
    row.appendChild(cells);

    return row;
}

