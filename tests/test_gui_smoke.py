import os
import importlib.util

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _ensure_qt_app():
    if not _has_module("PySide6"):
        return None
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_main_window_builds_with_expected_sections():
    _ensure_qt_app()
    from gui.main_window import MainWindow

    window = MainWindow()

    assert window.windowTitle() in ("晶体管测试系统", "BJT 测试台")
    assert window.panel_names() == [
        "连接",
        "硬件配置",
        "操作",
        "AI 助手",
        "测试点",
        "实时数值",
        "日志",
    ]
    assert window.plot_title() in ("输出特性预览", "Ic-Vce 输出特性")


def test_window_model_lists_key_controls():
    from gui.models import build_default_window_model

    model = build_default_window_model()

    assert model.connection.fields == ["mode", "device", "status"]
    assert "detect_type" in model.actions.buttons
    assert "full_suite" in model.actions.buttons
    assert model.ai.name == "AI 助手"
    assert "ai_mode" in model.ai.fields
    assert "provider" in model.ai.fields
    assert "model" in model.ai.fields
    assert "api_key" in model.ai.fields
    assert "apply_settings" in model.ai.buttons
    assert "generate_plan" in model.ai.buttons
    assert model.plan_table.name == "测试点"
    assert "static_points" in model.plan_table.fields
    assert "apply_plan" in model.plan_table.buttons
    assert "add_point" in model.plan_table.buttons
    assert "remove_point" in model.plan_table.buttons
    assert "beta" in model.live_values.metrics
    assert model.log.read_only is True


def test_main_window_uses_qt_widgets_when_qt_stack_installed():
    if not (_has_module("PySide6") and _has_module("pytestqt")):
        return

    _ensure_qt_app()
    from gui.main_window import MainWindow

    window = MainWindow()

    assert window.uses_qt is True
