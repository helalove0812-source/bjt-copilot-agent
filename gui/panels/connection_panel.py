from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton, QSizePolicy
except ImportError:
    QComboBox = QGridLayout = QGroupBox = QLabel = QPushButton = QSizePolicy = None


def build_connection_panel_model() -> PanelModel:
    return PanelModel(
        name='连接',
        fields=['mode', 'device', 'status'],
        buttons=['connect', 'disconnect'],
    )


if QGroupBox is not None:

    class ConnectionPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__('连接', parent)
            self.model = build_connection_panel_model()
            self.mode_combo = QComboBox()
            self.mode_combo.addItem('仿真', 'simulation')
            self.mode_combo.addItem('硬件', 'hardware')
            self.device_combo = QComboBox()
            self.device_combo.addItem('仿真后端', 'simulation')
            self.device_combo.addItem('雨骤 Model S (pyRD)', 'hardware')
            self.status_label = QLabel('未连接')
            self.status_label.setObjectName('StatusValue')
            self.connect_button = QPushButton('连接')
            self.connect_button.setObjectName('PrimaryButton')
            self.connect_button.setProperty("primary", "true")
            self.disconnect_button = QPushButton('断开')
            self.disconnect_button.setProperty("secondary", "true")
            self.mode_combo.setFixedHeight(36)
            self.device_combo.setFixedHeight(36)
            self.connect_button.setMinimumHeight(42)
            self.disconnect_button.setMinimumHeight(42)
            self.connect_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.disconnect_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            layout = QGridLayout(self)
            layout.setContentsMargins(16, 26, 16, 16)
            layout.setHorizontalSpacing(16)
            layout.setVerticalSpacing(14)
            layout.setColumnStretch(1, 1)
            layout.addWidget(QLabel('模式'), 0, 0)
            layout.addWidget(self.mode_combo, 0, 1)
            layout.addWidget(QLabel('设备'), 1, 0)
            layout.addWidget(self.device_combo, 1, 1)
            layout.addWidget(QLabel('状态'), 2, 0)
            layout.addWidget(self.status_label, 2, 1)
            layout.addWidget(self.connect_button, 3, 0)
            layout.addWidget(self.disconnect_button, 3, 1)
            layout.setRowMinimumHeight(0, 40)
            layout.setRowMinimumHeight(1, 40)
            layout.setRowMinimumHeight(2, 34)
            layout.setRowMinimumHeight(3, 42)

        def selected_mode(self) -> str:
            return str(self.mode_combo.currentData())

        def selected_device(self) -> str:
            return str(self.device_combo.currentData())

else:

    class ConnectionPanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_connection_panel_model()
            self.mode_options = ['仿真', '硬件']
            self.device_options = ['仿真后端', '雨骤 Model S (pyRD)']
            self.status_text = '未连接'

        def selected_mode(self) -> str:
            return 'simulation'

        def selected_device(self) -> str:
            return 'simulation'
