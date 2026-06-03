from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PanelModel:
    name: str
    fields: List[str] = field(default_factory=list)
    buttons: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    read_only: bool = False


@dataclass
class PlotModel:
    title: str
    x_label: str
    y_label: str


@dataclass
class WindowModel:
    connection: PanelModel
    hardware_config: PanelModel
    actions: PanelModel
    ai: PanelModel
    plan_table: PanelModel
    live_values: PanelModel
    log: PanelModel
    plot: PlotModel


def build_default_window_model() -> WindowModel:
    from gui.live_plot import build_live_plot_model
    from gui.panels.ai_panel import build_ai_panel_model
    from gui.panels.action_panel import build_action_panel_model
    from gui.panels.connection_panel import build_connection_panel_model
    from gui.panels.hw_config_panel import build_hw_config_panel_model
    from gui.panels.live_value_panel import build_live_value_panel_model
    from gui.panels.log_panel import build_log_panel_model
    from gui.panels.plan_table_panel import build_plan_table_panel_model

    return WindowModel(
        connection=build_connection_panel_model(),
        hardware_config=build_hw_config_panel_model(),
        actions=build_action_panel_model(),
        ai=build_ai_panel_model(),
        plan_table=build_plan_table_panel_model(),
        live_values=build_live_value_panel_model(),
        log=build_log_panel_model(),
        plot=build_live_plot_model(),
    )
