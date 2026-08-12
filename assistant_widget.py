"""
회사용 데스크톱 비서 위젯
--------------------------------
- 화면 좌측 하단에 항상 위에 떠 있는 작은 아이콘 버튼을 표시
- 아이콘을 누르면 위쪽으로 링크 뱃지 패널이 펼쳐짐
- 각 뱃지를 누르면 기본 브라우저로 해당 링크가 열림
- 다시 아이콘을 누르거나 바깥을 클릭하면 패널이 닫힘

실제 구현은 config.py(설정 상수) / redmine_api.py(레드마인 API) /
ui_common.py(그리기·텍스트 유틸) / widget.py(AssistantWidget 클래스)로 나뉘어 있고,
이 파일은 그걸 불러와 실행만 하는 진입점이다.

필요 라이브러리: 파이썬 표준 라이브러리만 사용 (tkinter, webbrowser)
실행: python assistant_widget.py
"""

from widget import AssistantWidget

if __name__ == "__main__":
    AssistantWidget().run()
