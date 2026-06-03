from __future__ import annotations


APP_STYLESHEET = """
QMainWindow {
    background: #ececee;
}

QWidget {
    color: #1d1d1f;
    font-family: "Helvetica Neue", "PingFang SC", Arial, sans-serif;
    font-size: 13px;
    letter-spacing: 0px;
}

QWidget#AppChrome {
    background: #f5f5f7;
}

QWidget#Sidebar,
QWidget#AIColumn {
    background: rgba(246, 246, 248, 0.72);
}

QWidget#Sidebar {
    border-right: 1px solid rgba(0, 0, 0, 0.08);
}

QLabel {
    color: #6e6e73;
}

QLabel#AppTitle {
    color: #1d1d1f;
    font-size: 28px;
    font-weight: 700;
}

QLabel#AppSubtitle {
    color: #6e6e73;
    font-size: 15px;
}

QLabel#StatusPill {
    background: #ffffff;
    border: none;
    border-radius: 999px;
    color: #007aff;
    font-weight: 600;
    padding: 7px 14px;
}

QGroupBox {
    background: #ffffff;
    border: none;
    border-radius: 12px;
    color: #1d1d1f;
    font-size: 12px;
    font-weight: 650;
    margin-top: 0px;
    padding: 34px 16px 16px 16px;
}

QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 16px;
    top: 0px;
    color: #9a9aa0;
    text-transform: uppercase;
}

QLabel#FormLabel {
    color: #6e6e73;
    font-size: 12px;
}

QLabel[role="panelTitle"] {
    color: #1d1d1f;
    font-size: 15px;
    font-weight: 640;
    padding: 0px;
}

QLabel#MetricValue,
QLabel#StatusValue,
QLabel[role="valueDisplay"] {
    color: #1d1d1f;
    font-family: Menlo, "PingFang SC", monospace;
    font-size: 24px;
    font-weight: 650;
}

QLabel#MetricName,
QLabel[role="valueCaption"] {
    color: #6e6e73;
    font-size: 12px;
}

QFrame#MetricCard {
    background: #ffffff;
    border: none;
    border-radius: 12px;
}

QLineEdit,
QComboBox,
QPlainTextEdit {
    background: #f2f2f7;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    color: #1d1d1f;
    min-height: 32px;
    padding: 7px 11px;
    selection-background-color: #007aff;
    selection-color: #ffffff;
}

QLineEdit:hover,
QComboBox:hover,
QPlainTextEdit:hover {
    background: #ffffff;
    border-color: rgba(0, 0, 0, 0.14);
}

QLineEdit:focus,
QComboBox:focus,
QPlainTextEdit:focus {
    background: #ffffff;
    border: 1px solid #007aff;
    padding: 7px 11px;
}

QPlainTextEdit {
    font-family: Menlo, "PingFang SC", monospace;
    font-size: 12px;
}

QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-radius: 8px;
    color: #1d1d1f;
    selection-background-color: #007aff;
    selection-color: #ffffff;
    outline: none;
}

QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 4px 8px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
}

QPushButton {
    background: rgba(120, 120, 128, 0.12);
    border: none;
    border-radius: 8px;
    color: #1d1d1f;
    font-weight: 590;
    min-height: 32px;
    padding: 8px 14px;
}

QPushButton:hover {
    background: rgba(120, 120, 128, 0.20);
}

QPushButton:pressed {
    background: rgba(120, 120, 128, 0.26);
}

QPushButton#PrimaryButton,
QPushButton[primary="true"] {
    background: #007aff;
    color: #ffffff;
}

QPushButton#PrimaryButton:hover,
QPushButton[primary="true"]:hover {
    background: #0a84ff;
}

QPushButton#DangerButton,
QPushButton[danger="true"] {
    background: #ff3b30;
    color: #ffffff;
}

QPushButton#DangerButton:hover,
QPushButton[danger="true"]:hover {
    background: #ff453a;
}

QPushButton[secondary="true"] {
    background: rgba(120, 120, 128, 0.12);
    color: #1d1d1f;
}

QPushButton[actionRow="true"],
QPushButton[modeOption="true"] {
    background: #ffffff;
    color: #1d1d1f;
    text-align: left;
    padding: 8px 14px;
}

QPushButton[actionRow="true"]:hover,
QPushButton[modeOption="true"]:hover {
    background: rgba(120, 120, 128, 0.12);
}

QPushButton[modeOption="true"][primary="true"] {
    background: #007aff;
    color: #ffffff;
    text-align: left;
}

QPushButton#EmergencyStopButton {
    margin-top: 6px;
    font-weight: 650;
}

QPushButton[ghost="true"] {
    background: transparent;
    color: #007aff;
    padding: 5px 8px;
}

QPushButton[ghost="true"]:hover {
    background: rgba(120, 120, 128, 0.12);
}

QTableWidget {
    background: #ffffff;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    color: #1d1d1f;
    gridline-color: rgba(0, 0, 0, 0.08);
    selection-background-color: rgba(0, 122, 255, 0.12);
    selection-color: #1d1d1f;
}

QHeaderView::section {
    background: #f2f2f7;
    border: none;
    border-right: 1px solid rgba(0, 0, 0, 0.08);
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
    color: #6e6e73;
    font-weight: 600;
    padding: 8px 12px;
}

QScrollArea {
    background: #f5f5f7;
}

QStatusBar {
    background: rgba(246, 246, 248, 0.72);
    border-top: 1px solid rgba(0, 0, 0, 0.08);
    color: #6e6e73;
}

QGroupBox#AIChatPanel {
    background: transparent;
    border: none;
    border-radius: 0px;
    margin-top: 0px;
    padding: 16px;
}

QGroupBox#AIChatPanel::title {
    height: 0px;
}

QLabel#AIChatTitle {
    color: #1d1d1f;
    font-size: 15px;
    font-weight: 700;
}

QLabel#AIChatPill {
    background: #ffffff;
    border: none;
    border-radius: 8px;
    color: #1d1d1f;
    font-size: 13px;
    font-weight: 590;
    padding: 8px 14px;
}

QPlainTextEdit#AIChatTranscript {
    background: transparent;
    border: none;
    border-radius: 0px;
    color: #6e6e73;
    font-family: "Helvetica Neue", "PingFang SC", Arial, sans-serif;
    font-size: 13px;
    padding: 14px 4px;
}

QPlainTextEdit#AIChatTranscript:focus {
    background: transparent;
    border: none;
    padding: 14px 4px;
}

QFrame#AIInputCard {
    background: #ffffff;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 12px;
}

QPlainTextEdit#AIChatInput {
    background: #ffffff;
    border: none;
    color: #1d1d1f;
    font-family: "Helvetica Neue", "PingFang SC", Arial, sans-serif;
    font-size: 13px;
    padding: 6px 4px;
}

QPlainTextEdit#AIChatInput:focus {
    background: #ffffff;
    border: none;
    padding: 6px 4px;
}

QPushButton#AISendButton {
    background: #007aff;
    border-radius: 8px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 640;
    min-height: 40px;
}

QPushButton#AISendButton:hover {
    background: #0a84ff;
}

QGroupBox#AIChatPanel QComboBox,
QGroupBox#AIChatPanel QLineEdit {
    background: #f2f2f7;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    min-height: 30px;
    padding: 7px 11px;
}
"""
