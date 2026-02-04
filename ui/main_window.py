from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                QTableView, QPushButton, QLabel, QLineEdit, 
                                QFileDialog, QProgressBar, QMessageBox, QMenuBar,
                                QStatusBar, QSplitter, QApplication, QInputDialog, QDialog, QGroupBox, QFormLayout, QComboBox, QHeaderView, QTableWidget, QTableWidgetItem, QTabWidget, QStackedWidget, QFrame, QListWidget, QListWidgetItem, QProgressDialog, QMenu, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QAction, QKeySequence, QShortcut, QIcon
from ui.table_model import PaperTableModel
from ui.patent_table_model import PatentTableModel
from ui.software_table_model import SoftwareTableModel
from ui.detail_panel import DetailPanel
from ui.patent_detail_panel import PatentDetailPanel
from ui.software_detail_panel import SoftwareDetailPanel
import os
import sqlite3
import subprocess
import logging
import json
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 设置中文字体
import matplotlib.font_manager as fm

def set_chinese_font():
    """尝试设置中文字体"""
    font_paths = [
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/NotoSansCJK-Regular.ttc',
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            font_prop = fm.FontProperties(fname=font_path)
            plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
            plt.rcParams['axes.unicode_minus'] = False
            return font_prop
    
    return None

_chinese_font = set_chinese_font()

logger = logging.getLogger(__name__)

class ScanThread(QThread):
    finished = Signal(list)
    progress = Signal(int)
    status = Signal(str)
    
    def __init__(self, db, root_dir):
        super().__init__()
        self.db = db
        self.root_dir = root_dir
        from core.scanner import scan_directory, get_file_info
        self.scan = scan_directory
        self.get_info = get_file_info
        from core.extractor import extract_metadata_from_pdf, needs_ocr, extract_certificate_info
        self.extract_pdf = extract_metadata_from_pdf
        self.extract_cert = extract_certificate_info
        self.needs_ocr = needs_ocr
        from core.resolver import resolve_doi
        self.resolve = resolve_doi
        from core.extractor import generate_bibtex_key
        self.gen_key = generate_bibtex_key
    
    def _check_pdf_has_paper(self, rel_path):
        """检查PDF文件是否有关联的论文"""
        try:
            conn = self.db.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT COUNT(*) as cnt FROM paper_files pf
                JOIN pdf_files f ON pf.pdf_file_id = f.id
                WHERE f.path = ?
            """, (rel_path,))
            result = cursor.fetchone()
            count = result['cnt'] if result else 0
            conn.close()
            return count > 0
        except Exception as e:
            logger.error(f"Error checking PDF-paper link: {e}")
            return True
    
    def _check_file_has_patent(self, rel_path):
        """检查文件是否已关联专利"""
        try:
            conn = self.db.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM patents WHERE file_path = ?", (rel_path,))
            result = cursor.fetchone()
            count = result['cnt'] if result else 0
            conn.close()
            return count > 0
        except Exception as e:
            logger.error(f"Error checking patent link: {e}")
            return True
    
    def _check_file_has_software(self, rel_path):
        """检查文件是否已关联软著"""
        try:
            conn = self.db.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM softwares WHERE file_path = ?", (rel_path,))
            result = cursor.fetchone()
            count = result['cnt'] if result else 0
            conn.close()
            return count > 0
        except Exception as e:
            logger.error(f"Error checking software link: {e}")
            return True
    
    def run(self):
        try:
            files = self.scan(self.root_dir)
            total = len(files)
            updated = []
            
            for i, path in enumerate(files):
                self.status.emit(f"扫描 {i+1}/{total}: {os.path.basename(path)}")
                self.progress.emit(int((i+1)/total*100))
                
                rel_path = os.path.relpath(path, self.root_dir)
                info = self.get_info(path)
                filename = os.path.basename(path).lower()
                is_image = path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff'))
                is_certificate_pdf = any(kw in filename for kw in ['专利', '软著', '证书', 'certificate', 'patent'])
                
                if is_image or is_certificate_pdf:
                    self._process_certificate(path, rel_path, info, updated)
                else:
                    self._process_pdf(path, rel_path, info, updated)
            
            logger.info(f"[DEBUG] Scan finished: {len(updated)} items updated")
            self.status.emit(f"扫描完成，新增/更新 {len(updated)} 项")
            self.finished.emit(updated)
        
        except Exception as e:
            self.status.emit(f"扫描错误: {e}")
            self.finished.emit([])
    
    def _process_certificate(self, path, rel_path, info, updated):
        """处理证书图片文件"""
        try:
            has_patent = self._check_file_has_patent(rel_path)
            has_software = self._check_file_has_software(rel_path)
            
            if has_patent or has_software:
                logger.info(f"Skip already linked: {os.path.basename(path)}")
                return
            
            logger.info(f"[DEBUG] Extracting certificate info from {os.path.basename(path)}")
            result = self.extract_cert(path)
            
            if result.get('type') == 'patent':
                data = result['data']
                patent_id = self.db.upsert_patent(
                    title=data.get('title') or os.path.basename(path),
                    patent_number=data.get('patent_number') or '',
                    grant_number=data.get('grant_number') or '',
                    inventors=data.get('inventors') or '',
                    patentee=data.get('patentee') or '',
                    application_date=data.get('application_date') or '',
                    grant_date=data.get('grant_date') or '',
                    patent_type='发明',
                    file_path=rel_path
                )
                updated.append({'path': rel_path, 'type': 'patent', 'id': patent_id})
                logger.info(f"[DEBUG] Added patent: {rel_path}")
                
            elif result.get('type') == 'software':
                data = result['data']
                software_id = self.db.upsert_software(
                    software_name=data.get('software_name') or '',
                    title=data.get('software_name') or os.path.basename(path),
                    version=data.get('version') or '',
                    registration_number=data.get('registration_number') or '',
                    copyright_holder=data.get('copyright_holder') or '',
                    development_date=data.get('development_date') or '',
                    file_path=rel_path
                )
                updated.append({'path': rel_path, 'type': 'software', 'id': software_id})
                logger.info(f"[DEBUG] Added software: {rel_path}")
            
            else:
                logger.info(f"[DEBUG] No certificate detected: {os.path.basename(path)}")
        
        except Exception as e:
            logger.error(f"[ERROR] Failed to process certificate {os.path.basename(path)}: {e}")
    
    def _process_pdf(self, path, rel_path, info, updated):
        """处理PDF文献文件"""
        try:
            existing = self.db.get_pdf_by_path(rel_path)
            
            needs_scan = True
            logger.info(f"[DEBUG] Scan {rel_path}: existing={existing is not None}")
            
            if existing:
                if existing.get('sha256') == info['sha256']:
                    has_paper = self._check_pdf_has_paper(rel_path)
                    logger.info(f"[DEBUG] PDF exists, sha256 matches, has_paper={has_paper}")
                    if has_paper:
                        needs_scan = False
                        logger.info(f"Skip unchanged: {os.path.basename(path)}")
                    else:
                        needs_scan = True
                        logger.info(f"PDF exists but no paper, will re-scan: {os.path.basename(path)}")
                elif existing.get('size') != info['size'] or existing.get('mtime') != info['mtime']:
                    needs_scan = True
                    logger.info(f"[DEBUG] PDF size/mtime changed, will re-scan")
            
            logger.info(f"[DEBUG] needs_scan={needs_scan} for {os.path.basename(path)}")
            
            if needs_scan:
                logger.info(f"[DEBUG] Extracting metadata from {os.path.basename(path)}")
                meta = self.extract_pdf(path)
                logger.info(f"[DEBUG] Extracted OK, title={meta.get('title', 'N/A')[:30] if meta.get('title') else 'N/A'}")
                
                pdf_id = self.db.upsert_pdf_file(
                    rel_path, info['sha256'], info['size'], info['mtime'],
                    parse_status='pending',
                    filename=info.get('filename')
                )
                
                if self.needs_ocr(meta.get('text', '')):
                    self.db.update_pdf_status(pdf_id, 'needs_ocr', 'Text too short')
                    paper_id = self.db.upsert_paper(
                        title=meta.get('title') or os.path.basename(path),
                        authors=meta.get('authors') or '',
                        year=meta.get('year'),
                        venue=meta.get('venue') or '',
                        doi=meta.get('doi') or '',
                        url=meta.get('url') or '',
                        entry_type='article',
                        publication_type='other',
                        bibtex_key='',
                        confidence=0,
                        source='pdf'
                    )
                    self.db.link_paper_pdf(paper_id, pdf_id)
                    updated.append({'path': rel_path, 'type': 'paper', 'id': paper_id})
                    logger.info(f"[DEBUG] Added paper (OCR): {rel_path}")
                else:
                    doi, conf, source, full_meta = self.resolve({
                        'title': meta.get('title'),
                        'authors': meta.get('authors'),
                        'year': meta.get('year'),
                        'venue': meta.get('venue'),
                        'doi': meta.get('doi')
                    })
                    
                    final_title = full_meta.get('title') or meta.get('title')
                    final_authors = full_meta.get('authors') or meta.get('authors')
                    final_year = full_meta.get('year') or meta.get('year')
                    final_venue = full_meta.get('venue') or meta.get('venue')
                    final_url = full_meta.get('url') or meta.get('url')
                    
                    entry_type = 'article'
                    venue_lower = (final_venue or '').lower()
                    if any(kw in venue_lower for kw in ['proceedings', 'conference', 'ccs', 'ndss', 'symposium']):
                        entry_type = 'inproceedings'
                    
                    from core.resolver import detect_publication_type
                    publication_type = detect_publication_type(final_venue)
                    
                    bibtex_key = self.gen_key({
                        'authors': final_authors,
                        'year': final_year,
                        'title': final_title
                    })
                    
                    paper_id = self.db.upsert_paper(
                        title=final_title,
                        authors=final_authors,
                        year=final_year,
                        venue=final_venue,
                        doi=doi,
                        url=final_url,
                        entry_type=entry_type,
                        publication_type=publication_type,
                        bibtex_key=bibtex_key,
                        confidence=conf,
                        source=source
                    )
                    self.db.link_paper_pdf(paper_id, pdf_id)
                    
                    status = 'success' if conf >= 80 else ('needs_review' if conf > 0 else 'needs_ocr')
                    self.db.update_pdf_status(pdf_id, status)
                    updated.append({'path': rel_path, 'type': 'paper', 'id': paper_id})
                    logger.info(f"[DEBUG] Added paper: {rel_path}, conf={conf}, doi={doi}")
        
        except Exception as e:
            logger.error(f"[ERROR] Failed to process {os.path.basename(path)}: {e}")
            self.db.upsert_pdf_file(rel_path, info['sha256'], info['size'], info['mtime'],
                                    parse_status='failed', parse_error=str(e)[:500],
                                    filename=info.get('filename'))


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的环境"""
    import sys
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)


