from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtWidgets import QFrame, QGridLayout, QGroupBox, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QGraphicsDropShadowEffect, QSizePolicy
    from PySide6.QtGui import QColor
except ImportError:
    QFrame = QGridLayout = QGroupBox = QLabel = QVBoxLayout = QWidget = QHBoxLayout = QGraphicsDropShadowEffect = QSizePolicy = QColor = None


def apply_soft_shadow(widget: QWidget):
    if QGraphicsDropShadowEffect is not None:
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(14)
        effect.setColor(QColor(0, 0, 0, 10))
        effect.setOffset(0, 1)
        widget.setGraphicsEffect(effect)


def build_live_value_panel_model() -> PanelModel:
    return PanelModel(
        name='实时数值',
        metrics=['vbe', 'ib', 'vce', 'ic', 'beta', 'region'],
    )


if QGroupBox is not None:

    class LiveValuePanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__('', parent)
            self.model = build_live_value_panel_model()
            self.value_labels = {}
            layout = QGridLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setHorizontalSpacing(14)
            layout.setVerticalSpacing(14)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
            header_label = QLabel('实时数值', self)
            header_label.setProperty("role", "panelTitle")
            layout.addWidget(header_label, 0, 0, 1, 3)
            for index, key in enumerate(self.model.metrics):
                card = QFrame(self)
                card.setObjectName("MetricCard")
                card.setMinimumHeight(64)
                card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(16, 16, 16, 16)
                card_layout.setSpacing(6)

                title_label = QLabel(_metric_label(key), card)
                title_label.setProperty("role", "valueCaption")
                value_label = QLabel("--", card)
                value_label.setProperty("role", "valueDisplay")

                card_layout.addWidget(title_label)
                card_layout.addStretch(1)
                card_layout.addWidget(value_label)
                self.value_labels[key] = value_label
                apply_soft_shadow(card)

                row, col = divmod(index, 3)
                layout.setRowMinimumHeight(row + 1, 64)
                layout.addWidget(card, row + 1, col)

else:

    class LiveValuePanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_live_value_panel_model()
            self.values = dict((key, '--') for key in self.model.metrics)


def _metric_label(key: str) -> str:
    labels = {
        "vbe": "基射电压 Vbe",
        "ib": "基极电流 Ib",
        "vce": "集射电压 Vce",
        "ic": "集电极电流 Ic",
        "beta": "电流增益 Beta",
        "region": "工作区状态",
    }
    return labels.get(key, key.upper())
