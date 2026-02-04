import sys
import os
import json

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog
from PySide6.QtCore import Qt

CONFIG_FILE = 'app_config.json'
DEFAULT_DB_NAME = 'literature.db'

def load_last_db_path():
    """加载上次打开的数据库路径"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('last_db_path')
    except Exception:
        pass
    return None

def save_last_db_path(db_path):
    """保存上次打开的数据库路径"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_db_path': db_path}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save config: {e}")

class StartupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("欢迎使用 PDF 文献管理器")
        self.setFixedSize(400, 200)
        self.result_path = None
        self.is_new_db = False  # True=新建数据库, False=打开已有
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        title = QLabel("请选择操作：")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_open_db = QPushButton("📂 打开已有的数据库文件")
        self.btn_open_db.setMinimumHeight(40)
        self.btn_open_db.clicked.connect(self._open_existing_db)
        btn_layout.addWidget(self.btn_open_db)
        
        self.btn_new_db = QPushButton("📁 选择文件夹（自动创建数据库）")
        self.btn_new_db.setMinimumHeight(40)
        self.btn_new_db.clicked.connect(self._create_new_db)
        btn_layout.addWidget(self.btn_new_db)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def _open_existing_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择数据库文件",
            os.path.expanduser('~'),
            "SQLite Database (*.db);;All Files (*)"
        )
        if path:
            self.result_path = path
            self.is_new_db = False
            self.accept()
    
    def _create_new_db(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择文献文件夹",
            os.path.expanduser('~')
        )
        if not directory:
            print("[DEBUG] startup_dialog: no directory selected")
            return
        
        db_path = os.path.join(directory, DEFAULT_DB_NAME)
        print(f"[DEBUG] startup_dialog: db_path={db_path}, exists={os.path.exists(db_path)}")
        
        if os.path.exists(db_path):
            reply = QMessageBox.question(
                self,
                "数据库已存在",
                f"该文件夹下已存在数据库文件：\n{DEFAULT_DB_NAME}\n\n请选择：",
                QMessageBox.Open | QMessageBox.Retry | QMessageBox.Cancel,
                QMessageBox.Retry
            )
            print(f"[DEBUG] startup_dialog: reply={reply}")
            
            if reply == QMessageBox.Cancel:
                print("[DEBUG] startup_dialog: user cancelled")
                return
            elif reply == QMessageBox.Open:
                self.result_path = db_path
                self.is_new_db = False
                print("[DEBUG] startup_dialog: user chose to open existing")
                self.accept()
            elif reply == QMessageBox.Retry:
                try:
                    os.remove(db_path)
                    self.result_path = db_path
                    self.is_new_db = True
                    print("[DEBUG] startup_dialog: user chose to retry, is_new_db=True")
                    self.accept()
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"无法删除现有数据库:\n{e}")
                    return
        else:
            self.result_path = db_path
            self.is_new_db = True
            print("[DEBUG] startup_dialog: new db, is_new_db=True")
            self.accept()
