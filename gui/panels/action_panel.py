from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtWidgets import QLabel, QGroupBox, QPushButton, QSizePolicy, QVBoxLayout
except ImportError:
    QLabel = QGroupBox = QPushButton = QSizePolicy = QVBoxLayout = None


def build_action_panel_model() -> PanelModel:
    return PanelModel(
        name='操作',
        buttons=['detect_type', 'measure_static', 'measure_vce_sat', 'scan_curves', 'beta_linearity', 'full_suite', 'emergency_stop'],
    )


if QGroupBox is not None:

    class ActionPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__('操作', parent)
            self.model = build_action_panel_model()
            self.buttons = {}
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 26, 16, 16)
            layout.setSpacing(10)
            labels = [
                ('detect_type', '识别类型'),
                ('measure_static', '静态点'),
                ('measure_vce_sat', '测 Vce(sat)'),
                ('beta_linearity', 'β 线性度'),
                ('scan_curves', '扫描曲线'),
                ('full_suite', '完整测试'),
                ('emergency_stop', '紧急停止'),
            ]
            mode_caption = QLabel("测试模式")
            mode_caption.setObjectName("FormLabel")
            for index, (key, text) in enumerate(labels):
                button = QPushButton(text)
                button.setMinimumHeight(38 if key != "emergency_stop" else 44)
                button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                if key == 'full_suite':
                    button.setProperty("primary", "true")
                    button.setProperty("modeOption", "true")
                elif key == 'emergency_stop':
                    button.setProperty("danger", "true")
                    button.setObjectName("EmergencyStopButton")
                else:
                    button.setProperty("secondary", "true")
                    if key in {"measure_vce_sat", "beta_linearity", "scan_curves"}:
                        button.setProperty("modeOption", "true")
                    else:
                        button.setProperty("actionRow", "true")
                self.buttons[key] = button
                if key == "measure_vce_sat":
                    layout.addWidget(mode_caption)
                layout.addWidget(button)

else:

    class ActionPanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_action_panel_model()
            self.buttons = list(self.model.buttons)
