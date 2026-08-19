"""한국 법정공휴일 계산 - 배포 달력(webapp/static/calendar_panel.js)이 날짜 칸에
공휴일을 표시하고, 배포일이 공휴일/주말에 잡혔는지 경고하는 데 쓴다.

바깥 API를 부르지 않는다. 이 위젯은 사내망(10.1.100.x)에서 도는 게 기본이라
공공데이터포털 같은 외부 서비스에 붙는다는 보장이 없고, 서비스키 발급이라는
설치 단계를 하나 더 만들고 싶지 않아서다. 대신:

  - 날짜가 고정된 공휴일(신정/삼일절/어린이날/현충일/제헌절/광복절/개천절/한글날/
    크리스마스)은 규칙으로 매년 만들어낸다 - 표에 없는 해가 와도 이만큼은 나온다.
  - 해마다 날짜가 바뀌는 음력 명절(설날/부처님오신날/추석)만 LUNAR_DATES 표에 둔다.
    새해 것을 추가하려면 그 표에 한 줄만 넣으면 된다.
  - 대체공휴일은 규칙으로 계산한다(SUBSTITUTE_TARGETS 설명 참고). 표로 적어두는
    것보다 이 편이 안전하다 - 실제로 널리 쓰이는 공휴일 사이트 중에도 현충일에
    대체공휴일을 붙여 놓은 곳이 있는데, 현충일은 추모 성격이라 대체 대상이 아니다.

표에 없는 연도는 음력 명절만 빠지고 나머지는 정상으로 나온다(조용히 틀리는 게 아니라
덜 나오는 쪽) - 화면에서는 그 해 설날/추석 표시만 안 뜬다.
"""

import datetime

# ─────────────────────────────────────────────
# 해마다 바뀌는 음력 명절만 적는다. 값은 "그 명절 당일"이고, 설날/추석은 당일 앞뒤
# 하루씩 합쳐 3일 연휴로 펼친다(_lunar_holidays 참고).
# 새 연도 추가는 여기 한 줄이면 된다.
# ─────────────────────────────────────────────
LUNAR_DATES = {
    2025: {"설날": "2025-01-29", "부처님오신날": "2025-05-05", "추석": "2025-10-06"},
    2026: {"설날": "2026-02-17", "부처님오신날": "2026-05-24", "추석": "2026-09-25"},
    2027: {"설날": "2027-02-07", "부처님오신날": "2027-05-13", "추석": "2027-09-15"},
    2028: {"설날": "2028-01-27", "부처님오신날": "2028-05-02", "추석": "2028-10-03"},
}

# (월, 일, 이름) - 해마다 같은 날
FIXED_DATES = [
    (1, 1, "신정"),
    (3, 1, "삼일절"),
    (5, 5, "어린이날"),
    (6, 6, "현충일"),
    (7, 17, "제헌절"),
    (8, 15, "광복절"),
    (10, 3, "개천절"),
    (10, 9, "한글날"),
    (12, 25, "크리스마스"),
]

# 제헌절은 2008년에 공휴일에서 빠졌다가 2026년부터 다시 공휴일이 됐다.
HOLIDAY_FIRST_YEAR = {"제헌절": 2026}

# 대체공휴일이 붙는 공휴일. 신정과 현충일은 빠져 있는데, 국경일이 아니거나(신정)
# 추모 성격이라(현충일) 법이 대상에서 빼 뒀기 때문이다 - 2026년 현충일이 토요일인데도
# 대체공휴일이 없는 게 그래서다.
SUBSTITUTE_TARGETS = {
    "삼일절", "어린이날", "부처님오신날", "제헌절", "광복절",
    "개천절", "한글날", "크리스마스",
}

# 설날/추석 "연휴"는 규칙이 다르다. 위 공휴일들은 토요일과 겹쳐도 대체공휴일이 붙지만,
# 명절 연휴는 일요일(또는 다른 공휴일)과 겹칠 때만 붙는다 - 2026년 추석 연휴가
# 목·금·토라서 대체공휴일이 없는 게 이 차이 때문이다.
LUNAR_FESTIVALS = {"설날", "추석"}

_ISO = "%Y-%m-%d"


def _parse(iso):
    return datetime.datetime.strptime(iso, _ISO).date()


