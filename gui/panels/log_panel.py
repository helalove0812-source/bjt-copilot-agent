from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtWidgets import QGroupBox, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout
except ImportError:
    QGroupBox = QLabel = QPlainTextEdit = QPushButton = QVBoxLayout = None


def build_log_panel_model() -> PanelModel:
    return PanelModel(name='日志', buttons=['clear_log'], read_only=True)


if QGroupBox is not None:

    class LogPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__('', parent)
            self.model = build_log_panel_model()
            self.log_view = QPlainTextEdit()
            self.log_view.setReadOnly(True)
            self.log_view.setMinimumHeight(104)
            self.clear_button = QPushButton('清空日志')
            self.clear_button.setMinimumHeight(40)
            self.header_label = QLabel('日志')
            self.header_label.setProperty("role", "panelTitle")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)
            self.log_view.setPlaceholderText('暂无事件')
            layout.addWidget(self.header_label)
            layout.addWidget(self.log_view)
            layout.addWidget(self.clear_button)

else:

    class LogPanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_log_panel_model()
            self.lines = []
