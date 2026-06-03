from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QComboBox
except ImportError:
    Qt = QGridLayout = QGroupBox = QLabel = QLineEdit = QComboBox = None


def build_hw_config_panel_model() -> PanelModel:
    return PanelModel(
        name='硬件配置',
        fields=['r_b_ohm', 'r_c_ohm', 'ic_max_a', 'pmax_w', 'lin_ic_range', 'lin_vce_window'],
    )


if QGroupBox is not None:

    class HwConfigPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__('硬件配置', parent)
            self.model = build_hw_config_panel_model()
            self.setMinimumHeight(384)
            self.rb_input = QLineEdit('22000')
            self.rc_input = QLineEdit('220')
            self.ic_limit_input = QLineEdit('0.03')
            self.pmax_input = QLineEdit('0.30')
            self.ic_range_input = QLineEdit('0.0005,0.02')
            self.vce_window_input = QLineEdit('2.0,4.0')
            self.scan_mode_combo = QComboBox()
            self.scan_mode_combo.addItem('软件轮询 (慢)', 'software')
            self.scan_mode_combo.addItem('硬件加速 (快)', 'hardware')
            for input_box in (
                self.rb_input,
                self.rc_input,
                self.ic_limit_input,
                self.pmax_input,
                self.ic_range_input,
                self.vce_window_input,
                self.scan_mode_combo,
            ):
                input_box.setFixedHeight(36)

            layout = QGridLayout(self)
            layout.setContentsMargins(16, 26, 16, 16)
            layout.setHorizontalSpacing(16)
            layout.setVerticalSpacing(10)
            rows = [
                ('基极电阻 (Ohm)', self.rb_input),
                ('集电极电阻 (Ohm)', self.rc_input),
                ('Ic 上限 (A)', self.ic_limit_input),
                ('功耗上限 (W)', self.pmax_input),
                ('线性 Ic 范围', self.ic_range_input),
                ('线性 Vce 窗口', self.vce_window_input),
                ('扫描模式', self.scan_mode_combo),
            ]
            for row, (text, input_box) in enumerate(rows):
                label = QLabel(text)
                label.setObjectName('FormLabel')
                label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                layout.addWidget(label, row, 0)
                layout.addWidget(input_box, row, 1)
                layout.setRowMinimumHeight(row, 42)
            layout.setColumnMinimumWidth(0, 130)
            layout.setColumnStretch(1, 1)

else:

    class HwConfigPanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_hw_config_panel_model()
            self.defaults = {
                'r_b_ohm': '22000',
                'r_c_ohm': '220',
                'ic_max_a': '0.03',
                'pmax_w': '0.30',
                'lin_ic_range': '0.0005,0.02',
                'lin_vce_window': '2.0,4.0',
            }
