"""
深色/浅色主题管理
"""

LIGHT_THEME = """
QMainWindow, QDialog {
    background-color: #f5f5f5;
    color: #333333;
}
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    color: #333333;
}
QTableView {
    background-color: white;
    alternate-background-color: #f9f9f9;
    gridline-color: #e0e0e0;
    color: #333333;
}
QTableView::item {
    color: #333333;
}
QTableView::item:selected {
    background-color: #0078d4;
    color: white;
}
QHeaderView::section {
    background-color: #e8e8e8;
    color: #333333;
    padding: 6px;
    border: 1px solid #d0d0d0;
    font-weight: bold;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 10px;
    color: #333333;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #333333;
}
QLabel {
    color: #333333;
}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
    background-color: white;
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    padding: 4px;
    min-height: 20px;
    color: #333333;
}
QComboBox {
    background-color: white;
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    padding: 4px 24px 4px 8px;
    min-height: 20px;
    min-width: 60px;
    color: #333333;
}
QComboBox QAbstractItemView {
    background-color: white;
    color: #333333;
    selection-background-color: #0078d4;
    selection-color: white;
    border: 1px solid #c0c0c0;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0078d4;
}
QPushButton {
    background-color: #e8e8e8;
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 4px 8px;
    color: #333333;
}
QPushButton:hover {
    background-color: #d8d8d8;
}
QPushButton:pressed {
    background-color: #c8c8c8;
}
QTabWidget::pane {
    border: 1px solid #d0d0d0;
}
QTabBar::tab {
    background-color: #e8e8e8;
    border: 1px solid #d0d0d0;
    padding: 8px 16px;
}
QTabBar::tab:selected {
    background-color: white;
    border-bottom-color: white;
}
QMenuBar {
    background-color: #f0f0f0;
}
QMenuBar::item:selected {
    background-color: #0078d4;
    color: white;
}
QMenu {
    background-color: white;
    border: 1px solid #d0d0d0;
}
QMenu::item:selected {
    background-color: #0078d4;
    color: white;
}
QScrollBar:vertical {
    background-color: #f0f0f0;
    width: 12px;
}
QScrollBar::handle:vertical {
    background-color: #c0c0c0;
    border-radius: 6px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #a0a0a0;
}
QScrollBar:horizontal {
    background-color: #f0f0f0;
    height: 12px;
}
QScrollBar::handle:horizontal {
    background-color: #c0c0c0;
    border-radius: 6px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #a0a0a0;
}
QListWidget {
    background-color: white;
    border: 1px solid #c0c0c0;
}
QListWidget::item:selected {
    background-color: #0078d4;
    color: white;
}
QProgressBar {
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #0078d4;
}
"""

DARK_THEME = """
QMainWindow, QDialog {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QWidget {
    color: #e0e0e0;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}
QTableView {
    background-color: #252526;
    alternate-background-color: #2d2d30;
    gridline-color: #3e3e42;
    color: #e0e0e0;
    selection-background-color: #264f78;
}
QTableView::item {
    color: #e0e0e0;
}
QTableView::item:selected {
    background-color: #264f78;
    color: white;
}
QTableView QTableCornerButton::section {
    background-color: #333337;
    border: 1px solid #3e3e42;
}
QHeaderView {
    background-color: #333337;
}
QHeaderView::section {
    background-color: #333337;
    color: #e0e0e0;
    padding: 6px;
    border: 1px solid #3e3e42;
    font-weight: bold;
}
QHeaderView::section:horizontal {
    background-color: #333337;
    color: #e0e0e0;
}
QHeaderView::section:vertical {
    background-color: #333337;
    color: #e0e0e0;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 10px;
    color: #e0e0e0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
    background-color: #3c3c3c;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    padding: 4px;
    color: #e0e0e0;
    min-height: 20px;
}
QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    padding: 4px 24px 4px 8px;
    color: #e0e0e0;
    min-height: 20px;
    min-width: 60px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0078d4;
}
QComboBox QAbstractItemView {
    background-color: #3c3c3c;
    color: #e0e0e0;
    selection-background-color: #264f78;
    border: 1px solid #3e3e42;
}
QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    padding: 4px 8px;
    color: #e0e0e0;
}
QPushButton:hover {
    background-color: #4a4a4d;
}
QPushButton:pressed {
    background-color: #5a5a5d;
}
QPushButton:disabled {
    background-color: #2d2d30;
    color: #6e6e6e;
}
QTabWidget::pane {
    border: 1px solid #3e3e42;
    background-color: #252526;
}
QTabBar::tab {
    background-color: #2d2d30;
    border: 1px solid #3e3e42;
    padding: 8px 16px;
    color: #e0e0e0;
}
QTabBar::tab:selected {
    background-color: #1e1e1e;
    border-bottom-color: #1e1e1e;
}
QTabBar::tab:hover {
    background-color: #3e3e42;
}
QMenuBar {
    background-color: #2d2d30;
    color: #e0e0e0;
}
QMenuBar::item {
    background-color: transparent;
    color: #e0e0e0;
}
QMenuBar::item:selected {
    background-color: #264f78;
    color: white;
}
QMenu {
    background-color: #2d2d30;
    border: 1px solid #3e3e42;
    color: #e0e0e0;
}
QMenu::item {
    padding: 6px 20px;
}
QMenu::item:selected {
    background-color: #264f78;
    color: white;
}
QMenu::separator {
    height: 1px;
    background-color: #3e3e42;
}
QScrollBar:vertical {
    background-color: #2d2d30;
    width: 12px;
}
QScrollBar::handle:vertical {
    background-color: #5a5a5d;
    border-radius: 6px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #7a7a7d;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #2d2d30;
    height: 12px;
}
QScrollBar::handle:horizontal {
    background-color: #5a5a5d;
    border-radius: 6px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #7a7a7d;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QSplitter::handle {
    background-color: #3e3e42;
}
QStatusBar {
    background-color: #007acc;
    color: white;
}
QToolTip {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #3e3e42;
    padding: 4px;
}
QListWidget {
    background-color: #252526;
    border: 1px solid #3e3e42;
    color: #e0e0e0;
}
QListWidget::item {
    color: #e0e0e0;
}
QListWidget::item:selected {
    background-color: #264f78;
    color: white;
}
QProgressBar {
    border: 1px solid #3e3e42;
    border-radius: 3px;
    text-align: center;
    background-color: #2d2d30;
    color: #e0e0e0;
}
QProgressBar::chunk {
    background-color: #0078d4;
}
QCheckBox {
    color: #e0e0e0;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QRadioButton {
    color: #e0e0e0;
}
QInputDialog {
    background-color: #1e1e1e;
}
QMessageBox {
    background-color: #1e1e1e;
}
QMessageBox QLabel {
    color: #e0e0e0;
}
"""

def get_theme(dark_mode=False):
    """获取主题样式表"""
    return DARK_THEME if dark_mode else LIGHT_THEME