class MainWindow(QMainWindow):
    def __init__(self, db, db_path):
        super().__init__()
        self.db = db
        self.db_path = db_path
        self.root_dir = os.path.dirname(os.path.abspath(db_path))
        
        # 设置窗口图标（兼容打包后环境）
        icon_path = get_resource_path("resources/icons/app.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 启用拖放
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._load_theme_setting()
        self.refresh_table()
    
    def _get_abs_path(self, rel_path):
        if not rel_path:
            return None
        if os.path.isabs(rel_path):
            return rel_path
        return os.path.join(self.root_dir, rel_path)
    
    def _setup_ui(self):
        db_name = os.path.basename(self.db_path)
        self.setWindowTitle(f"本地 PDF 文献管理器 - {db_name}")
        self.resize(1400, 900)
        self.move(100, 50)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        toolbar = QHBoxLayout()
        self.btn_scan = QPushButton("扫描文件夹")
        self.btn_scan.setEnabled(False)
        self.btn_scan.setToolTip("扫描功能在创建数据库时自动启用")
        toolbar.addWidget(self.btn_scan)
        
        spacer = QWidget()
        spacer.setFixedWidth(20)
        toolbar.addWidget(spacer)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索...")
        self.search_edit.setFixedWidth(300)
        toolbar.addWidget(self.search_edit)
        
        spacer2 = QWidget()
        spacer2.setFixedWidth(10)
        toolbar.addWidget(spacer2)
        
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("全部标签")
        self.tag_filter.setMinimumWidth(120)
        toolbar.addWidget(self.tag_filter)
        
        spacer3 = QWidget()
        spacer3.setFixedWidth(10)
        toolbar.addWidget(spacer3)
        
        # 年份筛选
        self.year_filter = QComboBox()
        self.year_filter.addItem("全部年份")
        self.year_filter.setMinimumWidth(90)
        self.year_filter.setToolTip("按年份筛选")
        toolbar.addWidget(self.year_filter)
        
        spacer4 = QWidget()
        spacer4.setFixedWidth(15)
        toolbar.addWidget(spacer4)
        
        # 排序按钮
        self.btn_move_up = QPushButton("上移")
        self.btn_move_up.setFixedWidth(50)
        self.btn_move_up.setToolTip("将选中项上移 (Ctrl+Up)")
        self.btn_move_up.clicked.connect(self._move_item_up)
        toolbar.addWidget(self.btn_move_up)
        
        self.btn_move_down = QPushButton("下移")
        self.btn_move_down.setFixedWidth(50)
        self.btn_move_down.setToolTip("将选中项下移 (Ctrl+Down)")
        self.btn_move_down.clicked.connect(self._move_item_down)
        toolbar.addWidget(self.btn_move_down)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(120)
        self.progress_bar.setVisible(False)
        toolbar.addWidget(self.progress_bar)
        
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        
        self.paper_model = PaperTableModel()
        self.paper_table_view = QTableView()
        self.paper_table_view.setModel(self.paper_model)
        self.paper_table_view.setSelectionBehavior(QTableView.SelectRows)
        self.paper_table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.paper_table_view.setWordWrap(False)
        self.paper_table_view.setAlternatingRowColors(True)
        header = self.paper_table_view.horizontalHeader()
        header.setVisible(True)
        header.setFixedHeight(30)
        vheader = self.paper_table_view.verticalHeader()
        vheader.setDefaultSectionSize(22)
        vheader.setVisible(False)
        self.paper_table_view.setSortingEnabled(True)
        self.paper_table_view.sortByColumn(0, Qt.DescendingOrder)
        self.paper_table_view.doubleClicked.connect(self._on_double_click)
        self.paper_table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.paper_table_view.customContextMenuRequested.connect(lambda pos: self._show_context_menu(pos, 'paper'))
        self.paper_table_view.setColumnWidth(0, 35)
        self.paper_table_view.setColumnWidth(1, 280)
        self.paper_table_view.setColumnWidth(2, 160)
        self.paper_table_view.setColumnWidth(3, 50)
        self.paper_table_view.setColumnWidth(4, 120)
        self.paper_table_view.setColumnWidth(5, 150)
        self.paper_table_view.setColumnWidth(6, 80)
        self.paper_table_view.setColumnWidth(7, 70)
        
        self.patent_model = PatentTableModel()
        self.patent_table_view = QTableView()
        self.patent_table_view.setModel(self.patent_model)
        self.patent_table_view.setSelectionBehavior(QTableView.SelectRows)
        self.patent_table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.patent_table_view.setWordWrap(False)
        self.patent_table_view.setAlternatingRowColors(True)
        header = self.patent_table_view.horizontalHeader()
        header.setVisible(True)
        header.setFixedHeight(30)
        vheader = self.patent_table_view.verticalHeader()
        vheader.setDefaultSectionSize(22)
        vheader.setVisible(False)
        self.patent_table_view.setSortingEnabled(True)
        self.patent_table_view.sortByColumn(0, Qt.DescendingOrder)
        self.patent_table_view.doubleClicked.connect(self._on_patent_double_click)
        self.patent_table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.patent_table_view.customContextMenuRequested.connect(lambda pos: self._show_context_menu(pos, 'patent'))
        self.patent_table_view.setColumnWidth(0, 35)   # 序号
        self.patent_table_view.setColumnWidth(1, 250)  # 专利名称
        self.patent_table_view.setColumnWidth(2, 50)   # 专利类型 (缩小)
        self.patent_table_view.setColumnWidth(3, 180)  # 专利号 (增加)
        self.patent_table_view.setColumnWidth(4, 200)  # 发明人 (增加)
        self.patent_table_view.setColumnWidth(5, 90)   # 申请日期
        self.patent_table_view.setColumnWidth(6, 90)   # 授权日期
        self.patent_table_view.setColumnWidth(7, 150)  # 权利人
        
        self.software_model = SoftwareTableModel()
        self.software_table_view = QTableView()
        self.software_table_view.setModel(self.software_model)
        self.software_table_view.setSelectionBehavior(QTableView.SelectRows)
        self.software_table_view.setSelectionMode(QTableView.ExtendedSelection)
        self.software_table_view.setWordWrap(False)
        self.software_table_view.setAlternatingRowColors(True)
        header = self.software_table_view.horizontalHeader()
        header.setVisible(True)
        header.setFixedHeight(30)
        vheader = self.software_table_view.verticalHeader()
        vheader.setDefaultSectionSize(22)
        vheader.setVisible(False)
        self.software_table_view.setSortingEnabled(True)
        self.software_table_view.sortByColumn(0, Qt.DescendingOrder)
        self.software_table_view.doubleClicked.connect(self._on_software_double_click)
        self.software_table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.software_table_view.customContextMenuRequested.connect(lambda pos: self._show_context_menu(pos, 'software'))
        self.software_table_view.setColumnWidth(0, 35)
        self.software_table_view.setColumnWidth(1, 250)
        
        self.detail_panel = DetailPanel()
        self.detail_panel.setFixedWidth(450)
        self.detail_panel.set_database(self.db, self._get_abs_path)
        
        self.patent_detail_panel = PatentDetailPanel()
        self.patent_detail_panel.setFixedWidth(450)
        self.patent_detail_panel.set_database(self.db, self._get_abs_path, self.patent_model)
        
        self.software_detail_panel = SoftwareDetailPanel()
        self.software_detail_panel.setFixedWidth(450)
        self.software_detail_panel.set_database(self.db, self._get_abs_path, self.software_model)
        
        paper_container = QWidget()
        paper_layout = QVBoxLayout(paper_container)
        paper_layout.addWidget(self.paper_table_view)
        
        patent_container = QWidget()
        patent_layout = QVBoxLayout(patent_container)
        patent_layout.addWidget(self.patent_table_view)
        
        software_container = QWidget()
        software_layout = QVBoxLayout(software_container)
        software_layout.addWidget(self.software_table_view)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(paper_container, "论文")
        self.tab_widget.addTab(patent_container, "专利")
        self.tab_widget.addTab(software_container, "软著")
        
        self.stacked_detail = QStackedWidget()
        self.stacked_detail.addWidget(self.detail_panel)
        self.stacked_detail.addWidget(self.patent_detail_panel)
        self.stacked_detail.addWidget(self.software_detail_panel)
        
        splitter.addWidget(self.tab_widget)
        splitter.addWidget(self.stacked_detail)
        splitter.setSizes([950, 450])
        
        layout.addWidget(splitter)
    
    def _setup_menu(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件")
        
        open_db_action = QAction("打开数据库...\tCtrl+O", self)
        open_db_action.setShortcut(QKeySequence("Ctrl+O"))
        open_db_action.triggered.connect(self._open_database)
        file_menu.addAction(open_db_action)
        
        new_db_action = QAction("新建数据库...\tCtrl+N", self)
        new_db_action.setShortcut(QKeySequence("Ctrl+N"))
        new_db_action.triggered.connect(self._new_database)
        file_menu.addAction(new_db_action)
        
        close_db_action = QAction("关闭当前数据库\tCtrl+W", self)
        close_db_action.setShortcut(QKeySequence("Ctrl+W"))
        close_db_action.triggered.connect(self._close_database)
        file_menu.addAction(close_db_action)
        
        refresh_db_action = QAction("刷新数据库\tF5", self)
        refresh_db_action.setShortcut(QKeySequence("F5"))
        refresh_db_action.triggered.connect(self._refresh_database)
        file_menu.addAction(refresh_db_action)
        
        rebuild_db_action = QAction("重建数据库", self)
        rebuild_db_action.triggered.connect(self._rebuild_database)
        file_menu.addAction(rebuild_db_action)
        
        file_menu.addSeparator()
        
        backup_db_action = QAction("备份数据库...", self)
        backup_db_action.triggered.connect(self._backup_database)
        file_menu.addAction(backup_db_action)
        
        restore_db_action = QAction("恢复数据库...", self)
        restore_db_action.triggered.connect(self._restore_database)
        file_menu.addAction(restore_db_action)
        
        open_db_folder_action = QAction("打开数据库所在文件夹", self)
        open_db_folder_action.triggered.connect(self._open_database_folder)
        file_menu.addAction(open_db_folder_action)
        
        file_menu.addSeparator()
        
        add_paper_action = QAction("添加论文...\tCtrl+P", self)
        add_paper_action.setShortcut(QKeySequence("Ctrl+P"))
        add_paper_action.triggered.connect(self._show_add_paper_dialog)
        file_menu.addAction(add_paper_action)
        
        delete_action = QAction("删除选中项目\tDelete", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self._delete_selected_items)
        file_menu.addAction(delete_action)
        
        tools_menu = menubar.addMenu("工具")
        
        view_menu = tools_menu.addMenu("查看")
        
        journal_if_action = QAction("期刊影响因子...", self)
        journal_if_action.triggered.connect(self._show_journal_impact_factors)
        view_menu.addAction(journal_if_action)
        
        paper_detail_action = QAction("论文详情...", self)
        paper_detail_action.triggered.connect(self._show_paper_detail_view)
        view_menu.addAction(paper_detail_action)
        
        stats_menu = tools_menu.addMenu("统计报表")
        
        yearly_stats_action = QAction("年度发文统计...", self)
        yearly_stats_action.triggered.connect(self._show_yearly_stats)
        stats_menu.addAction(yearly_stats_action)
        
        journal_dist_action = QAction("期刊分布统计...", self)
        journal_dist_action.triggered.connect(self._show_journal_distribution)
        stats_menu.addAction(journal_dist_action)
        
        type_dist_action = QAction("类型分布统计...", self)
        type_dist_action.triggered.connect(self._show_type_distribution)
        stats_menu.addAction(type_dist_action)
        
        tools_menu.addSeparator()
        
        fulltext_search_action = QAction("全文搜索...", self)
        fulltext_search_action.setShortcut("Ctrl+Shift+F")
        fulltext_search_action.triggered.connect(self._show_fulltext_search)
        tools_menu.addAction(fulltext_search_action)
        
        build_index_action = QAction("建立全文索引...", self)
        build_index_action.triggered.connect(self._build_fulltext_index)
        tools_menu.addAction(build_index_action)
        
        settings_menu = menubar.addMenu("设置")
        
        scan_prefs_action = QAction("扫描设置...", self)
        scan_prefs_action.triggered.connect(self._show_preferences)
        settings_menu.addAction(scan_prefs_action)
        
        literature_prefs_action = QAction("文献设置...", self)
        literature_prefs_action.triggered.connect(self._show_literature_settings)
        settings_menu.addAction(literature_prefs_action)
        
        proxy_action = QAction("代理设置...", self)
        proxy_action.triggered.connect(self._show_proxy_settings)
        settings_menu.addAction(proxy_action)
        
        settings_menu.addSeparator()
        
        self.dark_mode_action = QAction("深色模式", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.triggered.connect(self._toggle_dark_mode)
        settings_menu.addAction(self.dark_mode_action)
        
        file_menu.addSeparator()
        
        export_bibtex = QAction("导出 BibTeX", self)
        export_bibtex.triggered.connect(lambda: self._export('bibtex'))
        file_menu.addAction(export_bibtex)
        
        export_ris = QAction("导出 RIS (EndNote/Zotero)", self)
        export_ris.triggered.connect(lambda: self._export('ris'))
        file_menu.addAction(export_ris)
        
        export_gbt = QAction("导出 GB/T 7714", self)
        export_gbt.triggered.connect(lambda: self._export('gbt'))
        file_menu.addAction(export_gbt)
        
        copy_gbt = QAction("复制 GB/T 7714", self)
        copy_gbt.triggered.connect(lambda: self._export('gbt_copy'))
        file_menu.addAction(copy_gbt)
        
        file_menu.addSeparator()
        
        export_patents_csv = QAction("导出专利 CSV", self)
        export_patents_csv.triggered.connect(lambda: self._export('patents_csv'))
        file_menu.addAction(export_patents_csv)
        
        export_softwares_csv = QAction("导出软著 CSV", self)
        export_softwares_csv.triggered.connect(lambda: self._export('softwares_csv'))
        file_menu.addAction(export_softwares_csv)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        help_menu = menubar.addMenu("帮助")
        
        shortcuts_action = QAction("快捷键列表...", self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)
    
    def _show_shortcuts(self):
        shortcuts = [
            ("Ctrl+O", "打开数据库"),
            ("Ctrl+N", "新建数据库"),
            ("Ctrl+W", "关闭数据库"),
            ("F5", "刷新数据库"),
            ("Ctrl+F", "搜索框聚焦"),
            ("Enter / 双击", "打开PDF/证书"),
            ("Delete", "删除选中项目"),
            ("Ctrl+S", "保存修改（论文/专利/软著详情）"),
            ("Ctrl+Up", "上移选中项"),
            ("Ctrl+Down", "下移选中项"),
            ("Ctrl+Q", "退出程序"),
            ("Ctrl+1/2/3", "切换到论文/专利/软著标签"),
        ]
        
        text = "快捷键列表\n" + "="*30 + "\n\n"
        for key, desc in shortcuts:
            text += f"{key:<15} {desc}\n"
        
        QMessageBox.information(self, "快捷键", text)
    
    def _connect_signals(self):
        self.btn_scan.clicked.connect(self._start_scan)
        self.search_edit.textChanged.connect(self._on_search)
        self.tag_filter.currentTextChanged.connect(self._on_tag_filter)
        self.year_filter.currentTextChanged.connect(self._on_year_filter)
        self.detail_panel.data_changed.connect(lambda p: self.refresh_table())
        self.patent_detail_panel.data_changed.connect(lambda p: self.refresh_patents())
        self.software_detail_panel.data_changed.connect(lambda p: self.refresh_softwares())
        self.paper_table_view.selectionModel().currentChanged.connect(self._on_paper_current_changed)
        self.paper_table_view.selectionModel().selectionChanged.connect(self._on_paper_selection_changed)
        self.patent_table_view.selectionModel().currentChanged.connect(self._on_patent_current_changed)
        self.software_table_view.selectionModel().currentChanged.connect(self._on_software_current_changed)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self._update_scan_button_state()
        
        # 快捷键（菜单中已定义的快捷键不需要重复定义）
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.tab_widget.setCurrentIndex(0))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.tab_widget.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.tab_widget.setCurrentIndex(2))
        QShortcut(QKeySequence("Return"), self, self._open_selected_file)
        QShortcut(QKeySequence("Enter"), self, self._open_selected_file)
        QShortcut(QKeySequence("Ctrl+C"), self, self._copy_selected_citation)
        QShortcut(QKeySequence("Ctrl+E"), self, self._open_selected_folder)
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_current_detail)
        QShortcut(QKeySequence("Escape"), self, self._clear_search)
        QShortcut(QKeySequence("Ctrl+Up"), self, self._move_item_up)
        QShortcut(QKeySequence("Ctrl+Down"), self, self._move_item_down)
    
    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            # 检查是否有PDF文件
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragMoveEvent(self, event):
        """拖拽移动事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """拖拽放下事件"""
        if not self.db or not self.root_dir:
            QMessageBox.warning(self, "警告", "请先打开或创建数据库")
            event.ignore()
            return
        
        pdf_files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.pdf'):
                pdf_files.append(file_path)
        
        if not pdf_files:
            event.ignore()
            return
        
        event.acceptProposedAction()
        
        # 处理拖入的PDF文件
        self._process_dropped_files(pdf_files)
    
    def _process_dropped_files(self, pdf_files):
        """处理拖入的PDF文件"""
        import shutil
        import hashlib
        
        current_tab = self.tab_widget.currentIndex()
        added_count = 0
        errors = []
        
        for pdf_path in pdf_files:
            try:
                filename = os.path.basename(pdf_path)
                dest_path = os.path.join(self.root_dir, filename)
                
                # 如果文件已存在，添加数字后缀
                if os.path.exists(dest_path) and os.path.abspath(pdf_path) != os.path.abspath(dest_path):
                    base, ext = os.path.splitext(filename)
                    counter = 1
                    while os.path.exists(dest_path):
                        dest_path = os.path.join(self.root_dir, f"{base}_{counter}{ext}")
                        counter += 1
                    filename = os.path.basename(dest_path)
                
                # 如果源文件不在根目录，则复制
                if os.path.abspath(pdf_path) != os.path.abspath(dest_path):
                    shutil.copy2(pdf_path, dest_path)
                    self.statusBar().showMessage(f"已复制: {filename}")
                
                # 计算文件信息
                with open(dest_path, 'rb') as f:
                    sha256 = hashlib.sha256(f.read()).hexdigest()
                
                stat = os.stat(dest_path)
                rel_path = os.path.relpath(dest_path, self.root_dir)
                
                # 根据当前标签页处理
                if current_tab == 0:
                    # 论文标签页 - 解析PDF并添加论文
                    self._add_paper_from_pdf(dest_path, rel_path, sha256, stat)
                elif current_tab == 1:
                    # 专利标签页 - 尝试识别专利证书
                    self._add_patent_from_pdf(dest_path, rel_path)
                elif current_tab == 2:
                    # 软著标签页 - 尝试识别软著证书
                    self._add_software_from_pdf(dest_path, rel_path)
                
                added_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process dropped file {pdf_path}: {e}")
                errors.append(f"{os.path.basename(pdf_path)}: {str(e)}")
        
        # 刷新表格
        if current_tab == 0:
            self.refresh_table()
        elif current_tab == 1:
            self.refresh_patents()
        elif current_tab == 2:
            self.refresh_softwares()
        
        # 显示结果
        if added_count > 0:
            tab_names = ["论文", "专利", "软著"]
            msg = f"已添加 {added_count} 个{tab_names[current_tab]}文件"
            if errors:
                msg += f"\n\n{len(errors)} 个文件处理失败"
            QMessageBox.information(self, "完成", msg)
        elif errors:
            QMessageBox.warning(self, "错误", f"所有文件处理失败:\n" + "\n".join(errors[:5]))
    
    def _add_paper_from_pdf(self, pdf_path, rel_path, sha256, stat):
        """从PDF添加论文"""
        from core.extractor import extract_metadata_from_pdf, needs_ocr, generate_bibtex_key
        from core.resolver import resolve_doi, detect_publication_type
        
        # 提取元数据
        meta = extract_metadata_from_pdf(pdf_path)
        
        # 添加PDF记录
        pdf_id = self.db.upsert_pdf_file(
            path=rel_path,
            sha256=sha256,
            size=stat.st_size,
            mtime=stat.st_mtime,
            parse_status='pending',
            filename=os.path.basename(pdf_path)
        )
        
        # 尝试解析DOI
        if not needs_ocr(meta.get('text', '')):
            doi, conf, source, full_meta = resolve_doi({
                'title': meta.get('title'),
                'authors': meta.get('authors'),
                'year': meta.get('year'),
                'venue': meta.get('venue'),
                'doi': meta.get('doi')
            })
            
            final_title = full_meta.get('title') or meta.get('title') or os.path.basename(pdf_path)
            final_authors = full_meta.get('authors') or meta.get('authors') or ''
            final_year = full_meta.get('year') or meta.get('year')
            final_venue = full_meta.get('venue') or meta.get('venue') or ''
            final_url = full_meta.get('url') or meta.get('url') or ''
            
            entry_type = 'article'
            venue_lower = (final_venue or '').lower()
            if any(kw in venue_lower for kw in ['proceedings', 'conference', 'symposium']):
                entry_type = 'inproceedings'
            
            publication_type = detect_publication_type(final_venue)
            
            bibtex_key = generate_bibtex_key({
                'authors': final_authors,
                'year': final_year,
                'title': final_title
            })
            
            paper_id = self.db.upsert_paper(
                title=final_title,
                authors=final_authors,
                year=final_year,
                venue=final_venue,
                doi=doi,
                url=final_url,
                entry_type=entry_type,
                publication_type=publication_type,
                bibtex_key=bibtex_key,
                confidence=conf,
                source=source
            )
            
            status = 'success' if conf >= 80 else ('needs_review' if conf > 0 else 'needs_ocr')
            self.db.update_pdf_status(pdf_id, status)
        else:
            # 需要OCR
            paper_id = self.db.upsert_paper(
                title=meta.get('title') or os.path.basename(pdf_path),
                authors=meta.get('authors') or '',
                year=meta.get('year'),
                venue=meta.get('venue') or '',
                doi=meta.get('doi') or '',
                url=meta.get('url') or '',
                entry_type='article',
                publication_type='other',
                bibtex_key='',
                confidence=0,
                source='pdf'
            )
            self.db.update_pdf_status(pdf_id, 'needs_ocr', 'Text too short')
        
        self.db.link_paper_pdf(paper_id, pdf_id)
    
    def _add_patent_from_pdf(self, pdf_path, rel_path):
        """从PDF添加专利"""
        from core.extractor import extract_certificate_info
        
        result = extract_certificate_info(pdf_path)
        
        if result.get('type') == 'patent':
            data = result['data']
            self.db.upsert_patent(
                title=data.get('title') or os.path.basename(pdf_path),
                patent_number=data.get('patent_number') or '',
                grant_number=data.get('grant_number') or '',
                inventors=data.get('inventors') or '',
                patentee=data.get('patentee') or '',
                application_date=data.get('application_date') or '',
                grant_date=data.get('grant_date') or '',
                patent_type='发明',
                file_path=rel_path
            )
        else:
            # 无法识别为专利，添加空记录
            self.db.upsert_patent(
                title=os.path.basename(pdf_path),
                patent_number='',
                grant_number='',
                inventors='',
                patentee='',
                application_date='',
                grant_date='',
                patent_type='发明',
                file_path=rel_path
            )
    
    def _add_software_from_pdf(self, pdf_path, rel_path):
        """从PDF添加软著"""
        from core.extractor import extract_certificate_info
        
        result = extract_certificate_info(pdf_path)
        
        if result.get('type') == 'software':
            data = result['data']
            self.db.upsert_software(
                software_name=data.get('software_name') or '',
                title=data.get('software_name') or os.path.basename(pdf_path),
                version=data.get('version') or '',
                registration_number=data.get('registration_number') or '',
                copyright_holder=data.get('copyright_holder') or '',
                development_date=data.get('development_date') or '',
                file_path=rel_path
            )
        else:
            # 无法识别为软著，添加空记录
            self.db.upsert_software(
                software_name='',
                title=os.path.basename(pdf_path),
                version='',
                registration_number='',
                copyright_holder='',
                development_date='',
                file_path=rel_path
            )
    
    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()
    
    def _clear_search(self):
        self.search_edit.clear()
        self._on_search_changed('')
    
    def _save_current_detail(self):
        """Ctrl+S: 保存当前详情面板的修改"""
        current_tab = self.tab_widget.currentIndex()
        if current_tab == 0:
            self.detail_panel._save_changes()
        elif current_tab == 1:
            self.patent_detail_panel._save()
        elif current_tab == 2:
            self.software_detail_panel._save()
    
    def _move_item_up(self):
        """Ctrl+Up: 将选中项上移"""
        if not self.db:
            return
        
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:
            indexes = self.paper_table_view.selectionModel().selectedRows()
            if not indexes:
                return
            row = indexes[0].row()
            if row == 0:
                return  # 已经在最上面
            
            item_id = self.paper_model._data[row]['id']
            if self.db.move_item_up('papers', item_id, self.paper_model._data):
                # 刷新数据
                papers = self.db.get_all_papers()
                self.paper_model.update_data(papers)
                # 重新选中移动后的行
                self.paper_table_view.selectRow(row - 1)
                self.statusBar().showMessage(f"已上移", 2000)
        
        elif current_tab == 1:
            indexes = self.patent_table_view.selectionModel().selectedRows()
            if not indexes:
                return
            row = indexes[0].row()
            if row == 0:
                return
            
            item_id = self.patent_model._data[row]['id']
            if self.db.move_item_up('patents', item_id, self.patent_model._data):
                patents = self.db.get_all_patents()
                self.patent_model.update_data(patents)
                self.patent_table_view.selectRow(row - 1)
                self.statusBar().showMessage(f"已上移", 2000)
        
        elif current_tab == 2:
            indexes = self.software_table_view.selectionModel().selectedRows()
            if not indexes:
                return
            row = indexes[0].row()
            if row == 0:
                return
            
            item_id = self.software_model._data[row]['id']
            if self.db.move_item_up('softwares', item_id, self.software_model._data):
                softwares = self.db.get_all_softwares()
                self.software_model.update_data(softwares)
                self.software_table_view.selectRow(row - 1)
                self.statusBar().showMessage(f"已上移", 2000)
    
    def _move_item_down(self):
        """Ctrl+Down: 将选中项下移"""
        if not self.db:
            return
        
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:
            indexes = self.paper_table_view.selectionModel().selectedRows()
            if not indexes:
                return
            row = indexes[0].row()
            if row >= len(self.paper_model._data) - 1:
                return  # 已经在最下面
            
            item_id = self.paper_model._data[row]['id']
            if self.db.move_item_down('papers', item_id, self.paper_model._data):
                papers = self.db.get_all_papers()
                self.paper_model.update_data(papers)
                self.paper_table_view.selectRow(row + 1)
                self.statusBar().showMessage(f"已下移", 2000)
        
        elif current_tab == 1:
            indexes = self.patent_table_view.selectionModel().selectedRows()
            if not indexes:
                return
            row = indexes[0].row()
            if row >= len(self.patent_model._data) - 1:
                return
            
            item_id = self.patent_model._data[row]['id']
            if self.db.move_item_down('patents', item_id, self.patent_model._data):
                patents = self.db.get_all_patents()
                self.patent_model.update_data(patents)
                self.patent_table_view.selectRow(row + 1)
                self.statusBar().showMessage(f"已下移", 2000)
        
        elif current_tab == 2:
            indexes = self.software_table_view.selectionModel().selectedRows()
            if not indexes:
                return
            row = indexes[0].row()
            if row >= len(self.software_model._data) - 1:
                return
            
            item_id = self.software_model._data[row]['id']
            if self.db.move_item_down('softwares', item_id, self.software_model._data):
                softwares = self.db.get_all_softwares()
                self.software_model.update_data(softwares)
                self.software_table_view.selectRow(row + 1)
                self.statusBar().showMessage(f"已下移", 2000)
    
    def _open_selected_file(self):
        """Enter: 打开选中文件"""
        current_tab = self.tab_widget.currentIndex()
        if current_tab == 0:
            indexes = self.paper_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                paper = self.paper_model.get_paper_at(row)
                if paper:
                    file_path = paper.get('file_path', '')
                    if file_path:
                        abs_path = self._get_abs_path(file_path)
                        if abs_path and os.path.exists(abs_path):
                            os.startfile(abs_path)
        elif current_tab == 1:
            indexes = self.patent_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                patent = self.patent_model.get_patent_at(row)
                if patent:
                    file_path = patent.get('file_path', '')
                    if file_path:
                        abs_path = self._get_abs_path(file_path)
                        if abs_path and os.path.exists(abs_path):
                            os.startfile(abs_path)
        elif current_tab == 2:
            indexes = self.software_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                software = self.software_model.get_software_at(row)
                if software:
                    file_path = software.get('file_path', '')
                    if file_path:
                        abs_path = self._get_abs_path(file_path)
                        if abs_path and os.path.exists(abs_path):
                            os.startfile(abs_path)
    
    def _open_selected_folder(self):
        """Ctrl+E: 打开选中文件所在文件夹"""
        current_tab = self.tab_widget.currentIndex()
        rel_path = None
        
        if current_tab == 0:
            indexes = self.paper_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                rel_path = self.paper_model._data[row].get('rel_path', '')
        elif current_tab == 1:
            indexes = self.patent_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                rel_path = self.patent_model._data[row].get('pdf_path', '')
        elif current_tab == 2:
            indexes = self.software_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                rel_path = self.software_model._data[row].get('pdf_path', '')
        
        if rel_path:
            abs_path = self._get_abs_path(rel_path)
            if abs_path and os.path.exists(abs_path):
                folder = os.path.dirname(abs_path)
                os.startfile(folder)
    
    def _copy_selected_citation(self):
        """Ctrl+C: 复制选中项的引用"""
        current_tab = self.tab_widget.currentIndex()
        if current_tab == 0:
            indexes = self.paper_table_view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                data = self.paper_model._data[row]
                from core.export import format_gbt7714
                citation = format_gbt7714(data)
                QApplication.clipboard().setText(citation)
                self.statusBar().showMessage("已复制引用到剪贴板")
    
    def _update_scan_button_state(self):
        has_db = self.db is not None
        self.btn_scan.setEnabled(not has_db)
        self.btn_scan.setToolTip("请先打开或创建数据库" if not has_db else "扫描功能在创建数据库时自动启用")
    
    @Slot()
    def refresh_table(self):
        current_tag = self.tag_filter.currentText()
        if current_tag and current_tag != "全部标签":
            papers = self.db.get_papers_by_tag_name(current_tag)
        else:
            papers = self.db.get_all_papers()
        
        # 应用年份筛选
        papers = self._apply_year_filter(papers)
        self.paper_model.update_data(papers)
        
        self._refresh_tag_filter()
        self._update_year_filter()
    
    def refresh_patents(self):
        if self.db:
            current_tag = self.tag_filter.currentText()
            if current_tag and current_tag != "全部标签":
                patents = self.db.get_patents_by_tag_name(current_tag)
            else:
                patents = self.db.get_all_patents()
            
            # 应用年份筛选
            patents = self._apply_year_filter(patents, year_field='grant_date')
            self.patent_model.update_data(patents)
    
    def refresh_softwares(self):
        if self.db:
            current_tag = self.tag_filter.currentText()
            if current_tag and current_tag != "全部标签":
                softwares = self.db.get_softwares_by_tag_name(current_tag)
            else:
                softwares = self.db.get_all_softwares()
            
            # 应用年份筛选
            softwares = self._apply_year_filter(softwares, year_field='development_date')
            self.software_model.update_data(softwares)
    
    def _on_tab_changed(self, index):
        self.stacked_detail.setCurrentIndex(index)
        
        # 更新搜索框占位符
        placeholders = ["搜索论文...", "搜索专利...", "搜索软著..."]
        self.search_edit.setPlaceholderText(placeholders[index])
        self.search_edit.clear()
        
        # 刷新标签筛选
        self._refresh_tag_filter()
        
        # 刷新年份筛选
        self._update_year_filter()
        
        if index == 0:
            self.refresh_table()
        elif index == 1:
            self.refresh_patents()
        elif index == 2:
            self.refresh_softwares()
    
    def _on_paper_current_changed(self, current, previous):
        if current.isValid():
            row = current.row()
            paper = self.paper_model.get_paper_at(row)
            if paper:
                self.detail_panel.load_paper(paper)
    
    def _on_paper_selection_changed(self, selected, deselected):
        """当论文选择变化时，更新detail_panel的选中论文列表"""
        indexes = self.paper_table_view.selectionModel().selectedRows()
        selected_papers = []
        for index in indexes:
            row = index.row()
            paper = self.paper_model.get_paper_at(row)
            if paper:
                selected_papers.append(paper)
        self.detail_panel.set_selected_papers(selected_papers)
    
    def _on_patent_current_changed(self, current, previous):
        if current.isValid():
            row = current.row()
            patent = self.patent_model.get_patent_at(row)
            if patent:
                self.patent_detail_panel.load_patent(patent)
    
    def _on_software_current_changed(self, current, previous):
        if current.isValid():
            row = current.row()
            software = self.software_model.get_software_at(row)
            if software:
                self.software_detail_panel.load_software(software)
    
    def _on_patent_double_click(self, index):
        row = index.row()
        patent = self.patent_model.get_patent_at(row)
        if patent:
            file_path = patent.get('file_path')
            if file_path:
                abs_path = self._get_abs_path(file_path)
                if abs_path and os.path.exists(abs_path):
                    try:
                        os.startfile(abs_path)
                    except Exception as e:
                        QMessageBox.warning(self, "错误", f"无法打开文件: {e}")
    
    def _on_software_double_click(self, index):
        row = index.row()
        software = self.software_model.get_software_at(row)
        if software:
            file_path = software.get('file_path')
            if file_path:
                abs_path = self._get_abs_path(file_path)
                if abs_path and os.path.exists(abs_path):
                    try:
                        os.startfile(abs_path)
                    except Exception as e:
                        QMessageBox.warning(self, "错误", f"无法打开文件: {e}")
    
    def _refresh_tag_filter(self):
        """刷新标签筛选下拉框（根据当前标签页）"""
        current_text = self.tag_filter.currentText()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签")
        
        if self.db:
            current_tab = self.tab_widget.currentIndex()
            if current_tab == 0:
                # 论文标签
                tags = self.db.get_all_tags()
            elif current_tab == 1:
                # 专利标签
                tags = self.db.get_all_patent_tags()
            else:
                # 软著标签
                tags = self.db.get_all_software_tags()
            
            for tag in tags:
                self.tag_filter.addItem(tag['name'])
        
        # 恢复之前选中的标签（如果存在）
        index = self.tag_filter.findText(current_text)
        if index >= 0:
            self.tag_filter.setCurrentIndex(index)
        else:
            self.tag_filter.setCurrentIndex(0)
        
        self.tag_filter.blockSignals(False)
    
    def _on_tag_filter(self, tag_name):
        """按标签筛选（根据当前标签页）"""
        if not self.db:
            return
        
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:
            # 论文
            if tag_name == "全部标签" or not tag_name:
                papers = self.db.get_all_papers()
            else:
                papers = self.db.get_papers_by_tag_name(tag_name)
            # 应用年份筛选
            papers = self._apply_year_filter(papers)
            self.paper_model.update_data(papers)
            self.statusBar().showMessage(f"筛选: {tag_name} ({len(papers)} 篇)")
        
        elif current_tab == 1:
            # 专利
            if tag_name == "全部标签" or not tag_name:
                patents = self.db.get_all_patents()
            else:
                patents = self.db.get_patents_by_tag_name(tag_name)
            # 应用年份筛选
            patents = self._apply_year_filter(patents, year_field='grant_date')
            self.patent_model.update_data(patents)
            self.statusBar().showMessage(f"筛选: {tag_name} ({len(patents)} 项)")
        
        else:
            # 软著
            if tag_name == "全部标签" or not tag_name:
                softwares = self.db.get_all_softwares()
            else:
                softwares = self.db.get_softwares_by_tag_name(tag_name)
            # 应用年份筛选
            softwares = self._apply_year_filter(softwares, year_field='development_date')
            self.software_model.update_data(softwares)
            self.statusBar().showMessage(f"筛选: {tag_name} ({len(softwares)} 个)")
    
    def _on_year_filter(self, year_text):
        """按年份筛选"""
        if not self.db:
            return
        
        # 重新应用标签筛选（会自动应用年份筛选）
        self._on_tag_filter(self.tag_filter.currentText())
    
    def _apply_year_filter(self, items, year_field='year'):
        """应用年份筛选"""
        year_text = self.year_filter.currentText()
        if year_text == "全部年份" or not year_text:
            return items
        
        try:
            filter_year = int(year_text)
            filtered = []
            for item in items:
                item_year = item.get(year_field)
                # 处理不同格式的年份
                if item_year:
                    if isinstance(item_year, int):
                        if item_year == filter_year:
                            filtered.append(item)
                    elif isinstance(item_year, str):
                        # 从日期字符串中提取年份
                        import re
                        year_match = re.search(r'(\d{4})', str(item_year))
                        if year_match and int(year_match.group(1)) == filter_year:
                            filtered.append(item)
            return filtered
        except ValueError:
            return items
    
    def _update_year_filter(self):
        """更新年份筛选下拉列表"""
        if not self.db:
            return
        
        current_tab = self.tab_widget.currentIndex()
        years = set()
        
        if current_tab == 0:
            # 论文年份
            papers = self.db.get_all_papers()
            for p in papers:
                year = p.get('year')
                if year:
                    years.add(int(year))
        elif current_tab == 1:
            # 专利年份（从授权日期提取）
            patents = self.db.get_all_patents()
            import re
            for p in patents:
                date = p.get('grant_date', '')
                if date:
                    match = re.search(r'(\d{4})', str(date))
                    if match:
                        years.add(int(match.group(1)))
        else:
            # 软著年份（从开发完成日期提取）
            softwares = self.db.get_all_softwares()
            import re
            for s in softwares:
                date = s.get('development_date', '')
                if date:
                    match = re.search(r'(\d{4})', str(date))
                    if match:
                        years.add(int(match.group(1)))
        
        # 更新下拉列表
        self.year_filter.blockSignals(True)
        current_year = self.year_filter.currentText()
        self.year_filter.clear()
        self.year_filter.addItem("全部年份")
        for year in sorted(years, reverse=True):
            self.year_filter.addItem(str(year))
        
        # 恢复之前的选择
        idx = self.year_filter.findText(current_year)
        if idx >= 0:
            self.year_filter.setCurrentIndex(idx)
        self.year_filter.blockSignals(False)
    
    @Slot()
    def _start_scan(self):
        if not self.db:
            QMessageBox.warning(self, "警告", "请先打开或创建数据库")
            return
        
        directory = QFileDialog.getExistingDirectory(self, "选择包含PDF的文件夹", self.root_dir)
        if not directory:
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("扫描中...")
        
        self.scan_thread = ScanThread(self.db, directory)
        self.scan_thread.progress.connect(self.progress_bar.setValue)
        self.scan_thread.status.connect(self.statusBar().showMessage)
        self.scan_thread.finished.connect(self._on_scan_finished)
        self.scan_thread.start()
    
    def _refresh_database(self):
        print(f"[DEBUG] _refresh_database called: db={self.db is not None}, root_dir={self.root_dir}")
        if not self.db or not self.root_dir:
            print("[DEBUG] _refresh_database: db or root_dir is None, returning")
            QMessageBox.warning(self, "警告", "请先打开或创建数据库")
            return
        
        directory = self.root_dir
        print(f"[DEBUG] _refresh_database: starting scan on {directory}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("刷新中...")
        
        self.scan_thread = ScanThread(self.db, directory)
        self.scan_thread.progress.connect(self.progress_bar.setValue)
        self.scan_thread.status.connect(self.statusBar().showMessage)
        self.scan_thread.finished.connect(self._on_scan_finished)
        self.scan_thread.start()
    
    def _rebuild_database(self):
        """重建数据库：删除现有数据库并重新扫描"""
        if not self.db or not self.root_dir:
            QMessageBox.warning(self, "警告", "请先打开数据库")
            return
        
        reply = QMessageBox.question(
            self,
            "重建数据库",
            "确定要重建数据库吗？\n这将删除现有数据库文件并重新扫描文件夹中的所有PDF文件。\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        try:
            self.statusBar().showMessage("正在重建数据库...")
            QApplication.processEvents()
            
            original_db_path = self.db.db_path
            root_dir = self.root_dir
            
            self.db = None
            
            if os.path.exists(original_db_path):
                os.remove(original_db_path)
                logger.info(f"Removed old database: {original_db_path}")
            
            from db.database import Database
            self.db = Database(original_db_path)
            self.db_path = original_db_path
            
            self.detail_panel.set_database(self.db, self._get_abs_path)
            self.patent_detail_panel.set_database(self.db, self._get_abs_path, self.patent_model)
            self.software_detail_panel.set_database(self.db, self._get_abs_path, self.software_model)
            
            self.paper_model.update_data([])
            self.patent_model.update_data([])
            self.software_model.update_data([])
            
            QApplication.processEvents()
            
            self._refresh_database()
            self.statusBar().showMessage("数据库已重建")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重建数据库失败:\n{e}")
    
    def _on_scan_finished(self, updated):
        self.progress_bar.setVisible(False)
        self.refresh_table()
        self.refresh_patents()
        self.refresh_softwares()
        if updated:
            paper_count = sum(1 for u in updated if u.get('type') == 'paper')
            patent_count = sum(1 for u in updated if u.get('type') == 'patent')
            software_count = sum(1 for u in updated if u.get('type') == 'software')
            msg = f"扫描完成，新增/更新: {paper_count} 篇文献, {patent_count} 项专利, {software_count} 项软著"
            QMessageBox.information(self, "完成", msg)
        else:
            self.statusBar().showMessage("扫描完成，无新增内容")
    
    def _backup_database(self):
        if not self.db or not self.db_path:
            QMessageBox.warning(self, "警告", "没有打开的数据库")
            return
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"literature_backup_{timestamp}.sql"
        
        path, _ = QFileDialog.getSaveFileName(
            self, "备份数据库", default_name, "SQL Files (*.sql)"
        )
        if not path:
            return
        
        try:
            self.statusBar().showMessage("正在备份数据库...")
            QApplication.processEvents()
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write("-- 数据库备份\n")
                f.write(f"-- 备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("-- =====================\n\n")
                
                for table in ['papers', 'pdf_files', 'paper_files', 'patents', 'softwares', 'tags', 'paper_tags']:
                    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    table_sql = cursor.fetchone()
                    if table_sql:
                        f.write(f"-- 表: {table}\n")
                        f.write(table_sql[0] + ';\n\n')
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    cursor.execute(f"SELECT * FROM {table}")
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    
                    if rows:
                        f.write(f"-- 数据: {table}\n")
                        for row in rows:
                            values = []
                            for val in row:
                                if val is None:
                                    values.append('NULL')
                                elif isinstance(val, (int, float)):
                                    values.append(str(val))
                                elif isinstance(val, bytes):
                                    values.append(repr(val))
                                else:
                                    values.append("'" + str(val).replace("'", "''") + "'")
                            f.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});\n")
                        f.write('\n')
                
                conn.close()
            
            self.statusBar().showMessage(f"备份完成: {path}")
            QMessageBox.information(self, "完成", f"数据库已备份到:\n{path}")
            
        except Exception as e:
            self.statusBar().showMessage("备份失败")
            QMessageBox.critical(self, "错误", f"备份失败:\n{e}")
    
    def _restore_database(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "恢复数据库", "", "SQL Files (*.sql)"
        )
        if not path:
            return
        
        reply = QMessageBox.question(
            self, "确认恢复",
            "恢复数据库将覆盖当前数据！\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        try:
            self.statusBar().showMessage("正在恢复数据库...")
            QApplication.processEvents()
            
            with open(path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]
            
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
            
            conn.commit()
            
            cursor.executescript(sql_content)
            conn.commit()
            conn.close()
            
            self.refresh_table()
            self.refresh_patents()
            self.refresh_softwares()
            
            self.statusBar().showMessage("恢复完成")
            QMessageBox.information(self, "完成", "数据库已恢复")
            
        except Exception as e:
            self.statusBar().showMessage("恢复失败")
            QMessageBox.critical(self, "错误", f"恢复失败:\n{e}")
    
    def _open_database_folder(self):
        """打开数据库所在文件夹"""
        if not self.db:
            QMessageBox.warning(self, "警告", "请先打开或创建数据库")
            return
        
        db_path = self.db.db_path
        if db_path:
            folder = os.path.dirname(os.path.abspath(db_path))
            if os.path.exists(folder):
                os.startfile(folder)
            else:
                QMessageBox.warning(self, "警告", f"文件夹不存在: {folder}")
        else:
            QMessageBox.warning(self, "警告", "无法获取数据库路径")
    
    @Slot()
    def _on_search(self, text):
        """搜索（根据当前标签页）"""
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:
            # 论文搜索
            if not text:
                self.refresh_table()
                return
            papers = self.db.get_all_papers()
            text_lower = text.lower()
            filtered = [p for p in papers if any(
                text_lower in (str(p.get(f, '')) or '').lower() 
                for f in ['title', 'authors', 'doi', 'venue']
            )]
            self.paper_model.update_data(filtered)
            self.statusBar().showMessage(f"搜索结果: {len(filtered)} 篇")
        
        elif current_tab == 1:
            # 专利搜索
            if not text:
                self.refresh_patents()
                return
            patents = self.db.get_all_patents()
            text_lower = text.lower()
            filtered = [p for p in patents if any(
                text_lower in (str(p.get(f, '')) or '').lower() 
                for f in ['title', 'patent_number', 'inventors', 'patentee', 'grant_number']
            )]
            self.patent_model.update_data(filtered)
            self.statusBar().showMessage(f"搜索结果: {len(filtered)} 项")
        
        else:
            # 软著搜索
            if not text:
                self.refresh_softwares()
                return
            softwares = self.db.get_all_softwares()
            text_lower = text.lower()
            filtered = [s for s in softwares if any(
                text_lower in (str(s.get(f, '')) or '').lower() 
                for f in ['software_name', 'title', 'registration_number', 'copyright_holder']
            )]
            self.software_model.update_data(filtered)
            self.statusBar().showMessage(f"搜索结果: {len(filtered)} 个")
    
    def _on_row_click(self, index):
        row = index.row()
        paper = self.paper_model.get_paper_at(row)
        if paper:
            self.detail_panel.load_paper(paper)
    
    def _on_double_click(self, index):
        row = index.row()
        paper = self.paper_model.get_paper_at(row)
        if paper:
            file_path = paper.get('file_path')
            if file_path:
                abs_path = self._get_abs_path(file_path)
                if abs_path and os.path.exists(abs_path):
                    try:
                        os.startfile(abs_path)
                    except Exception as e:
                        QMessageBox.warning(self, "错误", f"无法打开文件: {e}")
                else:
                    QMessageBox.warning(self, "错误", f"文件不存在: {abs_path}")
    
    def _open_database(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择数据库文件",
            self.root_dir,
            "SQLite Database (*.db);;All Files (*)"
        )
        if path and os.path.exists(path):
            try:
                from db.database import Database
                self.db = Database(path)
                self.db_path = path
                self.root_dir = os.path.dirname(os.path.abspath(path))
                
                db_name = os.path.basename(path)
                self.setWindowTitle(f"本地 PDF 文献管理器 - {db_name}")
                
                self.detail_panel.set_database(self.db, self._get_abs_path)
                self.patent_detail_panel.set_database(self.db, self._get_abs_path, self.patent_model)
                self.software_detail_panel.set_database(self.db, self._get_abs_path, self.software_model)
                self._update_scan_button_state()
                self.refresh_table()
                self.statusBar().showMessage(f"已打开: {path}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法打开数据库:\n{e}")
    
    def _load_existing_db(self):
        """加载已存在的数据库"""
        try:
            from db.database import Database
            self.db = Database(self.db_path)
            self.root_dir = os.path.dirname(os.path.abspath(self.db_path))
            
            db_name = os.path.basename(self.db_path)
            self.setWindowTitle(f"本地 PDF 文献管理器 - {db_name}")
            
            self.detail_panel.set_database(self.db, self._get_abs_path)
            self.patent_detail_panel.set_database(self.db, self._get_abs_path, self.patent_model)
            self.software_detail_panel.set_database(self.db, self._get_abs_path, self.software_model)
            self._update_scan_button_state()
            self.refresh_table()
            self.statusBar().showMessage(f"已打开: {self.db_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开数据库:\n{e}")
    
    def _new_database(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择文献文件夹（将创建新数据库）",
            self.root_dir
        )
        if not directory:
            return
        
        db_path = os.path.join(directory, 'literature.db')
        
        if os.path.exists(db_path):
            reply = QMessageBox.question(
                self,
                "数据库已存在",
                f"该文件夹下已存在数据库文件：\nliterature.db\n\n请选择：",
                QMessageBox.Open | QMessageBox.Retry | QMessageBox.Cancel,
                QMessageBox.Retry
            )
            
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Open:
                self.db_path = db_path
                self._load_existing_db()
                return
            elif reply == QMessageBox.Retry:
                try:
                    os.remove(db_path)
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"无法删除现有数据库:\n{e}")
                    return
        
        self.db_path = db_path
        self.root_dir = directory
        
        try:
            from db.database import Database
            self.db = Database(self.db_path)
            
            db_name = os.path.basename(self.db_path)
            self.setWindowTitle(f"本地 PDF 文献管理器 - {db_name}")
            
            self.detail_panel.set_database(self.db, self._get_abs_path)
            self.patent_detail_panel.set_database(self.db, self._get_abs_path, self.patent_model)
            self.software_detail_panel.set_database(self.db, self._get_abs_path, self.software_model)
            self._update_scan_button_state()
            self.refresh_table()
            
            print(f"[DEBUG] _new_database: db={self.db is not None}, root_dir={self.root_dir}")
            
            # 直接调用刷新方法来执行扫描
            self._refresh_database()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建数据库:\n{e}")
    
    def _close_database(self):
        reply = QMessageBox.question(
            self,
            "关闭数据库",
            "是否关闭当前数据库？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        self.db = None
        self.db_path = None
        self.root_dir = None
        
        self.paper_model.update_data([])
        self.detail_panel.set_database(None, None)
        self.detail_panel.load_paper(None)
        self._update_scan_button_state()
        self.setWindowTitle("本地 PDF 文献管理器")
        self.statusBar().showMessage("数据库已关闭，请选择打开或新建数据库")
        
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from startup_dialog import StartupDialog
        dialog = StartupDialog()
        if dialog.exec() == QDialog.Accepted and dialog.result_path:
            try:
                from db.database import Database
                self.db_path = dialog.result_path
                self.db = Database(self.db_path)
                self.root_dir = os.path.dirname(os.path.abspath(self.db_path))
                
                db_name = os.path.basename(self.db_path)
                self.setWindowTitle(f"本地 PDF 文献管理器 - {db_name}")
                
                self.detail_panel.set_database(self.db, self._get_abs_path)
                self.patent_detail_panel.set_database(self.db, self._get_abs_path, self.patent_model)
                self.software_detail_panel.set_database(self.db, self._get_abs_path, self.software_model)
                self._update_scan_button_state()
                self.refresh_table()
                self.statusBar().showMessage(f"已打开: {self.db_path}")
                
                # 如果是新建数据库，触发扫描
                print(f"[DEBUG] _close_database: is_new_db={dialog.is_new_db}")
                if dialog.is_new_db:
                    print("[DEBUG] _close_database: triggering scan")
                    self._refresh_database()
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法打开数据库:\n{e}")
                self.paper_model.update_data([])
                self.detail_panel.set_database(None, None)
                self.detail_panel.load_paper(None)
                self._update_scan_button_state()
                self._update_scan_button_state()
        else:
            self.close()
    
    def _delete_selected_items(self):
        """删除当前选中标签页的选中项目"""
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:
            # 论文标签页
            selected = self.paper_table_view.selectionModel().selectedRows()
            if not selected:
                QMessageBox.information(self, "提示", "请先选中要删除的文献")
                return
            
            count = len(selected)
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除选中的 {count} 篇文献吗？\n（仅从数据库删除，不删除PDF文件）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            
            try:
                for idx in selected:
                    row = idx.row()
                    paper = self.paper_model.get_paper_at(row)
                    if paper and paper.get('id'):
                        self.db.delete_paper(paper['id'])
                
                self.refresh_table()
                self.detail_panel.load_paper(None)
                self.statusBar().showMessage(f"已删除 {count} 篇文献")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败:\n{e}")
                
        elif current_tab == 1:
            # 专利标签页
            selected = self.patent_table_view.selectionModel().selectedRows()
            if not selected:
                QMessageBox.information(self, "提示", "请先选中要删除的专利")
                return
            
            count = len(selected)
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除选中的 {count} 项专利吗？\n（仅从数据库删除，不删除PDF文件）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            
            try:
                for idx in selected:
                    row = idx.row()
                    patent = self.patent_model.get_patent_at(row)
                    if patent and patent.get('id'):
                        self.db.delete_patent(patent['id'])
                
                self.refresh_patents()
                self.patent_detail_panel.load_patent(None)
                self.statusBar().showMessage(f"已删除 {count} 项专利")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败:\n{e}")
                
        elif current_tab == 2:
            # 软著标签页
            selected = self.software_table_view.selectionModel().selectedRows()
            if not selected:
                QMessageBox.information(self, "提示", "请先选中要删除的软著")
                return
            
            count = len(selected)
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除选中的 {count} 项软著吗？\n（仅从数据库删除，不删除PDF文件）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            
            try:
                for idx in selected:
                    row = idx.row()
                    software = self.software_model.get_software_at(row)
                    if software and software.get('id'):
                        self.db.delete_software(software['id'])
                
                self.refresh_softwares()
                self.software_detail_panel.load_software(None)
                self.statusBar().showMessage(f"已删除 {count} 项软著")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败:\n{e}")
    
    def _export(self, mode):
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:
            selected = self.paper_table_view.selectionModel().selectedRows()
            if selected:
                rows = [idx.row() for idx in selected]
                papers = self.paper_model.get_selected_papers(rows)
            else:
                papers = self.paper_model._data
            
            if mode in ['bibtex', 'gbt', 'gbt_copy', 'ris'] and not papers:
                QMessageBox.information(self, "提示", "没有可导出的论文")
                return
            
            if mode == 'bibtex':
                from core.bibtex import export_bibtex
                content = export_bibtex(papers)
                path, _ = QFileDialog.getSaveFileName(self, "保存 BibTeX", "references.bib", "BibTeX Files (*.bib)")
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "BibTeX 已导出")
            
            elif mode == 'ris':
                from core.export import export_ris
                content = export_ris(papers)
                path, _ = QFileDialog.getSaveFileName(self, "保存 RIS", "references.ris", "RIS Files (*.ris)")
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "RIS 已导出")
            
            elif mode == 'gbt':
                from core.bibtex import export_gbt7714
                content = export_gbt7714(papers)
                path, _ = QFileDialog.getSaveFileName(self, "保存 GB/T 7714", "references.txt", "Text Files (*.txt)")
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "GB/T 7714 已导出")
            
            elif mode == 'gbt_copy':
                from core.bibtex import export_gbt7714
                content = export_gbt7714(papers)
                QApplication.clipboard().setText(content)
                self.statusBar().showMessage("已复制到剪贴板")
        
        elif current_tab == 1:
            selected = self.patent_table_view.selectionModel().selectedRows()
            if selected:
                rows = [idx.row() for idx in selected]
                patents = self.patent_model.get_selected_patents(rows)
            else:
                patents = self.patent_model._data
            
            if not patents:
                QMessageBox.information(self, "提示", "没有可导出的专利")
                return
            
            if mode == 'gbt':
                from core.export import export_patents_gbt7714
                content = export_patents_gbt7714(patents)
                path, _ = QFileDialog.getSaveFileName(self, "保存 GB/T 7714", "references.txt", "Text Files (*.txt)")
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "GB/T 7714 已导出")
            
            elif mode == 'gbt_copy':
                from core.export import export_patents_gbt7714
                content = export_patents_gbt7714(patents)
                QApplication.clipboard().setText(content)
                self.statusBar().showMessage("已复制到剪贴板")
            
            elif mode == 'patents_csv':
                from core.export import export_patents_csv
                content = export_patents_csv(patents)
                path, _ = QFileDialog.getSaveFileName(self, "保存专利CSV", "patents.csv", "CSV Files (*.csv)")
                if path:
                    with open(path, 'w', encoding='utf-8-sig') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "专利 CSV 已导出")
        
        else:
            selected = self.software_table_view.selectionModel().selectedRows()
            if selected:
                rows = [idx.row() for idx in selected]
                softwares = self.software_model.get_selected_softwares(rows)
            else:
                softwares = self.software_model._data
            
            if not softwares:
                QMessageBox.information(self, "提示", "没有可导出的软著")
                return
            
            if mode == 'gbt':
                from core.export import export_softwares_gbt7714
                content = export_softwares_gbt7714(softwares)
                path, _ = QFileDialog.getSaveFileName(self, "保存 GB/T 7714", "references.txt", "Text Files (*.txt)")
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "GB/T 7714 已导出")
            
            elif mode == 'gbt_copy':
                from core.export import export_softwares_gbt7714
                content = export_softwares_gbt7714(softwares)
                QApplication.clipboard().setText(content)
                self.statusBar().showMessage("已复制到剪贴板")
            
            elif mode == 'softwares_csv':
                from core.export import export_softwares_csv
                content = export_softwares_csv(softwares)
                path, _ = QFileDialog.getSaveFileName(self, "保存软著CSV", "softwares.csv", "CSV Files (*.csv)")
                if path:
                    with open(path, 'w', encoding='utf-8-sig') as f:
                        f.write(content)
                    QMessageBox.information(self, "完成", "软著 CSV 已导出")
    
    def _show_add_paper_dialog(self):
        """显示添加论文对话框"""
        if not self.db:
            QMessageBox.warning(self, "警告", "请先打开或创建数据库")
            return
        
        from ui.add_paper_dialog import AddPaperDialog
        dialog = AddPaperDialog(self, db=self.db, root_dir=self.root_dir)
        dialog.paper_added.connect(self._on_paper_added)
        dialog.exec()
    
    def _on_paper_added(self, paper_data):
        """论文添加成功回调"""
        self.refresh_table()
        self.statusBar().showMessage(f"已添加论文: {paper_data.get('title', '')[:50]}...")
    
    def _show_preferences(self):
        dialog = PreferencesDialog(self)
        dialog.exec()
    
    def _show_literature_settings(self):
        dialog = LiteratureSettingsDialog(self)
        dialog.exec()
    
    def _show_proxy_settings(self):
        dialog = ProxySettingsDialog(self)
        dialog.exec()
    
    def _toggle_dark_mode(self):
        from ui.theme import get_theme
        is_dark = self.dark_mode_action.isChecked()
        QApplication.instance().setStyleSheet(get_theme(is_dark))
        
        settings = self._read_settings()
        settings['dark_mode'] = is_dark
        self._write_settings(settings)
    
    def _read_settings(self):
        config_path = 'preferences.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _write_settings(self, settings):
        with open('preferences.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    
    def _load_theme_setting(self):
        settings = self._read_settings()
        is_dark = settings.get('dark_mode', True)
        self.dark_mode_action.setChecked(is_dark)
        from ui.theme import get_theme
        QApplication.instance().setStyleSheet(get_theme(is_dark))
    
    def _show_context_menu(self, pos, item_type):
        """显示右键菜单"""
        if item_type == 'paper':
            table_view = self.paper_table_view
            model = self.paper_model
        elif item_type == 'patent':
            table_view = self.patent_table_view
            model = self.patent_model
        else:
            table_view = self.software_table_view
            model = self.software_model
        
        index = table_view.indexAt(pos)
        if not index.isValid():
            return
        
        menu = QMenu(self)
        
        open_action = QAction("打开文件", self)
        open_action.triggered.connect(lambda: self._context_open_file(table_view, model, item_type))
        menu.addAction(open_action)
        
        open_folder_action = QAction("打开所在文件夹", self)
        open_folder_action.triggered.connect(lambda: self._context_open_folder(table_view, model, item_type))
        menu.addAction(open_folder_action)
        
        menu.addSeparator()
        
        copy_title_action = QAction("复制标题", self)
        copy_title_action.triggered.connect(lambda: self._context_copy_title(table_view, model, item_type))
        menu.addAction(copy_title_action)
        
        if item_type == 'paper':
            copy_cite_action = QAction("复制引用 (GB/T 7714)", self)
            copy_cite_action.triggered.connect(lambda: self._context_copy_citation(table_view, model))
            menu.addAction(copy_cite_action)
            
            menu.addSeparator()
            
            # 绑定PDF文件
            bind_pdf_action = QAction("绑定PDF文件...", self)
            bind_pdf_action.triggered.connect(lambda: self._context_bind_pdf(table_view, model))
            menu.addAction(bind_pdf_action)
            
            # 重命名PDF文件
            rename_pdf_action = QAction("重命名PDF文件...", self)
            rename_pdf_action.triggered.connect(lambda: self._context_rename_pdf(table_view, model))
            menu.addAction(rename_pdf_action)
            
            menu.addSeparator()
            
            tags_menu = menu.addMenu("标签")
            
            add_tag_action = QAction("添加标签...", self)
            add_tag_action.triggered.connect(lambda: self._context_add_tag(table_view, model))
            tags_menu.addAction(add_tag_action)
            
            manage_tags_action = QAction("管理标签...", self)
            manage_tags_action.triggered.connect(lambda: self._context_manage_tags(table_view, model))
            tags_menu.addAction(manage_tags_action)
            
            tags_menu.addSeparator()
            
            all_tags = self.db.get_all_tags()
            if all_tags:
                for tag in all_tags[:10]:
                    tag_action = QAction(f"  {tag['name']}", self)
                    tag_action.triggered.connect(lambda checked, t=tag: self._context_quick_add_tag(table_view, model, t['id']))
                    tags_menu.addAction(tag_action)
        
        menu.addSeparator()
        
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self._delete_selected_items)
        menu.addAction(delete_action)
        
        menu.exec(table_view.viewport().mapToGlobal(pos))
    
    def _context_open_file(self, table_view, model, item_type):
        """右键菜单：打开文件"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        if item_type == 'paper':
            data = model._data[row]
            rel_path = data.get('rel_path', '')
        elif item_type == 'patent':
            data = model._data[row]
            rel_path = data.get('pdf_path', '')
        else:
            data = model._data[row]
            rel_path = data.get('pdf_path', '')
        
        if rel_path:
            abs_path = self._get_abs_path(rel_path)
            if abs_path and os.path.exists(abs_path):
                os.startfile(abs_path)
    
    def _context_open_folder(self, table_view, model, item_type):
        """右键菜单：打开所在文件夹"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        if item_type == 'paper':
            data = model._data[row]
            rel_path = data.get('rel_path', '')
        elif item_type == 'patent':
            data = model._data[row]
            rel_path = data.get('pdf_path', '')
        else:
            data = model._data[row]
            rel_path = data.get('pdf_path', '')
        
        if rel_path:
            abs_path = self._get_abs_path(rel_path)
            if abs_path and os.path.exists(abs_path):
                folder = os.path.dirname(abs_path)
                os.startfile(folder)
    
    def _context_copy_title(self, table_view, model, item_type):
        """右键菜单：复制标题"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        data = model._data[row]
        
        if item_type == 'paper':
            title = data.get('title', '')
        elif item_type == 'patent':
            title = data.get('patent_name', '')
        else:
            title = data.get('software_name', '')
        
        if title:
            QApplication.clipboard().setText(title)
    
    def _context_copy_citation(self, table_view, model):
        """右键菜单：复制GB/T 7714引用"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        data = model._data[row]
        
        from core.export import format_gbt7714
        citation = format_gbt7714(data)
        QApplication.clipboard().setText(citation)
    
    def _context_bind_pdf(self, table_view, model):
        """右键菜单：绑定PDF文件到论文"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        
        row = indexes[0].row()
        paper = model._data[row]
        paper_id = paper.get('id')
        
        if not paper_id:
            QMessageBox.warning(self, "错误", "无法获取论文ID")
            return
        
        # 检查是否已有PDF
        existing_path = paper.get('file_path') or paper.get('rel_path')
        if existing_path:
            reply = QMessageBox.question(
                self, "确认",
                f"该论文已绑定PDF文件:\n{existing_path}\n\n是否替换为新文件？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        # 选择PDF文件
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, "选择PDF文件", self.root_dir, "PDF Files (*.pdf)"
        )
        
        if not pdf_path:
            return
        
        try:
            import hashlib
            
            # 计算文件信息
            with open(pdf_path, 'rb') as f:
                sha256 = hashlib.sha256(f.read()).hexdigest()
            
            stat = os.stat(pdf_path)
            rel_path = os.path.relpath(pdf_path, self.root_dir)
            filename = os.path.basename(pdf_path)
            
            # 添加或更新PDF记录
            pdf_id = self.db.upsert_pdf_file(
                path=rel_path,
                sha256=sha256,
                size=stat.st_size,
                mtime=stat.st_mtime,
                parse_status='success',
                filename=filename
            )
            
            # 如果已有关联，先删除旧的关联
            if existing_path:
                self.db.unlink_paper_pdfs(paper_id)
            
            # 关联论文和PDF
            self.db.link_paper_pdf(paper_id, pdf_id)
            
            # 刷新表格
            self.refresh_table()
            
            self.statusBar().showMessage(f"已绑定PDF: {filename}")
            QMessageBox.information(self, "成功", f"已将PDF文件绑定到论文:\n{paper.get('title', '')[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to bind PDF: {e}")
            QMessageBox.critical(self, "错误", f"绑定PDF失败: {e}")
    
    def _context_rename_pdf(self, table_view, model):
        """右键菜单：重命名PDF文件"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        
        row = indexes[0].row()
        paper = model._data[row]
        
        # 获取当前PDF路径
        rel_path = paper.get('file_path') or paper.get('rel_path')
        if not rel_path:
            QMessageBox.warning(self, "提示", "该论文没有关联的PDF文件")
            return
        
        abs_path = self._get_abs_path(rel_path)
        if not abs_path or not os.path.exists(abs_path):
            QMessageBox.warning(self, "错误", f"PDF文件不存在:\n{rel_path}")
            return
        
        # 获取当前文件名
        current_filename = os.path.basename(abs_path)
        current_name, ext = os.path.splitext(current_filename)
        
        # 弹出重命名对话框
        new_name, ok = QInputDialog.getText(
            self, "重命名PDF文件",
            "输入新的文件名（不含扩展名）:",
            text=current_name
        )
        
        if not ok or not new_name.strip():
            return
        
        new_name = new_name.strip()
        # 清理非法字符
        new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
        new_filename = f"{new_name}{ext}"
        
        if new_filename == current_filename:
            return
        
        # 构建新路径
        dir_path = os.path.dirname(abs_path)
        new_abs_path = os.path.join(dir_path, new_filename)
        
        # 检查新文件名是否已存在
        if os.path.exists(new_abs_path):
            QMessageBox.warning(self, "错误", f"文件已存在:\n{new_filename}")
            return
        
        try:
            # 重命名文件
            os.rename(abs_path, new_abs_path)
            
            # 更新数据库中的路径
            new_rel_path = os.path.relpath(new_abs_path, self.root_dir)
            self.db.update_pdf_path(rel_path, new_rel_path, new_filename)
            
            # 刷新表格
            self.refresh_table()
            
            self.statusBar().showMessage(f"已重命名: {new_filename}")
            
        except Exception as e:
            logger.error(f"Failed to rename PDF: {e}")
            QMessageBox.critical(self, "错误", f"重命名失败: {e}")
    
    def _context_add_tag(self, table_view, model):
        """右键菜单：添加标签"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        
        tag_name, ok = QInputDialog.getText(self, "添加标签", "输入标签名称:")
        if ok and tag_name.strip():
            tag_id = self.db.get_or_create_tag(tag_name.strip())
            for idx in indexes:
                row = idx.row()
                paper_id = model._data[row].get('id')
                if paper_id:
                    self.db.add_tag_to_paper(paper_id, tag_id)
            self.statusBar().showMessage(f"已添加标签: {tag_name}")
    
    def _context_manage_tags(self, table_view, model):
        """右键菜单：管理标签"""
        indexes = table_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        paper_id = model._data[row].get('id')
        if paper_id:
            dialog = TagManagerDialog(self.db, paper_id, self)
            dialog.exec()
    
    def _context_quick_add_tag(self, table_view, model, tag_id):
        """右键菜单：快速添加标签"""
        indexes = table_view.selectionModel().selectedRows()
        for idx in indexes:
            row = idx.row()
            paper_id = model._data[row].get('id')
            if paper_id:
                self.db.add_tag_to_paper(paper_id, tag_id)
        self.statusBar().showMessage("标签已添加")
    
    def _show_journal_impact_factors(self):
        dialog = JournalImpactDialog(self)
        dialog.exec()
    
    def _show_paper_detail_view(self):
        """显示论文详情对话框"""
        if not self.db:
            QMessageBox.warning(self, "警告", "请先打开数据库")
            return
        
        papers = self.paper_model._data
        if not papers:
            QMessageBox.information(self, "提示", "没有论文数据")
            return
        
        dialog = PaperDetailViewDialog(self.db, papers, self.root_dir, self)
        dialog.exec()
        
        # 刷新表格以显示更新后的数据
        self.refresh_table()
    
    def _show_yearly_stats(self):
        dialog = YearlyStatsDialog(self)
        dialog.exec()
    
    def _show_journal_distribution(self):
        dialog = JournalDistributionDialog(self)
        dialog.exec()
    
    def _show_type_distribution(self):
        self.refresh_patents()
        self.refresh_softwares()
        dialog = TypeDistributionDialog(self)
        dialog.exec()
    
    def _show_fulltext_search(self):
        dialog = FulltextSearchDialog(self.db, self.root_dir, self)
        dialog.exec()
    
    def _build_fulltext_index(self):
        """建立全文索引"""
        import fitz
        
        stats = self.db.get_fulltext_stats()
        unindexed = self.db.get_unindexed_pdfs()
        
        if not unindexed:
            QMessageBox.information(self, "提示", f"全文索引已完成\n已索引: {stats['indexed']}/{stats['total']}")
            return
        
        reply = QMessageBox.question(
            self, "建立全文索引",
            f"当前状态: 已索引 {stats['indexed']}/{stats['total']}\n"
            f"待索引: {len(unindexed)} 个文件\n\n"
            f"是否开始建立索引？（可能需要几分钟）",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        progress = QProgressDialog("正在建立全文索引...", "取消", 0, len(unindexed), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        
        indexed = 0
        failed = 0
        
        for i, pdf in enumerate(unindexed):
            if progress.wasCanceled():
                break
            
            progress.setValue(i)
            progress.setLabelText(f"正在索引: {pdf['filename'] or pdf['path']}")
            QApplication.processEvents()
            
            try:
                abs_path = self._get_abs_path(pdf['path'])
                if abs_path and os.path.exists(abs_path):
                    doc = fitz.open(abs_path)
                    text_parts = []
                    for page in doc:
                        text_parts.append(page.get_text())
                    doc.close()
                    
                    content = '\n'.join(text_parts)
                    if content.strip():
                        self.db.save_fulltext(pdf['id'], content)
                        indexed += 1
            except Exception as e:
                failed += 1
                logger.error(f"索引失败 {pdf['path']}: {e}")
        
        progress.setValue(len(unindexed))
        
        QMessageBox.information(
            self, "索引完成",
            f"成功索引: {indexed} 个文件\n"
            f"失败: {failed} 个文件"
        )
        dialog.exec()


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫描设置")
        self.setMinimumWidth(480)
        self.setMaximumHeight(550)
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        ocr_group = QGroupBox("OCR设置")
        ocr_layout = QFormLayout()
        ocr_layout.setSpacing(6)
        
        # PaddleOCR 提示
        ocr_hint = QLabel('<a href="https://aistudio.baidu.com/paddleocr">申请百度PaddleOCR API</a>')
        ocr_hint.setOpenExternalLinks(True)
        ocr_layout.addRow("", ocr_hint)
        
        self.ocr_url_edit = QLineEdit()
        self.ocr_url_edit.setPlaceholderText("https://xxx.aistudio-app.com/layout-parsing")
        ocr_layout.addRow("OCR URL:", self.ocr_url_edit)
        
        self.ocr_key_edit = QLineEdit()
        self.ocr_key_edit.setPlaceholderText("API Key")
        self.ocr_key_edit.setEchoMode(QLineEdit.Password)
        ocr_layout.addRow("API Key:", self.ocr_key_edit)
        
        self.tesseract_path = QLineEdit()
        self.tesseract_path.setPlaceholderText("留空使用系统PATH")
        ocr_layout.addRow("Tesseract:", self.tesseract_path)
        
        self.ocr_test_btn = QPushButton("测试OCR")
        self.ocr_test_btn.setFixedWidth(80)
        self.ocr_test_btn.clicked.connect(self._test_ocr)
        ocr_layout.addRow("", self.ocr_test_btn)
        
        ocr_group.setLayout(ocr_layout)
        layout.addWidget(ocr_group)
        
        llm_group = QGroupBox("大模型解析")
        llm_layout = QVBoxLayout()
        llm_layout.setSpacing(6)
        
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("解析方式:"))
        self.parse_method_combo = QComboBox()
        self.parse_method_combo.addItems(["程序解析", "大模型解析"])
        self.parse_method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_row.addWidget(self.parse_method_combo)
        method_row.addStretch()
        llm_layout.addLayout(method_row)
        
        self.llm_settings = QWidget()
        llm_form = QFormLayout()
        llm_form.setSpacing(6)
        
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setPlaceholderText("https://api.deepseek.com/chat/completions")
        llm_form.addRow("API URL:", self.api_url_edit)
        
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        llm_form.addRow("API Key:", self.api_key_edit)
        
        self.test_btn = QPushButton("测试")
        self.test_btn.setFixedWidth(60)
        self.test_btn.clicked.connect(self._test_api)
        llm_form.addRow("", self.test_btn)
        
        self.llm_settings.setLayout(llm_form)
        llm_layout.addWidget(self.llm_settings)
        
        llm_group.setLayout(llm_layout)
        layout.addWidget(llm_group)
        
        # 扫描排除文件夹设置
        exclude_group = QGroupBox("扫描排除文件夹")
        exclude_layout = QVBoxLayout()
        exclude_layout.setSpacing(4)
        
        self.exclude_list = QListWidget()
        self.exclude_list.setMaximumHeight(60)
        self.exclude_list.setSelectionMode(QListWidget.SingleSelection)
        exclude_layout.addWidget(self.exclude_list)
        
        exclude_btn_layout = QHBoxLayout()
        self.add_exclude_btn = QPushButton("添加")
        self.add_exclude_btn.setFixedWidth(60)
        self.add_exclude_btn.clicked.connect(self._add_exclude_folder)
        exclude_btn_layout.addWidget(self.add_exclude_btn)
        
        self.remove_exclude_btn = QPushButton("删除")
        self.remove_exclude_btn.setFixedWidth(60)
        self.remove_exclude_btn.clicked.connect(self._remove_exclude_folder)
        exclude_btn_layout.addWidget(self.remove_exclude_btn)
        
        exclude_btn_layout.addStretch()
        exclude_layout.addLayout(exclude_btn_layout)
        
        exclude_group.setLayout(exclude_layout)
        layout.addWidget(exclude_group)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
        self._on_method_changed(0)
    
    def _on_method_changed(self, index):
        self.llm_settings.setVisible(index == 1)
    
    def _add_exclude_folder(self):
        """添加排除文件夹"""
        folder, ok = QInputDialog.getText(self, "添加排除文件夹", 
            "请输入要排除的文件夹名称（相对于根目录）:\n例如: archive 或 backup/old")
        if ok and folder.strip():
            folder = folder.strip().replace('\\', '/')
            # 检查是否已存在
            for i in range(self.exclude_list.count()):
                if self.exclude_list.item(i).text() == folder:
                    QMessageBox.warning(self, "警告", f"文件夹 '{folder}' 已在排除列表中")
                    return
            self.exclude_list.addItem(folder)
    
    def _remove_exclude_folder(self):
        """删除选中的排除文件夹"""
        current_row = self.exclude_list.currentRow()
        if current_row >= 0:
            self.exclude_list.takeItem(current_row)
        else:
            QMessageBox.warning(self, "警告", "请先选择要删除的文件夹")
    
    def _load_settings(self):
        settings = self._read_settings()
        
        ocr_engines = settings.get('ocr_engines', {})
        self.ocr_url_edit.setText(ocr_engines.get('current', {}).get('url', ''))
        self.ocr_key_edit.setText(ocr_engines.get('current', {}).get('key', ''))
        self.tesseract_path.setText(ocr_engines.get('tesseract', {}).get('path', ''))
        
        self.parse_method_combo.setCurrentIndex(1 if settings.get('use_llm', False) else 0)
        self.api_url_edit.setText(settings.get('api_url', ''))
        self.api_key_edit.setText(settings.get('api_key', ''))
        
        # 加载排除文件夹列表
        self.exclude_list.clear()
        excluded_folders = settings.get('excluded_folders', [])
        for folder in excluded_folders:
            self.exclude_list.addItem(folder)
        
        self._on_method_changed(self.parse_method_combo.currentIndex())
    
    def _test_api(self):
        import requests
        
        api_url = self.api_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        
        if not api_url or not api_key:
            QMessageBox.warning(self, "警告", "请填写 API URL 和 Key")
            return
        
        test_prompt = "Hello"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": test_prompt}],
            "max_tokens": 10
        }
        
        try:
            from core.proxy import get_proxies
            proxies = get_proxies()
            response = requests.post(api_url, headers=headers, json=data, timeout=30, proxies=proxies)
            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                QMessageBox.information(self, "成功", f"API 连接成功！\n响应: {content[:100]}")
            else:
                QMessageBox.critical(self, "错误", f"API 调用失败:\n{response.status_code} {response.text[:200]}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接失败:\n{e}")
    
    def _test_ocr(self):
        import requests
        import base64
        
        ocr_url = self.ocr_url_edit.text().strip()
        ocr_key = self.ocr_key_edit.text().strip()
        tesseract_path = self.tesseract_path.text().strip()
        
        tesseract_version = None
        if tesseract_path:
            try:
                result = subprocess.run([tesseract_path, '--version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    tesseract_version = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
            except Exception:
                pass
        else:
            try:
                result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    tesseract_version = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
            except Exception:
                pass
        
        if not ocr_url and not tesseract_version:
            QMessageBox.warning(self, "警告", "请填写OCR URL或正确的Tesseract路径")
            return
        
        if ocr_url and ocr_key:
            self.ocr_test_btn.setText("测试中...")
            self.ocr_test_btn.setEnabled(False)
            QApplication.processEvents()
            
            try:
                headers = {
                    "Authorization": f"token {ocr_key}",
                    "Content-Type": "application/json"
                }
                
                pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test PDF) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n314\n%%EOF"
                file_data = base64.b64encode(pdf_content).decode("ascii")
                
                payload = {
                    "file": file_data,
                    "fileType": 0,
                    "useDocOrientationClassify": False,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
                
                response = requests.post(ocr_url, json=payload, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    msg = f"OCR服务连接成功！\n响应: {str(result)[:200]}"
                    if tesseract_version:
                        msg += f"\nTesseract可用: {tesseract_version}"
                    QMessageBox.information(self, "成功", msg)
                else:
                    QMessageBox.warning(self, "警告", f"OCR服务响应: {response.status_code}\n{response.text[:200]}")
            except requests.exceptions.ConnectionError:
                QMessageBox.critical(self, "错误", "无法连接到OCR服务，请检查URL")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"连接失败: {e}")
            finally:
                self.ocr_test_btn.setText("测试OCR服务")
                self.ocr_test_btn.setEnabled(True)
        elif tesseract_version:
            QMessageBox.information(self, "成功", f"Tesseract可用\n版本: {tesseract_version}")
        else:
            QMessageBox.warning(self, "警告", "Tesseract不可用，请检查路径设置")
    
    def _save_settings(self):
        settings = self._read_settings()
        
        # 收集排除文件夹列表
        excluded_folders = []
        for i in range(self.exclude_list.count()):
            folder = self.exclude_list.item(i).text().strip()
            if folder:
                excluded_folders.append(folder)
        
        settings.update({
            'ocr_engines': {
                'current': {
                    'url': self.ocr_url_edit.text().strip(),
                    'key': self.ocr_key_edit.text().strip()
                },
                'tesseract': {
                    'path': self.tesseract_path.text().strip()
                }
            },
            'use_llm': self.parse_method_combo.currentIndex() == 1,
            'api_url': self.api_url_edit.text().strip(),
            'api_key': self.api_key_edit.text().strip(),
            'excluded_folders': excluded_folders
        })
        self._write_settings(settings)
        
        self.accept()
        QMessageBox.information(self, "完成", "设置已保存")
    
    def _read_settings(self):
        config_path = 'preferences.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'ocr_engines': {
                'current': {'url': '', 'key': ''},
                'tesseract': {'path': ''}
            },
            'use_llm': False,
            'api_url': '', 
            'api_key': '',
            'proxy_enabled': False,
            'proxy_host': '127.0.0.1',
            'proxy_port': '1080',
            'proxy_type': 'SOCKS5',
            'excluded_folders': []
        }
    
    def _write_settings(self, settings):
        with open('preferences.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


class LiteratureSettingsDialog(QDialog):
    """文献设置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文献设置")
        self.setMinimumWidth(400)
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # BibKey生成模式设置
        bibkey_group = QGroupBox("BibKey生成设置")
        bibkey_layout = QFormLayout()
        bibkey_layout.setSpacing(10)
        
        self.bibkey_mode_combo = QComboBox()
        self.bibkey_mode_combo.addItem("简短 (author2024)", "short")
        self.bibkey_mode_combo.addItem("中等 (author2024keyword)", "medium")
        self.bibkey_mode_combo.addItem("完整 (author2024keywordtitle)", "long")
        bibkey_layout.addRow("生成模式:", self.bibkey_mode_combo)
        
        bibkey_hint = QLabel("<small>简短: 仅作者+年份<br>中等: 作者+年份+首个关键词<br>完整: 作者+年份+前3个关键词</small>")
        bibkey_hint.setStyleSheet("color: gray;")
        bibkey_layout.addRow("", bibkey_hint)
        
        bibkey_group.setLayout(bibkey_layout)
        layout.addWidget(bibkey_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _load_settings(self):
        settings = self._read_settings()
        bibkey_mode = settings.get('bibkey_mode', 'medium')
        idx = self.bibkey_mode_combo.findData(bibkey_mode)
        if idx >= 0:
            self.bibkey_mode_combo.setCurrentIndex(idx)
    
    def _save_settings(self):
        settings = self._read_settings()
        bibkey_mode = self.bibkey_mode_combo.currentData()
        settings['bibkey_mode'] = bibkey_mode
        self._write_settings(settings)
        
        # 应用BibKey模式到全局
        from core.extractor import set_bibkey_mode
        set_bibkey_mode(bibkey_mode)
        
        self.accept()
        QMessageBox.information(self, "完成", "设置已保存")
    
    def _read_settings(self):
        config_path = 'preferences.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {'bibkey_mode': 'medium'}
    
    def _write_settings(self, settings):
        with open('preferences.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


class ProxySettingsDialog(QDialog):
    """代理设置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("代理设置")
        self.setMinimumWidth(400)
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # 代理模式选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("代理模式:"))
        self.proxy_enabled = QComboBox()
        self.proxy_enabled.addItems(["不使用代理", "使用代理"])
        self.proxy_enabled.currentIndexChanged.connect(self._on_proxy_changed)
        mode_layout.addWidget(self.proxy_enabled)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # 代理详细设置
        self.proxy_settings = QGroupBox("代理配置")
        proxy_form = QFormLayout()
        proxy_form.setSpacing(10)
        
        self.proxy_host_edit = QLineEdit()
        self.proxy_host_edit.setPlaceholderText("127.0.0.1")
        proxy_form.addRow("代理地址:", self.proxy_host_edit)
        
        self.proxy_port_edit = QLineEdit()
        self.proxy_port_edit.setPlaceholderText("1080")
        self.proxy_port_edit.setFixedWidth(100)
        proxy_form.addRow("代理端口:", self.proxy_port_edit)
        
        self.proxy_type_combo = QComboBox()
        self.proxy_type_combo.addItems(["SOCKS5", "SOCKS4", "HTTP"])
        proxy_form.addRow("代理类型:", self.proxy_type_combo)
        
        self.proxy_test_btn = QPushButton("测试代理连接")
        self.proxy_test_btn.clicked.connect(self._test_proxy)
        proxy_form.addRow("", self.proxy_test_btn)
        
        self.proxy_settings.setLayout(proxy_form)
        layout.addWidget(self.proxy_settings)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _on_proxy_changed(self, index):
        self.proxy_settings.setEnabled(index == 1)
    
    def _load_settings(self):
        settings = self._read_settings()
        self.proxy_enabled.setCurrentIndex(1 if settings.get('proxy_enabled', False) else 0)
        self.proxy_host_edit.setText(settings.get('proxy_host', '127.0.0.1'))
        self.proxy_port_edit.setText(settings.get('proxy_port', '1080'))
        proxy_type = settings.get('proxy_type', 'SOCKS5')
        idx = self.proxy_type_combo.findText(proxy_type)
        if idx >= 0:
            self.proxy_type_combo.setCurrentIndex(idx)
        self._on_proxy_changed(self.proxy_enabled.currentIndex())
    
    def _test_proxy(self):
        """测试代理连接"""
        import requests
        
        host = self.proxy_host_edit.text().strip() or '127.0.0.1'
        port = self.proxy_port_edit.text().strip() or '1080'
        proxy_type = self.proxy_type_combo.currentText().lower()
        
        if proxy_type == 'http':
            proxies = {
                'http': f'http://{host}:{port}',
                'https': f'http://{host}:{port}'
            }
        else:
            proxies = {
                'http': f'{proxy_type}://{host}:{port}',
                'https': f'{proxy_type}://{host}:{port}'
            }
        
        try:
            self.proxy_test_btn.setEnabled(False)
            self.proxy_test_btn.setText("测试中...")
            QApplication.processEvents()
            
            response = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=10)
            if response.status_code == 200:
                ip_info = response.json()
                QMessageBox.information(self, "成功", f"代理连接成功！\n出口IP: {ip_info.get('origin', 'unknown')}")
            else:
                QMessageBox.warning(self, "警告", f"代理响应异常: {response.status_code}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"代理连接失败:\n{e}")
        finally:
            self.proxy_test_btn.setEnabled(True)
            self.proxy_test_btn.setText("测试代理连接")
    
    def _save_settings(self):
        # 读取现有设置（保留其他设置）
        settings = self._read_settings()
        settings.update({
            'proxy_enabled': self.proxy_enabled.currentIndex() == 1,
            'proxy_host': self.proxy_host_edit.text().strip() or '127.0.0.1',
            'proxy_port': self.proxy_port_edit.text().strip() or '1080',
            'proxy_type': self.proxy_type_combo.currentText()
        })
        self._write_settings(settings)
        
        # 应用代理设置到全局
        from core.proxy import apply_proxy_settings
        apply_proxy_settings(settings)
        
        self.accept()
        QMessageBox.information(self, "完成", "代理设置已保存")
    
    def _read_settings(self):
        config_path = 'preferences.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'ocr_engines': {
                'current': {'url': '', 'key': ''},
                'tesseract': {'path': ''}
            },
            'use_llm': False,
            'api_url': '', 
            'api_key': '',
            'proxy_enabled': False,
            'proxy_host': '127.0.0.1',
            'proxy_port': '1080',
            'proxy_type': 'SOCKS5'
        }
    
    def _write_settings(self, settings):
        with open('preferences.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


class JournalImpactDialog(QDialog):
    """期刊影响因子对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("期刊影响因子")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.stats_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["期刊名称", "影响因子", "文献数量"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _load_data(self):
        main_window = self.parent()
        if not main_window or not main_window.db:
            return
        
        try:
            papers = main_window.paper_model._data
            if not papers:
                self.stats_label.setText("没有文献数据")
                return
            
            journal_stats = {}
            for paper in papers:
                venue = (paper.get('venue') or '').strip()
                if venue:
                    if venue not in journal_stats:
                        journal_stats[venue] = {'count': 0, 'if_list': []}
                    journal_stats[venue]['count'] += 1
                    if paper.get('impact_factor'):
                        journal_stats[venue]['if_list'].append(paper['impact_factor'])
            
            sorted_journals = sorted(
                journal_stats.items(),
                key=lambda x: max(x[1]['if_list']) if x[1]['if_list'] else 0,
                reverse=True
            )
            
            self.table.setRowCount(len(sorted_journals))
            for row, (venue, stats) in enumerate(sorted_journals):
                self.table.setItem(row, 0, QTableWidgetItem(venue))
                if stats['if_list']:
                    max_if = max(stats['if_list'])
                    self.table.setItem(row, 1, QTableWidgetItem(f"{max_if:.2f}"))
                else:
                    self.table.setItem(row, 1, QTableWidgetItem("-"))
                self.table.setItem(row, 2, QTableWidgetItem(str(stats['count'])))
            
            total_journals = len(journal_stats)
            total_papers = len(papers)
            if_journals = sum(1 for v in journal_stats.values() if v['if_list'])
            self.stats_label.setText(f"共 {total_journals} 种期刊，{total_papers} 篇文献，其中 {if_journals} 种期刊有影响因子")
            
        except Exception as e:
            self.stats_label.setText(f"加载失败: {e}")


class YearlyStatsDialog(QDialog):
    """年度发文统计对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("年度发文统计")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.stats_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["年份", "论文数", "占比"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.export_btn = QPushButton("导出Markdown")
        self.export_btn.clicked.connect(self._export_markdown)
        btn_layout.addWidget(self.export_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _load_data(self):
        main_window = self.parent()
        if not main_window or not main_window.db:
            return
        
        try:
            papers = main_window.paper_model._data
            if not papers:
                self.stats_label.setText("没有文献数据")
                return
            
            yearly_stats = {}
            for paper in papers:
                year = paper.get('year')
                if year:
                    if year not in yearly_stats:
                        yearly_stats[year] = 0
                    yearly_stats[year] += 1
            
            sorted_years = sorted(yearly_stats.items(), key=lambda x: x[0], reverse=True)
            total = sum(yearly_stats.values())
            
            self.table.setRowCount(len(sorted_years))
            for row, (year, count) in enumerate(sorted_years):
                self.table.setItem(row, 0, QTableWidgetItem(str(year)))
                self.table.setItem(row, 1, QTableWidgetItem(str(count)))
                percentage = count / total * 100 if total > 0 else 0
                self.table.setItem(row, 2, QTableWidgetItem(f"{percentage:.1f}%"))
            
            self.stats_label.setText(f"共 {total} 篇文献，涵盖 {len(sorted_years)} 个年份")
            self.yearly_data = sorted_years
            self.total = total
        
        except Exception as e:
            self.stats_label.setText(f"加载失败: {e}")
    
    def _export_markdown(self):
        if not hasattr(self, 'yearly_data'):
            return
        
        lines = ["# 年度发文统计\n", f"总计: {self.total} 篇文献\n\n", "| 年份 | 论文数 | 占比 |", "|-----|-------|-----|"]
        for year, count in self.yearly_data:
            percentage = count / self.total * 100 if self.total > 0 else 0
            lines.append(f"| {year} | {count} | {percentage:.1f}% |")
        
        content = "\n".join(lines)
        path, _ = QFileDialog.getSaveFileName(self, "保存Markdown", "yearly_stats.md", "Markdown Files (*.md)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            QMessageBox.information(self, "完成", "Markdown 已导出")


class JournalDistributionDialog(QDialog):
    """期刊分布统计对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("期刊分布统计")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.stats_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["期刊名称", "论文数", "占比", "平均IF"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.export_btn = QPushButton("导出Markdown")
        self.export_btn.clicked.connect(self._export_markdown)
        btn_layout.addWidget(self.export_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _load_data(self):
        main_window = self.parent()
        if not main_window or not main_window.db:
            return
        
        try:
            papers = main_window.paper_model._data
            if not papers:
                self.stats_label.setText("没有文献数据")
                return
            
            journal_stats = {}
            for paper in papers:
                venue = (paper.get('venue') or '').strip()
                if venue:
                    if venue not in journal_stats:
                        journal_stats[venue] = {'count': 0, 'if_sum': 0, 'if_count': 0}
                    journal_stats[venue]['count'] += 1
                    if paper.get('impact_factor'):
                        journal_stats[venue]['if_sum'] += paper['impact_factor']
                        journal_stats[venue]['if_count'] += 1
            
            sorted_journals = sorted(journal_stats.items(), key=lambda x: x[1]['count'], reverse=True)
            total = len(papers)
            
            self.table.setRowCount(len(sorted_journals))
            for row, (venue, stats) in enumerate(sorted_journals):
                self.table.setItem(row, 0, QTableWidgetItem(venue))
                self.table.setItem(row, 1, QTableWidgetItem(str(stats['count'])))
                percentage = stats['count'] / total * 100 if total > 0 else 0
                self.table.setItem(row, 2, QTableWidgetItem(f"{percentage:.1f}%"))
                avg_if = stats['if_sum'] / stats['if_count'] if stats['if_count'] > 0 else 0
                self.table.setItem(row, 3, QTableWidgetItem(f"{avg_if:.2f}" if avg_if > 0 else "-"))
            
            self.stats_label.setText(f"共 {len(journal_stats)} 种期刊，{total} 篇文献")
            self.journal_data = sorted_journals
            self.total = total
        
        except Exception as e:
            self.stats_label.setText(f"加载失败: {e}")
    
    def _export_markdown(self):
        if not hasattr(self, 'journal_data'):
            return
        
        lines = ["# 期刊分布统计\n", f"总计: {self.total} 篇文献\n\n", "| 期刊 | 论文数 | 占比 | 平均IF |", "|-----|-------|-----|-----|"]
        for venue, stats in self.journal_data:
            percentage = stats['count'] / self.total * 100 if self.total > 0 else 0
            avg_if = stats['if_sum'] / stats['if_count'] if stats['if_count'] > 0 else 0
            if_str = f"{avg_if:.2f}" if avg_if > 0 else "-"
            lines.append(f"| {venue} | {stats['count']} | {percentage:.1f}% | {if_str} |")
        
        content = "\n".join(lines)
        path, _ = QFileDialog.getSaveFileName(self, "保存Markdown", "journal_distribution.md", "Markdown Files (*.md)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            QMessageBox.information(self, "完成", "Markdown 已导出")


class TypeDistributionDialog(QDialog):
    """类型分布统计对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("类型分布统计")
        self.setMinimumWidth(600)
        self.setMinimumHeight(450)
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.stats_label)
        
        self.chart_frame = QFrame()
        self.chart_frame.setMinimumHeight(320)
        self.chart_frame.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        layout.addWidget(self.chart_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.export_btn = QPushButton("导出Markdown")
        self.export_btn.clicked.connect(self._export_markdown)
        btn_layout.addWidget(self.export_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _load_data(self):
        main_window = self.parent()
        if not main_window or not main_window.db:
            return
        
        try:
            papers = main_window.paper_model._data
            patents = main_window.patent_model._data
            softwares = main_window.software_model._data
            
            self.paper_count = len(papers)
            self.patent_count = len(patents)
            self.software_count = len(softwares)
            
            self.stats_label.setText(f"论文: {self.paper_count} 篇 | 专利: {self.patent_count} 项 | 软著: {self.software_count} 个")
            
            self._draw_pie_chart()
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.stats_label.setText(f"加载失败: {e}")
    
    def _draw_pie_chart(self):
        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            
            types = ['论文', '专利', '软著']
            counts = [self.paper_count, self.patent_count, self.software_count]
            
            if sum(counts) == 0:
                return
            
            fig = Figure(figsize=(5, 4), dpi=100)
            ax = fig.add_subplot(111)
            
            colors = ['#2196F3', '#4CAF50', '#FF9800']
            
            wedges, texts, autotexts = ax.pie(
                counts, 
                labels=types,
                autopct='%1.1f%%',
                colors=colors,
                startangle=90,
                pctdistance=0.6,
                textprops={'fontsize': 11}
            )
            
            for autotext in autotexts:
                autotext.set_fontsize(10)
                autotext.set_color('white')
                autotext.set_weight('bold')
            
            ax.set_title('科研成果类型分布', fontsize=14, fontweight='bold')
            
            canvas = FigureCanvas(fig)
            canvas.setParent(self.chart_frame)
            
            layout = QVBoxLayout(self.chart_frame)
            layout.addWidget(canvas)
            layout.setContentsMargins(0, 0, 0, 0)
        
        except Exception as e:
            print(f"Chart drawing error: {e}")
    
    def _export_markdown(self):
        total = self.paper_count + self.patent_count + self.software_count
        
        lines = ["# 类型分布统计\n\n"]
        if total > 0:
            lines.append(f"- 论文: {self.paper_count} 篇 ({self.paper_count/total*100:.1f}%)")
            lines.append(f"- 专利: {self.patent_count} 项 ({self.patent_count/total*100:.1f}%)")
            lines.append(f"- 软著: {self.software_count} 个 ({self.software_count/total*100:.1f}%)")
            lines.append(f"\n总计: {total}")
        else:
            lines.append("- 论文: 0 篇")
            lines.append("- 专利: 0 项")
            lines.append("- 软著: 0 个")
        
        content = "\n".join(lines)
        path, _ = QFileDialog.getSaveFileName(self, "保存Markdown", "type_distribution.md", "Markdown Files (*.md)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            QMessageBox.information(self, "完成", "Markdown 已导出")


class FulltextSearchDialog(QDialog):
    """全文搜索对话框"""
    def __init__(self, db, root_dir, parent=None):
        super().__init__(parent)
        self.db = db
        self.root_dir = root_dir
        self.setWindowTitle("全文搜索")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        self._setup_ui()
        self._update_stats()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索关键词...")
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input)
        
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._do_search)
        search_layout.addWidget(self.search_btn)
        
        layout.addLayout(search_layout)
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.stats_label)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["标题", "作者", "年份", "匹配内容"])
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.doubleClicked.connect(self._open_file)
        self.result_table.setColumnWidth(0, 250)
        self.result_table.setColumnWidth(1, 150)
        self.result_table.setColumnWidth(2, 50)
        layout.addWidget(self.result_table)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _update_stats(self):
        stats = self.db.get_fulltext_stats()
        self.stats_label.setText(f"全文索引: {stats['indexed']}/{stats['total']} 个文件")
    
    def _do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            return
        
        self.search_btn.setText("搜索中...")
        self.search_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            results = self.db.search_fulltext(keyword)
            self.result_table.setRowCount(len(results))
            
            for i, r in enumerate(results):
                title_item = QTableWidgetItem(r.get('title') or r.get('filename') or '')
                self.result_table.setItem(i, 0, title_item)
                
                authors_item = QTableWidgetItem(r.get('authors') or '')
                self.result_table.setItem(i, 1, authors_item)
                
                year_item = QTableWidgetItem(str(r.get('year') or ''))
                self.result_table.setItem(i, 2, year_item)
                
                content = r.get('content') or ''
                match_pos = r.get('match_pos', 0)
                if match_pos > 0:
                    start = max(0, match_pos - 50)
                    end = min(len(content), match_pos + len(keyword) + 50)
                    snippet = '...' + content[start:end].replace('\n', ' ') + '...'
                else:
                    idx = content.lower().find(keyword.lower())
                    if idx >= 0:
                        start = max(0, idx - 50)
                        end = min(len(content), idx + len(keyword) + 50)
                        snippet = '...' + content[start:end].replace('\n', ' ') + '...'
                    else:
                        snippet = content[:100].replace('\n', ' ') + '...'
                
                snippet_item = QTableWidgetItem(snippet)
                self.result_table.setItem(i, 3, snippet_item)
                
                self.result_table.item(i, 0).setData(Qt.UserRole, r.get('rel_path'))
            
            self.stats_label.setText(f"找到 {len(results)} 个结果")
        finally:
            self.search_btn.setText("搜索")
            self.search_btn.setEnabled(True)
    
    def _open_file(self, index):
        row = index.row()
        rel_path = self.result_table.item(row, 0).data(Qt.UserRole)
        if rel_path:
            abs_path = os.path.join(self.root_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
            if os.path.exists(abs_path):
                os.startfile(abs_path)


class TagManagerDialog(QDialog):
    """标签管理对话框"""
    def __init__(self, db, paper_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.paper_id = paper_id
        self.setWindowTitle("管理标签")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self._setup_ui()
        self._load_tags()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        layout.addWidget(QLabel("当前标签:"))
        
        self.current_tags_list = QListWidget()
        self.current_tags_list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.current_tags_list)
        
        btn_layout1 = QHBoxLayout()
        self.remove_btn = QPushButton("移除选中标签")
        self.remove_btn.clicked.connect(self._remove_tags)
        btn_layout1.addWidget(self.remove_btn)
        btn_layout1.addStretch()
        layout.addLayout(btn_layout1)
        
        layout.addWidget(QLabel("添加新标签:"))
        
        add_layout = QHBoxLayout()
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setPlaceholderText("输入标签名称...")
        self.new_tag_input.returnPressed.connect(self._add_tag)
        add_layout.addWidget(self.new_tag_input)
        
        self.add_btn = QPushButton("添加")
        self.add_btn.clicked.connect(self._add_tag)
        add_layout.addWidget(self.add_btn)
        layout.addLayout(add_layout)
        
        layout.addWidget(QLabel("所有标签:"))
        
        self.all_tags_list = QListWidget()
        self.all_tags_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.all_tags_list.itemDoubleClicked.connect(self._add_existing_tag)
        layout.addWidget(self.all_tags_list)
        
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout2.addWidget(self.close_btn)
        layout.addLayout(btn_layout2)
        
        self.setLayout(layout)
    
    def _load_tags(self):
        self.current_tags_list.clear()
        current_tags = self.db.get_paper_tags(self.paper_id)
        for tag in current_tags:
            item = QListWidgetItem(tag['name'])
            item.setData(Qt.UserRole, tag['id'])
            self.current_tags_list.addItem(item)
        
        self.all_tags_list.clear()
        all_tags = self.db.get_all_tags()
        current_tag_ids = {t['id'] for t in current_tags}
        for tag in all_tags:
            if tag['id'] not in current_tag_ids:
                item = QListWidgetItem(tag['name'])
                item.setData(Qt.UserRole, tag['id'])
                self.all_tags_list.addItem(item)
    
    def _add_tag(self):
        tag_name = self.new_tag_input.text().strip()
        if tag_name:
            tag_id = self.db.get_or_create_tag(tag_name)
            self.db.add_tag_to_paper(self.paper_id, tag_id)
            self.new_tag_input.clear()
            self._load_tags()
    
    def _add_existing_tag(self, item):
        tag_id = item.data(Qt.UserRole)
        self.db.add_tag_to_paper(self.paper_id, tag_id)
        self._load_tags()
    
    def _remove_tags(self):
        for item in self.current_tags_list.selectedItems():
            tag_id = item.data(Qt.UserRole)
            self.db.remove_tag_from_paper(self.paper_id, tag_id)
        self._load_tags()


class PaperDetailViewDialog(QDialog):
    """论文详情查看对话框"""
    def __init__(self, db, papers, root_dir, parent=None):
        super().__init__(parent)
        self.db = db
        self.papers = papers
        self.root_dir = root_dir
        self.current_paper = None
        self.setWindowTitle("论文详情")
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)
        self._setup_ui()
        self._load_papers()
        
        # Ctrl+S 保存快捷键
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_current)
    
    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        
        # 左侧：论文列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("论文列表:"))
        
        self.paper_list = QListWidget()
        self.paper_list.setMinimumWidth(300)
        self.paper_list.currentRowChanged.connect(self._on_paper_selected)
        self.paper_list.itemDoubleClicked.connect(self._open_paper_pdf)
        left_layout.addWidget(self.paper_list)
        
        layout.addWidget(left_panel)
        
        # 右侧：详情面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # 摘要区域
        abstract_group = QGroupBox("摘要")
        abstract_layout = QVBoxLayout()
        
        abstract_btn_layout = QHBoxLayout()
        self.extract_abstract_btn = QPushButton("从PDF提取")
        self.extract_abstract_btn.clicked.connect(self._extract_abstract)
        abstract_btn_layout.addWidget(self.extract_abstract_btn)
        abstract_btn_layout.addStretch()
        abstract_layout.addLayout(abstract_btn_layout)
        
        self.abstract_edit = QTextEdit()
        self.abstract_edit.setPlaceholderText("论文摘要（可从PDF提取或手动编辑）")
        self.abstract_edit.setMinimumHeight(150)
        abstract_layout.addWidget(self.abstract_edit)
        
        abstract_group.setLayout(abstract_layout)
        right_layout.addWidget(abstract_group)
        
        # 笔记区域
        notes_group = QGroupBox("笔记")
        notes_layout = QVBoxLayout()
        
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("在此添加您的笔记...")
        self.notes_edit.setMinimumHeight(150)
        notes_layout.addWidget(self.notes_edit)
        
        notes_group.setLayout(notes_layout)
        right_layout.addWidget(notes_group)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存 (Ctrl+S)")
        self.save_btn.clicked.connect(self._save_current)
        btn_layout.addWidget(self.save_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        right_layout.addLayout(btn_layout)
        
        # 状态标签
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        right_layout.addWidget(self.status_label)
        
        layout.addWidget(right_panel, 1)
        self.setLayout(layout)
    
    def _load_papers(self):
        self.paper_list.clear()
        for i, paper in enumerate(self.papers):
            title = paper.get('title') or '(无标题)'
            authors = paper.get('authors') or '(无作者)'
            # 截断过长的标题和作者
            if len(title) > 50:
                title = title[:47] + '...'
            if len(authors) > 30:
                authors = authors[:27] + '...'
            
            item_text = f"{i+1}. {title}\n   {authors}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, i)
            # 增加行高，使不同论文之间更容易区分
            from PySide6.QtCore import QSize
            item.setSizeHint(QSize(0, 55))
            self.paper_list.addItem(item)
        
        if self.papers:
            self.paper_list.setCurrentRow(0)
    
    def _on_paper_selected(self, row):
        if row < 0 or row >= len(self.papers):
            return
        
        self.current_paper = self.papers[row]
        
        # 加载摘要和笔记
        self.abstract_edit.setPlainText(self.current_paper.get('abstract') or '')
        self.notes_edit.setPlainText(self.current_paper.get('notes') or '')
        
        self.status_label.setText(f"当前: {self.current_paper.get('title', '')[:50]}")
    
    def _open_paper_pdf(self, item):
        """双击打开论文PDF"""
        row = item.data(Qt.UserRole)
        if row is None or row < 0 or row >= len(self.papers):
            return
        
        paper = self.papers[row]
        file_path = paper.get('file_path')
        if not file_path:
            self.status_label.setText("无PDF文件")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        abs_path = os.path.join(self.root_dir, file_path) if not os.path.isabs(file_path) else file_path
        if os.path.exists(abs_path):
            try:
                os.startfile(abs_path)
            except Exception as e:
                self.status_label.setText(f"打开失败: {e}")
                self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setText(f"文件不存在: {abs_path}")
            self.status_label.setStyleSheet("color: red;")
    
    def _extract_abstract(self):
        if not self.current_paper:
            return
        
        file_path = self.current_paper.get('file_path')
        if not file_path:
            self.status_label.setText("无PDF文件")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        abs_path = os.path.join(self.root_dir, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.exists(abs_path):
            self.status_label.setText(f"文件不存在: {abs_path}")
            self.status_label.setStyleSheet("color: red;")
            return
        
        self.extract_abstract_btn.setEnabled(False)
        self.extract_abstract_btn.setText("提取中...")
        QApplication.processEvents()
        
        try:
            import fitz
            doc = fitz.open(abs_path)
            
            # 尝试从前几页提取摘要
            abstract = None
            full_text = ""
            
            for page_num in range(min(3, len(doc))):
                page = doc[page_num]
                text = page.get_text()
                full_text += text + "\n"
            
            doc.close()
            
            # 尝试找到Abstract部分
            import re
            
            # 改进的摘要提取模式
            abstract_patterns = [
                # Elsevier style: a b s t r a c t (with spaces)
                r'(?i)a\s*b\s*s\s*t\s*r\s*a\s*c\s*t\s*\n(.*?)(?=\n\s*(?:\d+\.\s*Introduction|1\.\s*Introduction))',
                # IEEE style with Manuscript received ending
                r'(?i)Abstract[\u2014\u2013\-:;\s]+(.*?)(?=\n\s*(?:Manuscript\s*received|Note\s*to\s*Practitioners|Index\s*Terms|Keywords?|Key\s*Words?|I\.\s*INTRODUCTION|1\s*[\.\)]\s*Introduction))',
                # Standard: Abstract followed by text
                r'(?i)Abstract[:\s]*\n(.*?)(?=\n\s*(?:Keywords?|Key\s*Words?|Introduction|1\s*[\.\)]|I\s*[\.\)]|Index\s*Terms?|CCS))',
                # Abstract with double newline ending
                r'(?i)Abstract[\u2014\u2013\-:;\s]+(.*?)(?=\n\s*\n\s*(?:I\.|1\.|Keywords|Index|Note\s*to|Manuscript))',
                # Chinese: 摘要
                r'(?:\u6458\s*\u8981|\u6458\u8981)[\uff1a:\s]*(.*?)(?=\n\s*(?:\u5173\u952e\u8bcd|\u5173\s*\u952e\s*\u8bcd|\u5f15\u8a00|1\s*[\.\)]|\u4e00\u3001|0\s*\u5f15\u8a00))',
                r'(?:\u6458\s*\u8981|\u6458\u8981)[\uff1a:\s]*(.*?)(?=\n\s*\n)',
                # Fallback: Abstract to double newline
                r'(?i)Abstract[\u2014\u2013\-:;\s]+(.*?)(?=\n\n)',
            ]
            
            for pattern in abstract_patterns:
                match = re.search(pattern, full_text, re.DOTALL | re.MULTILINE)
                if match:
                    abstract = match.group(1).strip()
                    # 清理多余空白
                    abstract = re.sub(r'\s+', ' ', abstract)
                    # 移除开头的特殊字符
                    abstract = re.sub(r'^[\u2014\u2013\-\s]+', '', abstract)
                    if 50 < len(abstract) < 3000:  # 确保摘要有足够内容且不过长
                        break
                    else:
                        abstract = None
            
            if abstract:
                self.abstract_edit.setPlainText(abstract)
                self.status_label.setText(f"已提取摘要 ({len(abstract)} 字符)")
                self.status_label.setStyleSheet("color: green;")
            else:
                # 如果没找到明确的摘要，取前500字符
                preview = full_text[:500].strip()
                self.abstract_edit.setPlainText(preview)
                self.status_label.setText("未找到明确摘要，已提取前500字符")
                self.status_label.setStyleSheet("color: orange;")
        
        except Exception as e:
            self.status_label.setText(f"提取失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.extract_abstract_btn.setEnabled(True)
            self.extract_abstract_btn.setText("从PDF提取")
    
    def _save_current(self):
        if not self.current_paper or not self.db:
            return
        
        try:
            abstract = self.abstract_edit.toPlainText().strip()
            notes = self.notes_edit.toPlainText().strip()
            
            self.db.update_paper(
                self.current_paper['id'],
                abstract=abstract or None,
                notes=notes or None
            )
            
            # 更新本地数据
            self.current_paper['abstract'] = abstract
            self.current_paper['notes'] = notes
            
            self.status_label.setText("已保存")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            self.status_label.setText(f"保存失败: {e}")
            self.status_label.setStyleSheet("color: red;")
