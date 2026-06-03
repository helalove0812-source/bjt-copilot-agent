from __future__ import annotations

from gui.models import PanelModel

try:
    from PySide6.QtWidgets import (
        QComboBox,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
    )
except ImportError:
    QComboBox = QFrame = QGridLayout = QGroupBox = QHBoxLayout = QLabel = QLineEdit = QPlainTextEdit = QPushButton = QSizePolicy = QVBoxLayout = None


def build_ai_panel_model() -> PanelModel:
    return PanelModel(
        name="AI 助手",
        fields=["ai_mode", "provider", "model", "api_key", "request", "plan_preview"],
        buttons=["apply_settings", "generate_plan", "run_simulation", "run_hardware"],
    )


if QGroupBox is not None:

    class AIPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__("", parent)
            self.setObjectName("AIChatPanel")
            self.model = build_ai_panel_model()
            self.header_label = QLabel("BJT-AI")
            self.header_label.setObjectName("AIChatTitle")
            self.chat_label = QLabel("测试对话")
            self.chat_label.setObjectName("AIChatPill")
            self.clear_button = QPushButton("清空")
            self.clear_button.setProperty("ghost", "true")

            self.ai_mode_combo = QComboBox()
            self.ai_mode_combo.addItem("本地", "local")
            self.ai_mode_combo.addItem("智能", "auto")
            self.ai_mode_combo.addItem("完整", "cloud")
            self.provider_combo = QComboBox()
            self.provider_combo.addItem("DeepSeek", "deepseek")
            self.provider_combo.addItem("OpenAI", "openai")
            self.model_input = QLineEdit("deepseek-v4-flash")
            self.api_key_input = QLineEdit()
            self.api_key_input.setPlaceholderText("API Key，仅当前进程使用")
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.apply_settings_button = QPushButton("应用配置")
            self.apply_settings_button.setProperty("ghost", "true")

            for widget in (
                self.ai_mode_combo,
                self.provider_combo,
                self.model_input,
                self.api_key_input,
                self.apply_settings_button,
            ):
                widget.setMinimumHeight(32)
            self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)

            self.request_edit = QPlainTextEdit()
            self.request_edit.setObjectName("AIChatInput")
            self.request_edit.setPlaceholderText("直接描述器件型号、测试目标、限制条件...")
            self.request_edit.setMinimumHeight(92)
            self.request_edit.setMaximumHeight(118)

            self.generate_button = QPushButton("Send")
            self.generate_button.setObjectName("AISendButton")
            self.generate_button.setProperty("primary", "true")
            self.run_sim_button = QPushButton("仿真执行")
            self.run_hw_button = QPushButton("硬件执行")
            self.plan_chip_button = QPushButton("生成计划")
            self.beta_chip_button = QPushButton("Beta")
            self.sat_chip_button = QPushButton("Vce(sat)")
            self.conservative_chip_button = QPushButton("保守一点")
            self.explain_chip_button = QPushButton("解释结果")
            for hidden_button in (
                self.run_sim_button,
                self.run_hw_button,
                self.plan_chip_button,
                self.beta_chip_button,
                self.sat_chip_button,
                self.conservative_chip_button,
                self.explain_chip_button,
            ):
                hidden_button.hide()
            for button in (
                self.generate_button,
            ):
                button.setMinimumHeight(36)

            self.plan_view = QPlainTextEdit()
            self.plan_view.setObjectName("AIChatTranscript")
            self.plan_view.setReadOnly(True)
            self.plan_view.setPlaceholderText(
                "BJT-AI\n\n从这里开始，读懂晶体管测试的一切。\n\n"
                "你可以让 AI 生成测试计划、修改扫描范围、解释结果，或把计划交给仿真/硬件执行。"
            )
            self.plan_view.setMinimumHeight(310)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

            self.plan_chip_button.clicked.connect(lambda: self.request_edit.setPlainText("测 S8050 重点看 beta"))
            self.beta_chip_button.clicked.connect(lambda: self.request_edit.setPlainText("测 S8050，重点看 beta"))
            self.sat_chip_button.clicked.connect(lambda: self.request_edit.setPlainText("测 S8050 的 Vce(sat)，给我饱和区扫描计划"))
            self.conservative_chip_button.clicked.connect(lambda: self.request_edit.setPlainText("保守一点，Ic 不超过 10mA"))
            self.explain_chip_button.clicked.connect(lambda: self.request_edit.setPlainText("解释刚才结果"))
            self.clear_button.clicked.connect(self._clear_chat)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(8)
            header_layout.addWidget(self.header_label)
            header_layout.addStretch(1)
            header_layout.addWidget(self.clear_button)
            layout.addLayout(header_layout)

            toolbar_layout = QHBoxLayout()
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(8)
            toolbar_layout.addWidget(self.chat_label)
            toolbar_layout.addStretch(1)
            toolbar_layout.addWidget(self.apply_settings_button)
            layout.addLayout(toolbar_layout)

            layout.addWidget(self.plan_view, stretch=1)

            input_card = QFrame(self)
            input_card.setObjectName("AIInputCard")
            card_layout = QVBoxLayout(input_card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(10)

            settings_layout = QGridLayout()
            settings_layout.setHorizontalSpacing(8)
            settings_layout.setVerticalSpacing(8)
            settings_layout.addWidget(self.ai_mode_combo, 0, 0)
            settings_layout.addWidget(self.provider_combo, 0, 1)
            settings_layout.addWidget(self.model_input, 1, 0, 1, 2)
            settings_layout.addWidget(self.api_key_input, 2, 0, 1, 2)
            settings_layout.setColumnStretch(0, 1)
            settings_layout.setColumnStretch(1, 1)
            card_layout.addLayout(settings_layout)
            card_layout.addWidget(self.request_edit)
            card_layout.addWidget(self.generate_button)
            layout.addWidget(input_card)

        def request_text(self) -> str:
            return self.request_edit.toPlainText().strip()

        def set_plan_text(self, text: str) -> None:
            self.plan_view.setPlainText(text)

        def ai_settings(self) -> dict[str, str]:
            return {
                "ai_mode": str(self.ai_mode_combo.currentData()),
                "provider": str(self.provider_combo.currentData()),
                "model": self.model_input.text().strip(),
                "api_key": self.api_key_input.text().strip(),
            }

        def _on_provider_changed(self) -> None:
            provider = str(self.provider_combo.currentData())
            if provider == "deepseek" and not self.model_input.text().strip().startswith("deepseek"):
                self.model_input.setText("deepseek-v4-flash")
            elif provider == "openai" and self.model_input.text().strip().startswith("deepseek"):
                self.model_input.setText("gpt-5")

        def clear_request(self) -> None:
            self.request_edit.clear()

        def _clear_chat(self) -> None:
            self.plan_view.clear()
            self.request_edit.clear()

else:

    class AIPanel:
        def __init__(self, parent=None):
            self.parent = parent
            self.model = build_ai_panel_model()
            self.request = "测 S8050 重点看 beta"
            self.plan_text = ""
            self.settings = {
                "ai_mode": "local",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "api_key": "",
            }

        def request_text(self) -> str:
            return self.request

        def set_plan_text(self, text: str) -> None:
            self.plan_text = text

        def ai_settings(self) -> dict[str, str]:
            return dict(self.settings)

        def clear_request(self) -> None:
            self.request = ""
