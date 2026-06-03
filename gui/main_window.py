from __future__ import annotations

from gui.live_plot import LivePlotWidget
from gui.models import build_default_window_model
from gui.panels.ai_panel import AIPanel
from gui.panels.action_panel import ActionPanel
from gui.panels.connection_panel import ConnectionPanel
from gui.panels.hw_config_panel import HwConfigPanel
from gui.panels.live_value_panel import LiveValuePanel
from gui.panels.log_panel import LogPanel
from gui.panels.plan_table_panel import PlanTablePanel
from gui.style import APP_STYLESHEET
from app.orchestrator import AppOrchestrator
from ai.conversation import AIConversationState
from core.types import HwConfig
import os
import traceback

try:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QApplication,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
        QGraphicsDropShadowEffect,
        QScrollArea,
        QMessageBox,
    )
except ImportError:
    Qt = QThread = Signal = QColor = QFrame = QHBoxLayout = QLabel = QMainWindow = QApplication = QSizePolicy = QVBoxLayout = QWidget = QGraphicsDropShadowEffect = QScrollArea = QMessageBox = None


def apply_soft_shadow(widget: QWidget):
    if QGraphicsDropShadowEffect is not None:
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(18)
        effect.setColor(QColor(0, 0, 0, 14))
        effect.setOffset(0, 2)
        widget.setGraphicsEffect(effect)


if QThread is not None:
    class WorkerThread(QThread):
        result_ready = Signal(object)
        error_occurred = Signal(str)

        def __init__(self, func, *args, **kwargs):
            super().__init__()
            self.func = func
            self.args = args
            self.kwargs = kwargs

        def run(self):
            try:
                res = self.func(*self.args, **self.kwargs)
                self.result_ready.emit(res)
            except Exception as e:
                self.error_occurred.emit(str(e))


def qt_available() -> bool:
    return QMainWindow is not None


