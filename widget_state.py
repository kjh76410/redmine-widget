"""위젯 자체의 상태 - 아이콘을 어디에 두었는지, 윈도우 시작 시 자동 실행할지.

레드마인 데이터(프로젝트/일감/즐겨찾기)는 redmine_api.py가 다루고, 여기는 "이 위젯을
이 PC에서 어떻게 쓰는가"만 담는다. 둘 다 순수 데이터/OS 계층이라 UI 프레임워크에
안 묶여 있다.
"""

import json
import sys
import winreg
from pathlib import Path

POSITION_FILE = Path(__file__).parent / "widget_position.json"
SETTINGS_FILE = Path(__file__).parent / "widget_settings.json"

# 자동 실행은 HKCU\...\Run 레지스트리 값 하나로 처리한다. 시작프로그램 폴더에 바로가기를
# 만드는 방법도 있지만 .lnk를 만들려면 COM(WScript.Shell)이 필요하고, .bat을 넣으면 부팅
# 때마다 검은 콘솔 창이 번쩍인다. 레지스트리는 표준 라이브러리(winreg)만으로 끝난다.
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "RedmineWidget"


def load_icon_position():
    """저장해 둔 아이콘 위치 (x, y)를 물리 픽셀로 돌려준다. 없거나 깨졌으면 None.

    화면 밖으로 나가지 않게 자르는 건 호출부 몫이다 - 저장한 뒤에 해상도나 배율이
    바뀌었을 수 있는데, 그때 기준이 되는 화면 크기는 여기서 알 수 없다."""
    if not POSITION_FILE.exists():
        return None
    try:
        with open(POSITION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return int(data["x"]), int(data["y"])
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
        return None


def save_icon_position(x, y):
    try:
        with open(POSITION_FILE, "w", encoding="utf-8") as f:
            json.dump({"x": int(x), "y": int(y)}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 위치 저장 실패로 위젯이 멈출 이유는 없다 - 다음 실행에 기본 자리로 뜬다


def always_on_top_enabled():
    """위젯(아이콘/패널)을 다른 창 위에 항상 띄울지. 기본값 True - pywebview
    on_top=True로 만들던 원래 동작 그대로다(우클릭 메뉴에서 끄기 전까지는 그대로 유지)."""
    if not SETTINGS_FILE.exists():
        return True
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("always_on_top", True))
    except (json.JSONDecodeError, OSError, TypeError):
        return True


def set_always_on_top(enabled):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"always_on_top": bool(enabled)}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 저장 실패해도 이번 실행 중엔 App.always_on_top(메모리)이 그대로 적용된다


def _launch_command():
    """부팅 때 실행할 명령줄. 콘솔 창이 안 뜨도록 python.exe 대신 pythonw.exe를 쓴다."""
    if getattr(sys, "frozen", False):  # 나중에 exe로 묶더라도 그대로 동작하게
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = Path(__file__).resolve().parent / "webapp" / "main.py"
    return f'"{exe}" "{script}"'


def autostart_enabled():
    """Run 키에 우리 값이 있으면 켜진 것으로 본다. 값의 내용(경로)까지는 비교하지 않는다 -
    파이썬을 옮겼거나 프로젝트를 다른 데로 옮기면 경로가 낡을 수 있는데, 그건 켤 때
    현재 경로로 덮어쓰면서 저절로 고쳐진다(set_autostart 참고)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_VALUE_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled):
    """자동 실행을 켜거나 끈다. 실제로 적용된 상태를 돌려준다(실패하면 원래 상태 그대로)."""
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass  # 이미 꺼져 있었다
    except OSError:
        pass
    return autostart_enabled()
