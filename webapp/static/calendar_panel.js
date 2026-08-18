// 파이썬(App._render_calendar)이 호출하는 진입점: 즐겨찾기한 프로젝트의 배포 버전 중
// 종료일(due_date)이 잡힌 것들을 평평한 한 목록으로 받는다.
// {versions: [{version_id, version, project, project_id, source, due_date, status, url}, ...],
//  loading: bool, has_favorites: bool, today: "YYYY-MM-DD"}
//
// 화면은 좌우 두 칸이다. 오른쪽은 월 달력이라 어느 날에 무엇이 나가는지 한눈에 훑는
// 용도고, 왼쪽은 실제로 매일 보게 되는 "다가오는 일정" 목록이다. 달력에서 날짜를 누르면
// 왼쪽이 그 날 상세로 바뀌고, 거기서만 진행률을 따로 받아 채운다 - 전체 버전의 진행률을
// 미리 세면 프로젝트마다 이슈를 수백 건씩 훑어야 해서 창이 뜨는 데만 한참 걸린다
// (redmine_api.fetch_calendar_versions 설명 참고).
//
// 다른 화면들과 달리 왼쪽에 프로젝트 트리가 없다. 즐겨찾기 전체를 가로질러 보는 게
// 이 화면의 존재 이유라서, 프로젝트를 고르는 단계 자체가 없는 게 맞다.

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];
const UPCOMING_DAYS = 60;  // "다가오는 일정"에 담을 기간 - 그 뒤는 건수만 알려준다
// 달력 한 칸에 이름까지 보여줄 버전 개수. 칸 높이(창 680px에서 6주면 한 칸 약 100px)가
// 날짜 숫자 + 칩 2줄 + "+N건 더" 한 줄까지만 감당한다 - 3줄을 넣으면 마지막 칩이 칸
// 아래로 잘린다(.items가 overflow:hidden이라 소리 없이 잘려서 더 나쁘다).
const MAX_CHIPS = 2;

let versions = [];
let byDate = new Map();     // "YYYY-MM-DD" -> [version, ...]
let holidays = {};          // "YYYY-MM-DD" -> 공휴일 이름 (파이썬 korean_holidays가 계산)
let today = "";
let loading = true;
let hasFavorites = true;

let viewYear = null;        // 지금 보고 있는 달 (month는 자바스크립트와 같은 0~11)
let viewMonth = null;
let selectedDate = null;    // 왼쪽에 상세를 펼쳐 놓은 날짜, 없으면 null
let progressToken = 0;      // 진행률을 비동기로 채우는 중에 다른 날짜로 넘어가면 버리려고

function renderCalendarPanel(data) {
    versions = data.versions || [];
    holidays = data.holidays || {};
    loading = !!data.loading;
    hasFavorites = !!data.has_favorites;
    today = data.today || isoOf(new Date());

    byDate = new Map();
    versions.forEach((v) => {
        if (!byDate.has(v.due_date)) byDate.set(v.due_date, []);
        byDate.get(v.due_date).push(v);
    });

    // 처음 그릴 때만 오늘이 있는 달로 맞춘다 - 목록을 다 받아온 뒤 다시 그릴 때
    // (파이썬이 같은 함수를 두 번 부른다) 사용자가 넘겨 둔 달을 되돌리면 안 된다.
    if (viewYear === null) {
        const now = new Date(today + "T00:00:00");
        viewYear = now.getFullYear();
        viewMonth = now.getMonth();
    }

    // 그 사이 목록이 바뀌어 고른 날짜에 아무것도 안 남았으면 목록 화면으로 되돌린다.
    if (selectedDate && !byDate.has(selectedDate)) selectedDate = null;

    renderCalendar();
    renderLeft();
}

