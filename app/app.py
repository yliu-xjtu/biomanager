import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import logging
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtGui import QIcon
from ui.main_window import MainWindow
from db.database import Database
from startup_dialog import load_last_db_path, save_last_db_path, StartupDialog


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的环境"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(PROJECT_ROOT, relative_path)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("启动本地 PDF 文献管理器")
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 设置应用图标（兼容打包后环境）
    icon_path = get_resource_path("resources/icons/app.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    db = None
    window = None
    is_new_db = False
    
    while True:
        db_path = load_last_db_path()
        
        if db_path and os.path.exists(db_path):
            try:
                db = Database(db_path)
                logger.info(f"自动打开数据库: {db_path}")
                break
            except Exception as e:
                logger.warning(f"无法打开上次使用的数据库: {e}")
                db_path = None
        
        dialog = StartupDialog()
        if dialog.exec() == QDialog.Accepted and dialog.result_path:
            try:
                db_path = dialog.result_path
                db = Database(db_path)
                logger.info(f"数据库已打开: {db_path}")
                save_last_db_path(db_path)
                is_new_db = dialog.is_new_db
                break
            except Exception as e:
                logger.error(f"无法打开数据库: {e}")
                QMessageBox.critical(None, "错误", f"无法打开数据库:\n{e}")
        else:
            QMessageBox.information(None, "提示", "未选择数据库，程序将退出")
            return
    
    window = MainWindow(db, db_path)
    window.show()
    
    # 如果是新创建的数据库，触发扫描
    print(f"[DEBUG] main: is_new_db={is_new_db}")
    if is_new_db:
        print("[DEBUG] main: triggering scan")
        window._refresh_database()
    else:
        print("[DEBUG] main: not a new db, skipping scan")
    
    logger.info("程序启动成功")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
