from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtWidgets import (
        QGridLayout,
        QGroupBox,
        QLabel,
        QLineEdit,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )
except ImportError:
    QGridLayout = QGroupBox = QLabel = QLineEdit = QPushButton = QTableWidget = QTableWidgetItem = QVBoxLayout = None


def build_plan_table_panel_model() -> PanelModel:
    return PanelModel(
        name="测试点",
        fields=["plan_limits", "static_points"],
        buttons=["apply_plan", "add_point", "remove_point"],
    )


if QGroupBox is not None:

    class PlanTablePanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__("", parent)
            self.model = build_plan_table_panel_model()
            self.header_label = QLabel("测试点")
            self.header_label.setProperty("role", "panelTitle")
            self.ic_limit_input = QLineEdit()
            self.power_limit_input = QLineEdit()
            for input_box in (self.ic_limit_input, self.power_limit_input):
                input_box.setMinimumHeight(34)

            self.points_table = QTableWidget(0, 2)
            self.points_table.setHorizontalHeaderLabels(["Vcc", "Vbb"])
            self.points_table.setMinimumHeight(150)
            self.points_table.verticalHeader().setVisible(False)
            self.points_table.horizontalHeader().setStretchLastSection(True)

            self.apply_plan_button = QPushButton("应用表格到计划")
            self.add_point_button = QPushButton("添加点")
            self.remove_point_button = QPushButton("删除点")
            for button in (
                self.apply_plan_button,
                self.add_point_button,
                self.remove_point_button,
            ):
                button.setMinimumHeight(36)
                button.setProperty("secondary", "true")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(10)

            header_layout = QGridLayout()
            header_layout.setHorizontalSpacing(10)
            header_layout.addWidget(self.header_label, 0, 0)
            header_layout.addWidget(self.apply_plan_button, 0, 1)
            header_layout.addWidget(self.add_point_button, 0, 2)
            header_layout.addWidget(self.remove_point_button, 0, 3)
            header_layout.setColumnStretch(0, 1)
            layout.addLayout(header_layout)

            limits_layout = QGridLayout()
            limits_layout.setHorizontalSpacing(10)
            limits_layout.setVerticalSpacing(8)
            limits_layout.addWidget(QLabel("Ic 上限(A)"), 0, 0)
            limits_layout.addWidget(self.ic_limit_input, 0, 1)
            limits_layout.addWidget(QLabel("功耗(W)"), 0, 2)
            limits_layout.addWidget(self.power_limit_input, 0, 3)
            limits_layout.setColumnStretch(1, 1)
            limits_layout.setColumnStretch(3, 1)
            layout.addLayout(limits_layout)
            layout.addWidget(self.points_table)

        def load_plan(self, plan) -> None:
            self.ic_limit_input.setText(str(plan.ic_limit_a))
            self.power_limit_input.setText(str(plan.power_limit_w))
            self.points_table.setRowCount(0)
            for point in plan.static_points:
                self.add_static_point(point["vcc"], point["vbb"])

        def add_static_point(self, vcc: float = 3.0, vbb: float = 2.0) -> None:
            row = self.points_table.rowCount()
            self.points_table.insertRow(row)
            self.points_table.setItem(row, 0, QTableWidgetItem(str(vcc)))
            self.points_table.setItem(row, 1, QTableWidgetItem(str(vbb)))

        def remove_selected_point(self) -> None:
            row = self.points_table.currentRow()
            if row >= 0:
                self.points_table.removeRow(row)

        def edited_plan_values(self) -> dict:
            points = []
            for row in range(self.points_table.rowCount()):
                vcc_item = self.points_table.item(row, 0)
                vbb_item = self.points_table.item(row, 1)
                if vcc_item is None or vbb_item is None:
                    continue
                points.append(
                    {
                        "vcc": float(vcc_item.text()),
                        "vbb": float(vbb_item.text()),
                    }
                )
            return {
                "ic_limit_a": float(self.ic_limit_input.text()),
                "power_limit_w": float(self.power_limit_input.text()),
                "static_points": points,
            }

else:

    class PlanTablePanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_plan_table_panel_model()

        def load_plan(self, plan) -> None:
            return None

        def add_static_point(self, vcc: float = 3.0, vbb: float = 2.0) -> None:
            return None

        def remove_selected_point(self) -> None:
            return None

        def edited_plan_values(self) -> dict:
            return {
                "ic_limit_a": 0.03,
                "power_limit_w": 0.3,
                "static_points": [],
            }