if QMainWindow is not None:

    class MainWindow(QMainWindow):
        _app_ref = None

        def __init__(self):
            if QApplication.instance() is None:
                MainWindow._app_ref = QApplication([])
            super().__init__()
            self.model = build_default_window_model()
            self.uses_qt = True
            self.connection_panel = ConnectionPanel(self)
            self.hw_config_panel = HwConfigPanel(self)
            self.action_panel = ActionPanel(self)
            self.ai_panel = AIPanel(self)
            self.plan_table_panel = PlanTablePanel(self)
            self.live_value_panel = LiveValuePanel(self)
            self.log_panel = LogPanel(self)
            self.live_plot = LivePlotWidget(self)

            self.live_value_panel.setMinimumHeight(150)
            self.log_panel.setMinimumHeight(220)
            self.live_plot.setMinimumHeight(300)
            self.connection_panel.setMinimumHeight(236)
            self.hw_config_panel.setMinimumHeight(384)
            self.action_panel.setMinimumHeight(390)
            self.ai_panel.setMinimumHeight(560)
            self.plan_table_panel.setMinimumHeight(300)

            self.setWindowTitle('BJT 测试台')
            self.resize(1320, 860)
            self.setMinimumSize(1080, 720)
            self.setStyleSheet(APP_STYLESHEET)
            self.statusBar().showMessage('未连接')
            
            # Use light gray background
            self.setAutoFillBackground(True)
            p = self.palette()
            p.setColor(self.backgroundRole(), QColor("#ECECEE"))
            self.setPalette(p)

            central = QWidget(self)
            central.setObjectName('AppChrome')
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            app_body = QWidget(central)
            app_body.setObjectName('AppChrome')
            body_layout = QHBoxLayout(app_body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)

            sidebar_rail = QWidget()
            sidebar_rail.setObjectName('Sidebar')
            sidebar_rail.setFixedWidth(312)
            sidebar_rail_layout = QVBoxLayout(sidebar_rail)
            sidebar_rail_layout.setContentsMargins(0, 0, 0, 0)
            sidebar_rail_layout.setSpacing(0)

            sidebar_scroll = QScrollArea(sidebar_rail)
            sidebar_scroll.setWidgetResizable(True)
            sidebar_scroll.setFrameShape(QFrame.NoFrame)
            sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sidebar_scroll.setStyleSheet("QScrollArea { background: transparent; }")

            sidebar_container = QWidget()
            sidebar_container.setObjectName('SidebarContent')
            left_layout = QVBoxLayout(sidebar_container)
            left_layout.setContentsMargins(16, 20, 16, 24)
            left_layout.setSpacing(16)

            workspace = QWidget()
            workspace.setMinimumSize(680, 900)
            right_layout = QVBoxLayout(workspace)
            right_layout.setContentsMargins(32, 32, 32, 40)
            right_layout.setSpacing(20)

            workspace_scroll = QScrollArea()
            workspace_scroll.setWidgetResizable(True)
            workspace_scroll.setFrameShape(QFrame.NoFrame)
            workspace_scroll.setStyleSheet("QScrollArea { background: transparent; }")

            bottom_workspace = QWidget(workspace)
            bottom_layout = QHBoxLayout(bottom_workspace)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(14)

            ai_column = QWidget()
            ai_column.setObjectName('AIColumn')
            ai_column.setFixedWidth(320)
            ai_column_layout = QVBoxLayout(ai_column)
            ai_column_layout.setContentsMargins(0, 0, 0, 0)
            ai_column_layout.setSpacing(0)

            header = QWidget(workspace)
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(16)

            title_stack = QVBoxLayout()
            title_stack.setContentsMargins(0, 0, 0, 0)
            title_stack.setSpacing(2)
            title = QLabel('BJT 测试台')
            title.setObjectName('AppTitle')
            subtitle = QLabel('雨骤 Model S')
            subtitle.setObjectName('AppSubtitle')
            title_stack.addWidget(title)
            title_stack.addWidget(subtitle)

            status_pill = QLabel('支持硬件 / 仿真')
            status_pill.setObjectName('StatusPill')
            status_pill.setAlignment(Qt.AlignCenter)
            status_pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            header_layout.addLayout(title_stack)
            header_layout.addStretch(1)
            header_layout.addWidget(status_pill)

            divider = QFrame(workspace)
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet('color: #d2d2d7;')

            left_layout.addWidget(self.connection_panel)
            apply_soft_shadow(self.connection_panel)
            left_layout.addWidget(self.hw_config_panel)
            apply_soft_shadow(self.hw_config_panel)
            left_layout.addWidget(self.action_panel)
            apply_soft_shadow(self.action_panel)
            left_layout.addStretch(1)

            sidebar_scroll.setWidget(sidebar_container)
            sidebar_rail_layout.addWidget(sidebar_scroll)

            ai_column_layout.addWidget(self.ai_panel, stretch=1)
            apply_soft_shadow(self.ai_panel)

            right_layout.addWidget(header)
            right_layout.addWidget(divider)
            right_layout.addWidget(self.live_plot, stretch=3)
            right_layout.addWidget(self.live_value_panel, stretch=1)
            apply_soft_shadow(self.live_value_panel)
            bottom_layout.addWidget(self.plan_table_panel, stretch=3)
            apply_soft_shadow(self.plan_table_panel)
            bottom_layout.addWidget(self.log_panel, stretch=2)
            apply_soft_shadow(self.log_panel)
            right_layout.addWidget(bottom_workspace, stretch=4)

            workspace_scroll.setWidget(workspace)
            body_layout.addWidget(sidebar_rail)
            body_layout.addWidget(workspace_scroll, stretch=1)
            body_layout.addWidget(ai_column)
            root_layout.addWidget(app_body)

            self.setCentralWidget(central)

            self.orchestrator = AppOrchestrator(config=HwConfig())
            self._ai_plan = None
            self._ai_state = AIConversationState()
            self._worker = None
            self._bind_events()

        def _bind_events(self):
            self.connection_panel.connect_button.clicked.connect(self._on_connect_clicked)
            self.connection_panel.disconnect_button.clicked.connect(self._on_disconnect_clicked)
            self.action_panel.buttons["detect_type"].clicked.connect(self._on_detect_type_clicked)
            self.action_panel.buttons["measure_static"].clicked.connect(self._on_measure_static_clicked)
            self.action_panel.buttons["scan_curves"].clicked.connect(self._on_scan_curves_clicked)
            self.action_panel.buttons["full_suite"].clicked.connect(self._on_full_suite_clicked)
            self.log_panel.clear_button.clicked.connect(self.log_panel.log_view.clear)
            self.ai_panel.apply_settings_button.clicked.connect(self._on_ai_apply_settings_clicked)
            self.ai_panel.generate_button.clicked.connect(self._on_ai_generate_plan_clicked)
            self.plan_table_panel.apply_plan_button.clicked.connect(self._on_ai_apply_plan_clicked)
            self.plan_table_panel.add_point_button.clicked.connect(lambda: self.plan_table_panel.add_static_point())
            self.plan_table_panel.remove_point_button.clicked.connect(self.plan_table_panel.remove_selected_point)
            self.ai_panel.run_sim_button.clicked.connect(self._on_ai_run_simulation_clicked)
            self.ai_panel.run_hw_button.clicked.connect(self._on_ai_run_hardware_clicked)

        def _log(self, msg: str):
            self.log_panel.log_view.appendPlainText(msg)
            # Scroll to bottom
            bar = self.log_panel.log_view.verticalScrollBar()
            bar.setValue(bar.maximum())

        def _run_worker(self, func, *args, **kwargs):
            if self._worker is not None and self._worker.isRunning():
                self._log("警告：当前有任务正在运行中...")
                return None
            self._worker = WorkerThread(func, *args, **kwargs)
            self._worker.error_occurred.connect(lambda err: self._log(f"[错误] {err}"))
            self._worker.start()
            return self._worker

        def _get_mode(self):
            return self.connection_panel.selected_mode()

        def _plan_mode(self):
            return self._get_mode()

        def _apply_ai_settings(self):
            settings = self.ai_panel.ai_settings()
            ai_mode = settings.get("ai_mode", "local") or "local"
            provider = settings.get("provider", "deepseek") or "deepseek"
            model = settings.get("model", "").strip()
            api_key = settings.get("api_key", "").strip()

            os.environ["BJT_AI_MODE"] = ai_mode
            os.environ["BJT_AI_PROVIDER"] = provider
            if provider == "deepseek":
                if model:
                    os.environ["DEEPSEEK_MODEL"] = model
                if api_key:
                    os.environ["DEEPSEEK_API_KEY"] = api_key
            elif provider == "openai":
                if model:
                    os.environ["OPENAI_MODEL"] = model
                if api_key:
                    os.environ["OPENAI_API_KEY"] = api_key
            return ai_mode, provider, model, bool(api_key)

        def _on_ai_apply_settings_clicked(self):
            ai_mode, provider, model, has_key = self._apply_ai_settings()
            key_status = "已设置 Key" if has_key else "未填写 Key，将尝试使用环境变量或本地规则"
            self._log(f"[AI] 配置已应用：{ai_mode} / {provider} / {model or '默认模型'}，{key_status}。")

        def _format_ai_plan(self, summary, plan, provider):
            return "\n".join(
                [
                    summary,
                    "",
                    f"Provider: {provider}",
                    f"型号: {plan.model} ({plan.bjt_type})",
                    f"目标: {plan.goal} / {plan.depth}",
                    f"模式: {plan.mode}",
                    f"Vcc: {min(plan.vcc_steps):.3f} - {max(plan.vcc_steps):.3f} V",
                    f"Vbb: {min(plan.vbb_steps):.3f} - {max(plan.vbb_steps):.3f} V",
                    f"Ic 上限: {plan.ic_limit_a * 1000:.2f} mA",
                    f"功耗上限: {plan.power_limit_w * 1000:.1f} mW",
                    f"静态点: {len(plan.static_points)} 个",
                ]
            )

        def _build_ai_plan(self, request_text, mode):
            from ai.assistant import summarize_plan_with_ai
            from ai.conversation import apply_intent_to_plan, answer_from_context, interpret_user_message

            intent, used_intent_ai, intent_provider, intent_usage = interpret_user_message(
                request_text,
                self._ai_state,
                default_mode=mode,
            )
            if intent.action in {"execute_simulation", "execute_hardware", "explain_result", "answer"}:
                return {
                    "plan": self._ai_state.current_plan,
                    "summary": answer_from_context(intent, self._ai_state),
                    "used_ai": used_intent_ai,
                    "provider": intent_provider,
                    "usage": intent_usage,
                    "intent": intent,
                }

            plan = apply_intent_to_plan(intent, self._ai_state)
            summary, used_ai, provider, usage = summarize_plan_with_ai(plan, request_text)
            return {
                "plan": plan,
                "summary": summary,
                "used_ai": used_ai or used_intent_ai,
                "provider": provider if used_ai else intent_provider,
                "usage": usage,
                "intent": intent,
            }

        def _on_ai_generate_plan_clicked(self):
            request_text = self.ai_panel.request_text()
            if not request_text:
                self._log("[AI] 请输入测试需求。")
                return
            self._apply_ai_settings()
            self._log("[AI] 正在生成测试计划...")
            worker = self._run_worker(self._build_ai_plan, request_text, self._plan_mode())
            if worker:
                worker.result_ready.connect(self._on_ai_plan_ready)

        def _on_ai_plan_ready(self, payload):
            self._ai_plan = payload["plan"]
            request_text = self.ai_panel.request_text()
            self._ai_state.add("user", request_text)
            self._ai_state.add("assistant", payload["summary"])
            if self._ai_plan is not None:
                self._ai_state.current_plan = self._ai_plan
                self.plan_table_panel.load_plan(self._ai_plan)
            self.ai_panel.set_plan_text(
                self._format_ai_plan(payload["summary"], payload["plan"], payload["provider"])
                if payload["plan"] is not None
                else payload["summary"]
            )
            self.ai_panel.clear_request()
            if payload["plan"] is not None:
                self._log(f"[AI] 测试计划已生成：{payload['plan'].model} / {payload['plan'].goal}")
            else:
                self._log("[AI] 已根据上下文回复。")

        def _on_ai_apply_plan_clicked(self):
            if self._ai_plan is None:
                self._log("[AI] 当前没有可应用的计划。")
                return
            try:
                self._ai_plan = self._plan_from_editor(self._ai_plan)
            except ValueError as exc:
                self._log(f"[AI] 计划表格无效：{exc}")
                return
            self._ai_state.current_plan = self._ai_plan
            self.ai_panel.set_plan_text(
                self._format_ai_plan("已应用表格中的测试点和限制。", self._ai_plan, "editor")
            )
            self._log("[AI] 已应用表格到当前计划。")

        def _plan_from_editor(self, base_plan):
            values = self.plan_table_panel.edited_plan_values()
            points = values["static_points"]
            if not points:
                raise ValueError("至少需要一个静态点")
            ic_limit = max(0.001, min(float(values["ic_limit_a"]), base_plan.ic_limit_a))
            power_limit = max(0.005, min(float(values["power_limit_w"]), base_plan.power_limit_w))
            safe_points = []
            for point in points:
                vcc = max(0.0, min(float(point["vcc"]), max(base_plan.vcc_steps)))
                vbb = max(0.0, min(float(point["vbb"]), max(base_plan.vbb_steps)))
                safe_points.append({"vcc": round(vcc, 3), "vbb": round(vbb, 3)})
            from dataclasses import replace

            return replace(
                base_plan,
                ic_limit_a=round(ic_limit, 6),
                power_limit_w=round(power_limit, 6),
                static_points=safe_points,
            )

        def _ensure_ai_plan(self, mode):
            from ai.conversation import apply_intent_to_plan, interpret_user_message

            request_text = self.ai_panel.request_text()
            if self._ai_plan is None or self._ai_plan.mode != mode:
                intent, _, _, _ = interpret_user_message(
                    request_text,
                    self._ai_state,
                    default_mode=mode,
                )
                self._ai_plan = apply_intent_to_plan(intent, self._ai_state)
                self._ai_state.current_plan = self._ai_plan
            else:
                try:
                    self._ai_plan = self._plan_from_editor(self._ai_plan)
                    self._ai_state.current_plan = self._ai_plan
                except ValueError:
                    pass
            return self._ai_plan

        def _run_ai_plan(self, mode, allow_hardware=False):
            from ai.tools import execute_plan
            from pathlib import Path

            plan = self._ensure_ai_plan(mode)
            return execute_plan(
                plan,
                mode=mode,
                output_dir=Path("./analysis_out/ai_gui"),
                allow_hardware=allow_hardware,
            )

        def _on_ai_run_simulation_clicked(self):
            self._apply_ai_settings()
            self._log("[AI] 开始按计划执行仿真测试...")
            worker = self._run_worker(self._run_ai_plan, "simulation", False)
            if worker:
                worker.result_ready.connect(self._on_ai_execution_ready)

        def _on_ai_run_hardware_clicked(self):
            if QMessageBox is None:
                self._log("[AI] 当前环境不支持确认弹窗，已取消硬件执行。")
                return
            reply = QMessageBox.warning(
                self,
                "确认硬件执行",
                "即将按 AI 计划执行真实硬件输出。请确认器件、夹具、引脚和量程已检查。",
                QMessageBox.Cancel | QMessageBox.Ok,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                self._log("[AI] 已取消硬件执行。")
                return
            self._apply_ai_settings()
            self._log("[AI] 开始按计划执行硬件测试...")
            worker = self._run_worker(self._run_ai_plan, "hardware", True)
            if worker:
                worker.result_ready.connect(self._on_ai_execution_ready)

        def _on_ai_execution_ready(self, result):
            if result.get("skipped"):
                self._log(f"[AI] 跳过执行：{result.get('reason')}")
                self.ai_panel.set_plan_text(f"跳过执行：{result.get('reason')}")
                return
            measurements = result.get("measurements", [])
            self._ai_state.current_execution = result
            self._log(f"[AI] 执行完成，共 {len(measurements)} 个测量点。")
            if result.get("execution_json"):
                self._log(f"[AI] 结果已保存：{result['execution_json']}")
            self._plot_ai_measurements(measurements)
            if measurements:
                self._update_live_values_from_mapping(measurements[-1])
            self._log("[AI] 正在生成结果总结...")
            worker = self._run_worker(self._summarize_ai_execution, result)
            if worker:
                worker.result_ready.connect(self._on_ai_execution_summary_ready)

        def _summarize_ai_execution(self, result):
            from ai.assistant import summarize_execution_with_ai

            summary, used_ai, provider, usage = summarize_execution_with_ai(result)
            self._ai_state.current_summary = summary
            self._ai_state.add("assistant", summary)
            return {
                "summary": summary,
                "used_ai": used_ai,
                "provider": provider,
                "usage": usage,
            }

        def _on_ai_execution_summary_ready(self, payload):
            provider_line = f"Provider: {payload['provider']}"
            self.ai_panel.set_plan_text(payload["summary"] + "\n\n" + provider_line)
            self._log("[AI] 结果总结已生成。")

        def _update_live_values_from_mapping(self, point):
            self.live_value_panel.value_labels["vbe"].setText(f"{point['Vbe']:.3f} V")
            self.live_value_panel.value_labels["ib"].setText(f"{point['Ib']*1e6:.1f} μA")
            self.live_value_panel.value_labels["vce"].setText(f"{point['Vce']:.3f} V")
            self.live_value_panel.value_labels["ic"].setText(f"{point['Ic']*1e3:.2f} mA")
            self.live_value_panel.value_labels["beta"].setText(f"{point['beta']:.1f}")
            self.live_value_panel.value_labels["region"].setText(str(point["region"]))

        def _plot_ai_measurements(self, measurements):
            if not measurements:
                return
            self.live_plot.axes.clear()
            self.live_plot.axes.set_facecolor("#FFFFFF")
            self.live_plot.axes.grid(True, color="#E5E5EA", linewidth=1)
            self.live_plot.axes.spines['top'].set_visible(False)
            self.live_plot.axes.spines['right'].set_visible(False)
            self.live_plot.axes.spines['left'].set_color("#E5E5EA")
            self.live_plot.axes.spines['bottom'].set_color("#E5E5EA")
            self.live_plot.axes.set_title("AI 静态点测试")
            self.live_plot.axes.set_xlabel("Vbb (V)")
            self.live_plot.axes.set_ylabel("Beta")
            x_vals = [point["Vbb"] for point in measurements]
            y_vals = [point["beta"] for point in measurements]
            self.live_plot.axes.plot(x_vals, y_vals, "-o", color="#0071E3", markersize=5)
            self.live_plot.draw()

        def _on_connect_clicked(self):
            self._log("正在连接设备...")
            mode = self._get_mode()
            
            def ping():
                from app.services import build_driver
                driver = build_driver(mode)
                try:
                    sn = driver.connect()
                    return sn
                finally:
                    driver.close()
            
            worker = self._run_worker(ping)
            if worker:
                worker.result_ready.connect(self._on_connect_success)

        def _on_connect_success(self, serial):
            self._log(f"连接成功！设备序列号: {serial}")
            self.connection_panel.status_label.setText("已连接")
            self.connection_panel.status_label.setStyleSheet("color: #248A3D; font-weight: 600;")
            self.statusBar().showMessage(f"当前状态：已连接 ({serial})")

        def _on_disconnect_clicked(self):
            self.connection_panel.status_label.setText("未连接")
            self.connection_panel.status_label.setStyleSheet("color: #FF3B30; font-weight: 600;")
            self.statusBar().showMessage("当前状态：未连接设备")
            self._log("已断开连接。")

        def _on_detect_type_clicked(self):
            self._log("开始识别管型...")
            worker = self._run_worker(self.orchestrator.detect, self._get_mode())
            if worker:
                worker.result_ready.connect(lambda res: self._log(f"管型识别结果: {res[1]}"))

        def _on_measure_static_clicked(self):
            self._log("开始静态测试 (Vcc=3.0V, Vbb=2.0V)...")
            worker = self._run_worker(self.orchestrator.npn_static, self._get_mode(), 3.0, 2.0)
            if worker:
                worker.result_ready.connect(self._on_measure_static_success)

        def _on_measure_static_success(self, point):
            self._log("静态测试完成！")
            self._log(f"Vbe={point.Vbe:.4f}V, Vce={point.Vce:.4f}V")
            self._log(f"Ib={point.Ib*1e6:.1f}uA, Ic={point.Ic*1e3:.2f}mA")
            self._log(f"Beta={point.beta:.1f}, 状态={point.region}")
            
            # Update Live Value Panel
            self.live_value_panel.value_labels["vbe"].setText(f"{point.Vbe:.3f} V")
            self.live_value_panel.value_labels["ib"].setText(f"{point.Ib*1e6:.1f} μA")
            self.live_value_panel.value_labels["vce"].setText(f"{point.Vce:.3f} V")
            self.live_value_panel.value_labels["ic"].setText(f"{point.Ic*1e3:.2f} mA")
            self.live_value_panel.value_labels["beta"].setText(f"{point.beta:.1f}")
            self.live_value_panel.value_labels["region"].setText(f"{point.region}")

            # Plot a point
            self.live_plot.axes.clear()
            self.live_plot.axes.set_facecolor("#FFFFFF")
            self.live_plot.axes.grid(True, color="#E5E5EA", linewidth=1)
            self.live_plot.axes.spines['top'].set_visible(False)
            self.live_plot.axes.spines['right'].set_visible(False)
            self.live_plot.axes.spines['left'].set_color("#E5E5EA")
            self.live_plot.axes.spines['bottom'].set_color("#E5E5EA")
            self.live_plot.axes.set_title(self.live_plot.model.title)
            self.live_plot.axes.set_xlabel(self.live_plot.model.x_label)
            self.live_plot.axes.set_ylabel(self.live_plot.model.y_label)
            self.live_plot.axes.tick_params(colors="#86868B")
            self.live_plot.axes.title.set_color("#1D1D1F")
            self.live_plot.axes.title.set_fontweight("bold")
            self.live_plot.axes.xaxis.label.set_color("#86868B")
            self.live_plot.axes.yaxis.label.set_color("#86868B")

            self.live_plot.axes.plot([point.Vce], [point.Ic], 'o', color="#0071E3", markersize=8)
            self.live_plot.axes.text(point.Vce, point.Ic, f" Beta={point.beta:.1f}", color="#34C759", verticalalignment="bottom")
            self.live_plot.draw()

        def _on_scan_curves_clicked(self):
            scan_mode = self.hw_config_panel.scan_mode_combo.currentData()
            scan_text = self.hw_config_panel.scan_mode_combo.currentText()
            self._log(f"开始扫描特性曲线 (使用模式: {scan_text})...")
            worker = self._run_worker(self.orchestrator.scan_curves, self._get_mode(), scan_mode)
            if worker:
                worker.result_ready.connect(self._on_scan_curves_success)

        def _on_scan_curves_success(self, points):
            self._log(f"曲线扫描完成，共采集 {len(points)} 个静态点！")
            
            # Plot the points
            self.live_plot.axes.clear()
            self.live_plot.axes.set_facecolor("#FFFFFF")
            self.live_plot.axes.grid(True, color="#E5E5EA", linewidth=1)
            self.live_plot.axes.spines['top'].set_visible(False)
            self.live_plot.axes.spines['right'].set_visible(False)
            self.live_plot.axes.spines['left'].set_color("#E5E5EA")
            self.live_plot.axes.spines['bottom'].set_color("#E5E5EA")
            self.live_plot.axes.set_title(self.live_plot.model.title)
            self.live_plot.axes.set_xlabel(self.live_plot.model.x_label)
            self.live_plot.axes.set_ylabel(self.live_plot.model.y_label)
            
            # Group points by Ib
            from measurement.curves import group_points_by_ib
            curves = group_points_by_ib(points)
            
            colors = ["#0071E3", "#34C759", "#FF9500", "#FF3B30", "#AF52DE", "#5856D6"]
            
            for i, (ib, pts) in enumerate(curves.items()):
                vce_vals = [p.Vce for p in pts]
                ic_vals = [p.Ic for p in pts]
                color = colors[i % len(colors)]
                self.live_plot.axes.plot(vce_vals, ic_vals, '-o', color=color, markersize=4, label=f"Ib={ib*1e6:.1f}uA")
                
            self.live_plot.axes.legend(loc="upper left", fontsize=8)
            self.live_plot.draw()

        def _on_full_suite_clicked(self):
            from pathlib import Path
            self._log("开始完整测试流程...")
            worker = self._run_worker(
                self.orchestrator.full_run, 
                self._get_mode(), 
                "GUI-DUT", 
                Path("./analysis_out")
            )
            if worker:
                worker.result_ready.connect(lambda r: self._log(f"完整测试成功！报告已写入 analysis_out，测得 Beta 中位数: {r.beta_median:.1f}"))

        def panel_names(self):
            return [
                self.model.connection.name,
                self.model.hardware_config.name,
                self.model.actions.name,
                self.model.ai.name,
                self.model.plan_table.name,
                self.model.live_values.name,
                self.model.log.name,
            ]

        def plot_title(self) -> str:
            return self.model.plot.title

else:

    class MainWindow:
        def __init__(self):
            self.model = build_default_window_model()
            self.uses_qt = False
            self.connection_panel = ConnectionPanel()
            self.hw_config_panel = HwConfigPanel()
            self.action_panel = ActionPanel()
            self.ai_panel = AIPanel()
            self.plan_table_panel = PlanTablePanel()
            self.live_value_panel = LiveValuePanel()
            self.log_panel = LogPanel()
            self.live_plot = LivePlotWidget()
            self._title = 'BJT 测试台'

        def windowTitle(self) -> str:
            return self._title

        def panel_names(self):
            return [
                self.model.connection.name,
                self.model.hardware_config.name,
                self.model.actions.name,
                self.model.ai.name,
                self.model.plan_table.name,
                self.model.live_values.name,
                self.model.log.name,
            ]

        def plot_title(self) -> str:
            return self.model.plot.title