// ── 날짜 유틸 ────────────────────────────────
// 날짜 문자열은 항상 "YYYY-MM-DD"라 사전순 비교 = 시간순 비교다(지연/예정 판정에 쓴다).
// Date로 만들 때 "T00:00:00"을 붙이는 이유는 team_progress.js와 같다 - 안 붙이면
// UTC로 해석돼서 한국 시간대에선 하루씩 밀린다.
function isoOf(d) {
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function dayDiff(fromIso, toIso) {
    const a = new Date(fromIso + "T00:00:00");
    const b = new Date(toIso + "T00:00:00");
    return Math.round((b - a) / 86400000);
}

function formatDay(iso) {
    const d = new Date(iso + "T00:00:00");
    return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAYS[d.getDay()]})`;
}

// 레드마인 버전 상태(status)와 종료일만으로 판정한다 - 이슈를 한 건도 안 받고
// 정해지는 게 핵심이라 달력이 가볍다.
//   done    : 버전이 닫힘 = 이미 나간 배포
//   late    : 종료일이 지났는데 아직 안 닫힘 = 밀린 배포
//   planned : 그 외 = 예정된 배포
function versionState(v) {
    if (v.status === "closed") return "done";
    if (v.due_date < today) return "late";
    return "planned";
}

function stateLabel(state) {
    if (state === "done") return "배포됨";
    if (state === "late") return "지연";
    return "예정";
}

// 그 날이 일하는 날이 아니면 이유("광복절" / "토요일")를, 평일이면 null을 준다.
// 배포가 쉬는 날에 잡혔는지 알려주는 데 쓴다 - 배포 달력에서 공휴일을 보는 이유가
// 사실상 이것이다.
function offDayReason(iso) {
    if (holidays[iso]) return holidays[iso];
    const dow = new Date(iso + "T00:00:00").getDay();
    if (dow === 0) return "일요일";
    if (dow === 6) return "토요일";
    return null;
}

// ── 오른쪽: 월 달력 ──────────────────────────
function renderCalendar() {
    document.getElementById("monthLabel").textContent = `${viewYear}년 ${viewMonth + 1}월`;

    const weekdays = document.getElementById("weekdays");
    weekdays.innerHTML = "";
    WEEKDAYS.forEach((name, i) => {
        const span = document.createElement("span");
        span.textContent = name;
        if (i === 0) span.className = "sun";
        if (i === 6) span.className = "sat";
        weekdays.appendChild(span);
    });

    const grid = document.getElementById("grid");
    grid.innerHTML = "";

    // 1일이 있는 주의 일요일부터 6주(42칸)를 항상 그린다 - 달마다 줄 수가 바뀌면
    // 칸 높이가 들쭉날쭉해져서 달을 넘길 때 화면이 출렁인다.
    const first = new Date(viewYear, viewMonth, 1);
    const start = new Date(viewYear, viewMonth, 1 - first.getDay());
    for (let i = 0; i < 42; i++) {
        const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
        grid.appendChild(renderDayCell(date));
    }
}

function renderDayCell(date) {
    const iso = isoOf(date);
    const items = byDate.get(iso) || [];

    const holiday = holidays[iso];
    const weekend = date.getDay() === 0 || date.getDay() === 6;

    const cell = document.createElement("div");
    let cls = "day";
    if (weekend) cls += " weekend";
    if (holiday) cls += " holiday";
    if (date.getMonth() !== viewMonth) cls += " other";
    if (iso === today) cls += " today";
    if (iso === selectedDate) cls += " selected";
    if (items.length > 0) cls += " has-items";
    cell.className = cls;
    // 칸이 좁아 공휴일 이름이 잘리니, 전체 이름은 칸에 마우스를 올려 확인할 수 있게 둔다.
    if (holiday) cell.title = `${formatDay(iso)} · ${holiday}`;

    const numRow = document.createElement("div");
    numRow.className = "num-row";

    const num = document.createElement("span");
    num.className = "num" + (date.getDay() === 0 ? " sun" : date.getDay() === 6 ? " sat" : "");
    num.textContent = String(date.getDate());
    numRow.appendChild(num);

    if (holiday) {
        const label = document.createElement("span");
        label.className = "hol";
        label.textContent = holiday;
        numRow.appendChild(label);
    }
    cell.appendChild(numRow);

    if (items.length > 0) {
        const list = document.createElement("div");
        list.className = "items";
        items.slice(0, MAX_CHIPS).forEach((v) => {
            const chip = document.createElement("div");
            chip.className = "chip";
            chip.title = `${v.project} - ${v.version} (${stateLabel(versionState(v))})`;

            const dot = document.createElement("i");
            dot.className = "dot " + versionState(v);
            chip.appendChild(dot);

            const name = document.createElement("span");
            name.className = "name";
            name.textContent = v.version;
            chip.appendChild(name);

            list.appendChild(chip);
        });
        cell.appendChild(list);

        if (items.length > MAX_CHIPS) {
            const more = document.createElement("div");
            more.className = "more";
            more.textContent = `+${items.length - MAX_CHIPS}건 더`;
            cell.appendChild(more);
        }

        cell.addEventListener("click", () => selectDate(iso));
    }

    return cell;
}

function selectDate(iso) {
    // 같은 날짜를 다시 누르면 접고 "다가오는 일정"으로 돌아간다(토글).
    selectedDate = selectedDate === iso ? null : iso;
    renderCalendar();
    renderLeft();
}

// ── 왼쪽: 다가오는 일정 / 날짜 상세 ───────────
function renderLeft() {
    const col = document.getElementById("colUpcoming");
    col.innerHTML = "";
    progressToken++;  // 이전 날짜의 진행률 응답이 뒤늦게 도착해도 무시되게

    if (selectedDate) {
        renderDayDetail(col, selectedDate);
        return;
    }

    col.appendChild(heading("다가오는 일정"));

    if (versions.length === 0) {
        col.appendChild(placeholder(emptyMessage()));
        return;
    }

    // 지연은 최근에 놓친 것부터 보여준다. 레드마인에는 몇 해 전에 만들어 놓고 닫지
    // 않은 버전이 흔히 남아있어서, 오래된 순으로 쌓으면 그런 껍데기가 목록 맨 위를
    // 차지하고 정작 방금 놓친 배포가 스크롤 아래로 밀린다.
    const late = versions
        .filter((v) => versionState(v) === "late")
        .sort((a, b) => (a.due_date > b.due_date ? -1 : 1));
    const upcoming = versions
        .filter((v) => v.due_date >= today && dayDiff(today, v.due_date) <= UPCOMING_DAYS)
        .sort((a, b) => (a.due_date < b.due_date ? -1 : 1));
    const laterCount = versions.filter(
        (v) => dayDiff(today, v.due_date) > UPCOMING_DAYS
    ).length;

    if (late.length > 0) {
        col.appendChild(groupHeading(`지연 ${late.length}건`, true));
        late.forEach((v) => col.appendChild(renderUpcomingItem(v)));
    }

    if (upcoming.length > 0) {
        col.appendChild(groupHeading(`앞으로 ${UPCOMING_DAYS}일 ${upcoming.length}건`));
        upcoming.forEach((v) => col.appendChild(renderUpcomingItem(v)));
    }

    if (late.length === 0 && upcoming.length === 0) {
        col.appendChild(placeholder(
            laterCount > 0
                ? `앞으로 ${UPCOMING_DAYS}일 안에 예정된 배포가 없습니다.`
                : "예정된 배포가 없습니다."
        ));
    }

    if (laterCount > 0) {
        col.appendChild(placeholder(`그 이후 ${laterCount}건은 달력에서 확인하세요.`));
    }
}

// 즐겨찾기가 아예 없는 것과, 즐겨찾기는 했는데 종료일 잡힌 버전이 없는 것은
// 사용자가 해야 할 일이 다르다 - 문구도 나눈다.
function emptyMessage() {
    if (loading) return "배포 일정을 불러오는 중...";
    if (!hasFavorites) {
        return "즐겨찾기한 프로젝트가 없습니다. 프로젝트 목록에서 우클릭해 즐겨찾기하면 "
             + "그 프로젝트의 배포일이 달력에 표시됩니다.";
    }
    return "종료일이 지정된 배포 버전이 없습니다.";
}

function renderUpcomingItem(v) {
    const state = versionState(v);
    const diff = dayDiff(today, v.due_date);

    const item = document.createElement("div");
    item.className = "up-item";
    item.title = `${v.project} - ${v.version} (${v.due_date}, ${stateLabel(state)})`;

    const dday = document.createElement("span");
    let ddayClass = "dday";
    if (state === "late") {
        ddayClass += " late";
        dday.textContent = `+${-diff}일`;
    } else if (state === "done") {
        ddayClass += " done";
        dday.textContent = "배포됨";
    } else if (diff === 0) {
        ddayClass += " today";
        dday.textContent = "D-DAY";
    } else {
        dday.textContent = `D-${diff}`;
    }
    dday.className = ddayClass;
    item.appendChild(dday);

    const body = document.createElement("div");
    body.className = "body";

    const version = document.createElement("div");
    version.className = "version";
    version.textContent = v.version;
    body.appendChild(version);

    const project = document.createElement("div");
    project.className = "project";
    project.textContent = v.project;
    body.appendChild(project);

    const date = document.createElement("div");
    date.className = "date";
    date.textContent = formatDay(v.due_date);
    body.appendChild(date);

    // 아직 안 나간 배포만 알린다 - 이미 나갔거나(done) 밀린 배포(late)에 대고
    // "그날 쉬는 날이었다"고 해봐야 지금 할 수 있는 일이 없다.
    const offDay = state === "planned" ? offDayReason(v.due_date) : null;
    if (offDay) {
        const warn = document.createElement("div");
        warn.className = "off-day";
        warn.textContent = offDay;
        body.appendChild(warn);
    }

    item.appendChild(body);

    // 목록에서 누르면 그 날짜로 달력을 옮기고 상세를 편다 - 여기서 바로 브라우저를
    // 열어버리면 위젯 안에서 훑어보던 흐름이 끊긴다. 링크는 상세 카드에서 연다.
    item.addEventListener("click", () => {
        const d = new Date(v.due_date + "T00:00:00");
        viewYear = d.getFullYear();
        viewMonth = d.getMonth();
        selectedDate = v.due_date;
        renderCalendar();
        renderLeft();
    });

    return item;
}

function renderDayDetail(col, iso) {
    const items = byDate.get(iso) || [];

    const head = heading(`${formatDay(iso)} · ${items.length}건`);
    const back = document.createElement("button");
    back.className = "back-btn";
    back.title = "다가오는 일정으로";
    back.textContent = "‹";
    back.addEventListener("click", () => {
        selectedDate = null;
        renderCalendar();
        renderLeft();
    });
    head.insertBefore(back, head.firstChild);
    col.appendChild(head);

    const token = progressToken;
    items.forEach((v) => {
        col.appendChild(renderDayCard(v));
        loadProgress(v, token);
    });
}

function renderDayCard(v) {
    const state = versionState(v);

    const card = document.createElement("div");
    card.className = "day-card";
    card.title = "레드마인에서 이 버전 열기";

    const version = document.createElement("div");
    version.className = "version";
    version.textContent = v.version;
    card.appendChild(version);

    const project = document.createElement("div");
    project.className = "project";
    project.textContent = v.project;
    card.appendChild(project);

    const pill = document.createElement("span");
    pill.className = "state " + state;
    pill.textContent = stateLabel(state);
    card.appendChild(pill);

    const offDay = state === "planned" ? offDayReason(v.due_date) : null;
    if (offDay) {
        const warn = document.createElement("span");
        warn.className = "off-day";
        warn.textContent = offDay;
        card.appendChild(warn);
    }

    const progress = document.createElement("div");
    progress.className = "progress";
    progress.id = progressId(v);
    const caption = document.createElement("div");
    caption.className = "caption";
    caption.textContent = "진행률 확인 중...";
    progress.appendChild(caption);
    card.appendChild(progress);

    card.addEventListener("click", () => window.pywebview.api.open_url(v.url));
    return card;
}

// 전사/팀 레드마인은 서버가 달라서 버전 id가 겹칠 수 있다 - source까지 넣어야 안전하다.
function progressId(v) {
    return `prog-${v.source}-${v.version_id}`;
}

function loadProgress(v, token) {
    window.pywebview.api.get_version_progress(v.version_id, v.source).then((counts) => {
        if (token !== progressToken) return;  // 그 사이 다른 날짜로 넘어갔으면 버린다
        const box = document.getElementById(progressId(v));
        if (!box) return;
        box.innerHTML = "";

        if (!counts) {
            box.appendChild(captionEl("진행률을 불러오지 못했습니다."));
            return;
        }
        if (!counts.total) {
            box.appendChild(captionEl("연결된 일감 없음"));
            return;
        }

        const percent = Math.round((counts.closed / counts.total) * 100);
        const track = document.createElement("div");
        track.className = "track";
        const fill = document.createElement("div");
        fill.className = "fill" + (percent >= 100 ? " done" : "");
        fill.style.width = percent + "%";
        track.appendChild(fill);
        box.appendChild(track);
        box.appendChild(captionEl(`${counts.closed}/${counts.total}건 완료 (${percent}%)`));
    }).catch(() => {
        if (token !== progressToken) return;
        const box = document.getElementById(progressId(v));
        if (box) {
            box.innerHTML = "";
            box.appendChild(captionEl("진행률을 불러오지 못했습니다."));
        }
    });
}

// ── 자잘한 조각들 ────────────────────────────
function heading(text) {
    const el = document.createElement("div");
    el.className = "pane-heading";
    const span = document.createElement("span");
    span.textContent = text;
    el.appendChild(span);
    return el;
}

function groupHeading(text, isLate) {
    const el = document.createElement("div");
    el.className = "group-heading" + (isLate ? " late" : "");
    el.textContent = text;
    return el;
}

function placeholder(text) {
    const el = document.createElement("div");
    el.className = "placeholder";
    el.textContent = text;
    return el;
}

function captionEl(text) {
    const el = document.createElement("div");
    el.className = "caption";
    el.textContent = text;
    return el;
}

// ── 달 넘기기 ────────────────────────────────
function shiftMonth(delta) {
    const d = new Date(viewYear, viewMonth + delta, 1);
    viewYear = d.getFullYear();
    viewMonth = d.getMonth();
    renderCalendar();
}

document.getElementById("prevMonth").addEventListener("click", () => shiftMonth(-1));
document.getElementById("nextMonth").addEventListener("click", () => shiftMonth(1));
document.getElementById("todayBtn").addEventListener("click", () => {
    const d = new Date(today + "T00:00:00");
    viewYear = d.getFullYear();
    viewMonth = d.getMonth();
    renderCalendar();
});
