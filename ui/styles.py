MAIN_STYLE = """
QMainWindow { background: #F0F2F5; }
QWidget#sidebar { background: #001529; min-width: 200px; max-width: 200px; }
QLabel#appTitle { color: #FFFFFF; font-size: 15px; font-weight: bold; }
QLabel#appSubtitle { color: #8FA8C0; font-size: 11px; }
QPushButton#navButton {
    background: transparent; color: #A8C4D8; border: none;
    text-align: left; padding: 12px 20px; font-size: 13px;
}
QPushButton#navButton:hover { background: #112A45; color: #FFFFFF; }
QPushButton#navButton[active="true"] {
    background: #1677FF; color: #FFFFFF; font-weight: bold;
}
QWidget#contentArea { background: #F0F2F5; }
QLabel#pageTitle { font-size: 18px; font-weight: bold; color: #262626; }
QFrame#card {
    background: #FFFFFF; border-radius: 8px; border: 1px solid #E8E8E8;
}
QPushButton#primaryButton {
    background: #1677FF; color: white; border: none; border-radius: 6px;
    padding: 8px 20px; font-size: 13px; font-weight: bold; min-height: 32px;
}
QPushButton#primaryButton:hover { background: #0958D9; }
QPushButton#primaryButton:disabled { background: #BFBFBF; }
QPushButton#defaultButton {
    background: #FFFFFF; color: #262626; border: 1px solid #D9D9D9;
    border-radius: 6px; padding: 8px 20px; font-size: 13px; min-height: 32px;
}
QPushButton#defaultButton:hover { border-color: #1677FF; color: #1677FF; }
QPushButton#dangerButton {
    background: #FF4D4F; color: white; border: none; border-radius: 6px;
    padding: 8px 20px; font-size: 13px; min-height: 32px;
}
QPushButton#successButton {
    background: #52C41A; color: white; border: none; border-radius: 6px;
    padding: 8px 20px; font-size: 13px; font-weight: bold; min-height: 32px;
}
QPushButton#successButton:hover { background: #389E0D; }
QPushButton#successButton:disabled { background: #BFBFBF; }
QLabel#previewLabel {
    background: #FAFAFA; border: 2px dashed #D9D9D9; border-radius: 6px;
    color: #8C8C8C; font-size: 13px;
}
QListWidget {
    border: 1px solid #E8E8E8; border-radius: 6px;
    background: #FFFFFF; font-size: 13px;
}
QListWidget::item { padding: 6px 8px; }
QListWidget::item:selected { background: #E6F4FF; color: #262626; }
QPlainTextEdit#ocrLog {
    background: #1E1E1E; color: #D4D4D4;
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px; border: 1px solid #333; border-radius: 6px;
}
QLineEdit, QComboBox, QSpinBox {
    border: 1px solid #D9D9D9; border-radius: 6px;
    padding: 6px 10px; font-size: 13px; background: #FFFFFF; min-height: 28px;
}
QLineEdit:focus, QComboBox:focus { border-color: #1677FF; }
QTabWidget::pane { border: 1px solid #E8E8E8; border-radius: 6px; background: #FFF; }
QTabBar::tab {
    padding: 8px 16px; font-size: 13px;
    border: 1px solid #E8E8E8; border-bottom: none;
    background: #FAFAFA; margin-right: 2px;
}
QTabBar::tab:selected { background: #FFFFFF; color: #1677FF; font-weight: bold; }
QStatusBar {
    background: #FFFFFF; border-top: 1px solid #E8E8E8;
    font-size: 12px; color: #595959;
}
QDialog { background: #FFFFFF; }
QLabel#viewerImage { background: #1A1A1A; }
QTableWidget {
    background: #FFFFFF; border: 1px solid #E8E8E8; border-radius: 6px;
    gridline-color: #F0F0F0; font-size: 13px;
}
QTableWidget::item:selected { background: #E6F4FF; color: #262626; }
QHeaderView::section {
    background: #FAFAFA; border: none;
    border-bottom: 1px solid #E8E8E8; border-right: 1px solid #E8E8E8;
    padding: 8px 10px; font-weight: bold; color: #595959;
}
"""
