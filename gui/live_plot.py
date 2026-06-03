from __future__ import annotations

import os

os.environ.setdefault("QT_API", "pyside6")

from matplotlib.figure import Figure
from matplotlib import rcParams

from gui.models import PlotModel

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtWidgets import QApplication
except Exception:
    FigureCanvasQTAgg = None
    QApplication = None


def build_live_plot_model() -> PlotModel:
    return PlotModel(title='Ic-Vce 输出特性', x_label='Vce (V)', y_label='Ic (A)')


def _qt_canvas_available() -> bool:
    return FigureCanvasQTAgg is not None and QApplication is not None and QApplication.instance() is not None


def _style_axes(figure: Figure) -> None:
    rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "PingFang SC", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False
    axes = figure.axes[0]
    figure.patch.set_facecolor("#FFFFFF")
    figure.subplots_adjust(left=0.10, right=0.97, top=0.85, bottom=0.22)
    axes.set_facecolor("#FFFFFF")
    axes.grid(True, color="#E5E5EA", linewidth=1.0)
    axes.tick_params(colors="#9A9AA0", labelsize=10)
    axes.title.set_color("#1D1D1F")
    axes.title.set_fontweight("semibold")
    axes.xaxis.label.set_color("#6E6E73")
    axes.yaxis.label.set_color("#6E6E73")
    axes.spines['top'].set_visible(False)
    axes.spines['right'].set_visible(False)
    axes.spines['left'].set_color("#D2D2D7")
    axes.spines['bottom'].set_color("#D2D2D7")
    axes.text(
        0.5,
        0.5,
        "等待测量数据",
        transform=axes.transAxes,
        ha="center",
        va="center",
        color="#9A9AA0",
        fontsize=14,
    )


if FigureCanvasQTAgg is not None:

    class LivePlotWidget(FigureCanvasQTAgg):
        def __init__(self, parent=None):
            model = build_live_plot_model()
            figure = Figure(figsize=(6, 4))
            axes = figure.add_subplot(111)
            axes.set_title(model.title)
            axes.set_xlabel(model.x_label)
            axes.set_ylabel(model.y_label)
            _style_axes(figure)
            self.figure = figure
            self.axes = axes
            self.model = model
            if not _qt_canvas_available():
                self.parent = parent
                return
            super().__init__(figure)
            self.setMinimumHeight(360)
            self.setStyleSheet("background: #ffffff; border: none; border-radius: 12px;")
            if parent is not None:
                self.setParent(parent)

        def plot_title(self) -> str:
            return self.model.title

else:

    class LivePlotWidget:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_live_plot_model()
            self.figure = Figure(figsize=(6, 4))
            self.axes = self.figure.add_subplot(111)
            self.axes.set_title(self.model.title)
            self.axes.set_xlabel(self.model.x_label)
            self.axes.set_ylabel(self.model.y_label)
            _style_axes(self.figure)

        def plot_title(self) -> str:
            return self.model.title
