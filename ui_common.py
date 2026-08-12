"""
공용 그리기/텍스트/아이콘 유틸리티 - tkinter Canvas에 둥근 사각형/카드를 그리거나,
아이콘 이미지를 원하는 색 실루엣으로 만들거나, 긴 텍스트를 말줄임표로 자르는 등
여러 창에서 공통으로 쓰는 순수 헬퍼 함수들이다.
"""

import webbrowser

import tkinter as tk

from config import (
    BG_COLOR,
    BROWSER,
    GO_ICON_FILE,
    GO_ICON_SIZE,
    ISSUE_BADGE_H,
    ISSUE_LINE_GAP,
    ISSUE_ROW_PAD_Y,
    SHADOW_COLOR,
    SHADOW_OFFSET,
    TOAST_ICON_FILE,
    TOAST_ICON_SIZE,
)


def open_url(url):
    """BROWSER가 지정돼 있으면 해당 브라우저로, 아니면 시스템 기본 브라우저로 연다."""
    if BROWSER:
        try:
            webbrowser.get(f'"{BROWSER}" %s').open(url)
            return
        except Exception:
            pass  # 지정 브라우저 실행 실패 시 기본 브라우저로 폴백
    webbrowser.open(url)


def load_toast_icon():
    """새 이슈 알림 토스트에 쓸 알람 아이콘을 흰색 실루엣으로 TOAST_ICON_SIZE만큼 불러온다.
    (포인트 컬러 배지 위에 올릴 것이므로 원래 색과 상관없이 흰색으로 통일한다)"""
    return load_icon_glyph(TOAST_ICON_FILE, TOAST_ICON_SIZE, "#FFFFFF")


def load_go_icon():
    """뱃지의 "바로 이동" 화살표 아이콘을 GO_ICON_SIZE로 불러온다. 원본은 검정 원
    배경 위에 흰 화살표인데, 어두운 카드 위에서 검정 원이 안 보이므로 원(어두운
    픽셀)만 포인트 컬러로 바꾸고 화살표(밝은 픽셀)는 흰색 그대로 살린다."""
    try:
        from PIL import Image, ImageTk
        img = Image.open(GO_ICON_FILE).convert("RGBA")
        r, g, b = tuple(int(BG_COLOR[i:i + 2], 16) for i in (1, 3, 5))
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                pr, pg, pb, pa = px[x, y]
                if pa == 0:
                    continue
                if (pr + pg + pb) / 3 < 128:
                    px[x, y] = (r, g, b, pa)  # 어두운(원) 픽셀 → 포인트 컬러
                else:
                    px[x, y] = (255, 255, 255, pa)  # 밝은(화살표) 픽셀 → 흰색
        img = img.resize((GO_ICON_SIZE, GO_ICON_SIZE), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except ImportError:
        return tk.PhotoImage(file=str(GO_ICON_FILE))


def load_icon_glyph(path, size, color):
    """아이콘 이미지를 원래 색과 상관없이 color 단색 실루엣으로 만들어 size로 불러온다.
    (원본의 알파 채널을 마스크로 써서 모양만 남기고 전부 color로 칠한다)"""
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGBA")
        alpha = img.split()[3]
        r, g, b = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        solid = Image.new("RGBA", img.size, (r, g, b, 0))
        solid.putalpha(alpha)
        solid = solid.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(solid)
    except ImportError:
        return tk.PhotoImage(file=str(path))


def draw_rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """캔버스에 둥근 모서리 사각형(뱃지 모양)을 그린다."""
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def draw_card(canvas, w, h, radius, fill, tags="badge"):
    """캔버스(w×h) 안에 부드러운 그림자가 깔린 둥근 카드를 그린다.
    카드가 그림자만큼 살짝 안쪽으로 들어가므로, 텍스트/아이콘을 배치할
    카드 중심 좌표 (cx, cy)를 반환한다."""
    cx2, cy2 = w - 1 - SHADOW_OFFSET, h - 1 - SHADOW_OFFSET
    draw_rounded_rect(
        canvas, SHADOW_OFFSET, SHADOW_OFFSET, w - 1, h - 1, radius,
        fill=SHADOW_COLOR, outline="", tags=tags,
    )
    draw_rounded_rect(
        canvas, 0, 0, cx2, cy2, radius,
        fill=fill, outline="", tags=tags,
    )
    return cx2 / 2, cy2 / 2


def truncate_text(font_obj, text, max_width):
    """max_width(px) 안에 들어가도록 text를 말줄임표(…)로 잘라 반환한다.
    max_width가 충분하면 원본 그대로 반환한다."""
    if max_width <= 0:
        return "…"
    if font_obj.measure(text) <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font_obj.measure(text[:mid] + "…") <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + "…") if lo > 0 else "…"


def wrap_text_two_lines(font_obj, text, first_width, rest_width=None):
    """text를 최대 2줄로 줄바꿈한다. 첫 줄은 first_width(px), 둘째 줄은 rest_width(px)
    안에 들어가야 하며, rest_width를 생략하면 첫 줄과 같은 너비를 쓴다.
    (첫 줄 앞에 id 뱃지 등이 붙어 첫 줄만 폭이 좁은 경우에 쓴다)
    2줄에도 다 안 들어가면 2번째 줄 끝을 말줄임표(…)로 자른다."""
    if rest_width is None:
        rest_width = first_width
    if font_obj.measure(text) <= first_width:
        return [text]

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font_obj.measure(text[:mid]) <= first_width:
            lo = mid
        else:
            hi = mid - 1
    line1 = text[:lo] if lo > 0 else text[:1]
    rest = text[len(line1):]

    if font_obj.measure(rest) <= rest_width:
        return [line1, rest]
    return [line1, truncate_text(font_obj, rest, rest_width)]


def issue_row_height(font_obj):
    """이슈 id 뱃지 + 제목(최대 2줄, 뱃지 옆에 이어서 표시)을 담는 뱃지의 전체 높이(px)를 계산한다."""
    line_h = font_obj.metrics("linespace")
    row1_h = max(ISSUE_BADGE_H, line_h)
    return ISSUE_ROW_PAD_Y + row1_h + ISSUE_LINE_GAP + line_h + ISSUE_ROW_PAD_Y