def _lunar_holidays(year):
    """그 해 음력 명절을 {날짜: 이름}으로. 설날/추석은 당일 앞뒤로 하루씩 붙여 3일 연휴."""
    table = LUNAR_DATES.get(year)
    if not table:
        return {}

    result = {}
    for name, iso in table.items():
        day = _parse(iso)
        if name in LUNAR_FESTIVALS:
            for offset in (-1, 0, 1):
                result[(day + datetime.timedelta(days=offset)).strftime(_ISO)] = name
        else:
            result[iso] = name
    return result


def _base_holidays_by_date(year):
    """대체공휴일을 뺀 그 해 공휴일을 {날짜: [이름, ...]}으로.

    값이 이름 하나가 아니라 목록인 게 중요하다 - 공휴일 두 개가 같은 날일 수 있고
    (2025년 어린이날과 부처님오신날이 둘 다 5월 5일, 2028년 추석 당일이 개천절),
    "겹쳤다"는 사실 자체가 대체공휴일 발생 조건이라 하나로 뭉개면 그 하루를 놓친다."""
    by_date = {}
    for month, day, name in FIXED_DATES:
        if year < HOLIDAY_FIRST_YEAR.get(name, 0):
            continue
        by_date.setdefault(datetime.date(year, month, day).strftime(_ISO), []).append(name)
    for iso, name in _lunar_holidays(year).items():
        by_date.setdefault(iso, []).append(name)
    return by_date


def _next_free_day(day, taken):
    """day 다음날부터, 주말도 아니고 이미 공휴일도 아닌 첫 날을 찾는다."""
    candidate = day + datetime.timedelta(days=1)
    while candidate.weekday() >= 5 or candidate.strftime(_ISO) in taken:
        candidate += datetime.timedelta(days=1)
    return candidate


def holidays_for_year(year):
    """그 해 법정공휴일 전체를 {"YYYY-MM-DD": 이름}으로 (대체공휴일 포함).

    대체공휴일 규칙: 대상 공휴일이 토·일이나 다른 공휴일과 겹치면, 그 뒤 가장 가까운
    "주말도 공휴일도 아닌 날"이 대체공휴일이 된다. 명절 연휴는 연휴 전체를 한 덩어리로
    보고 일요일(또는 다른 공휴일)과 겹칠 때만 하루를 붙인다(LUNAR_FESTIVALS 설명 참고)."""
    by_date = _base_holidays_by_date(year)
    # 같은 날에 공휴일이 둘이면 둘 다 적는다(예: "어린이날·부처님오신날").
    result = {iso: "·".join(names) for iso, names in by_date.items()}

    def overlapped(iso):
        return len(by_date[iso]) > 1

    # 1) 명절 연휴 - 연휴 전체를 한 덩어리로 보고, 그 안에 일요일이 있거나 다른
    #    공휴일과 겹친 날이 있으면 연휴 다음 첫 평일 하루를 붙인다.
    for festival in LUNAR_FESTIVALS:
        days = sorted(_parse(d) for d, names in by_date.items() if festival in names)
        if not days:
            continue
        if any(d.weekday() == 6 or overlapped(d.strftime(_ISO)) for d in days):
            result[_next_free_day(days[-1], result).strftime(_ISO)] = f"{festival} 대체공휴일"

    # 2) 나머지 대상 공휴일 - 토·일이거나 다른 공휴일과 겹치면 하루씩 뒤로.
    for iso in sorted(by_date):
        names = by_date[iso]
        if any(n in LUNAR_FESTIVALS for n in names):
            continue  # 연휴는 위에서 한 덩어리로 이미 처리했다 - 여기서 또 붙이면 두 번이다
        targets = [n for n in names if n in SUBSTITUTE_TARGETS]
        if not targets:
            continue
        day = _parse(iso)
        if day.weekday() < 5 and not overlapped(iso):
            continue
        result[_next_free_day(day, result).strftime(_ISO)] = f"{targets[0]} 대체공휴일"

    return result


def holidays_between(first_year, last_year):
    """여러 해의 공휴일을 한 dict로 합쳐 돌려준다(달력이 달을 넘길 때마다 서버에
    다시 묻지 않도록, 창을 열 때 한 번에 넘겨주려고)."""
    merged = {}
    for year in range(first_year, last_year + 1):
        merged.update(holidays_for_year(year))
    return merged


def known_years():
    """음력 명절 표가 있는 연도 범위 (first, last). 표를 늘리면 자동으로 따라온다."""
    years = sorted(LUNAR_DATES)
    return (years[0], years[-1]) if years else (0, -1)
