from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                                QTextEdit, QLabel, QPushButton, QComboBox, 
                                QHBoxLayout, QMessageBox, QGroupBox, QListWidget,
                                QListWidgetItem, QDialog, QInputDialog, QDialogButtonBox,
                                QFileIconProvider, QStyle, QApplication)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QIcon, QPixmap
from typing import Dict
import os
import logging

logger = logging.getLogger(__name__)

class AuthorsDialog(QDialog):
    def __init__(self, parent=None, authors_text=""):
        super().__init__(parent)
        self.setWindowTitle("调整作者顺序")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.authors = []
        self._init_ui(authors_text)
    
    def _init_ui(self, authors_text):
        layout = QVBoxLayout(self)
        
        hint = QLabel("提示：双击作者可编辑，拖拽可调整顺序")
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)
        
        self.authors_list = QListWidget()
        self.authors_list.setSelectionMode(QListWidget.SingleSelection)
        self.authors_list.setDragDropMode(QListWidget.InternalMove)
        self.authors_list.setDefaultDropAction(Qt.MoveAction)
        self.authors_list.itemDoubleClicked.connect(self._edit_author)
        layout.addWidget(self.authors_list)
        
        if authors_text:
            authors = [a.strip() for a in authors_text.split(';') if a.strip()]
            for author in authors:
                item = QListWidgetItem(author)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.authors_list.addItem(item)
        
        btn_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("+ 添加")
        self.add_btn.clicked.connect(self._add_author)
        btn_layout.addWidget(self.add_btn)
        
        self.up_btn = QPushButton("上移")
        self.up_btn.clicked.connect(self._move_up)
        btn_layout.addWidget(self.up_btn)
        
        self.down_btn = QPushButton("下移")
        self.down_btn.clicked.connect(self._move_down)
        btn_layout.addWidget(self.down_btn)
        
        self.edit_btn = QPushButton("编辑")
        self.edit_btn.clicked.connect(self._edit_selected)
        btn_layout.addWidget(self.edit_btn)
        
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._delete)
        btn_layout.addWidget(self.delete_btn)
        
        layout.addLayout(btn_layout)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
    
    def _move_up(self):
        current_row = self.authors_list.currentRow()
        if current_row > 0:
            item = self.authors_list.takeItem(current_row)
            self.authors_list.insertItem(current_row - 1, item)
            self.authors_list.setCurrentRow(current_row - 1)
    
    def _move_down(self):
        current_row = self.authors_list.currentRow()
        if current_row < self.authors_list.count() - 1:
            item = self.authors_list.takeItem(current_row)
            self.authors_list.insertItem(current_row + 1, item)
            self.authors_list.setCurrentRow(current_row + 1)
    
    def _edit_author(self, item):
        new_text, ok = QInputDialog.getText(self, "编辑作者", "请输入新的作者姓名:", 
                                            text=item.text())
        if ok and new_text.strip():
            item.setText(new_text.strip())
    
    def _edit_selected(self):
        current_row = self.authors_list.currentRow()
        if current_row >= 0:
            self._edit_author(self.authors_list.currentItem())
    
    def _add_author(self):
        new_text, ok = QInputDialog.getText(self, "添加作者", "请输入新作者姓名:")
        if ok and new_text.strip():
            item = QListWidgetItem(new_text.strip())
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.authors_list.addItem(item)
            self.authors_list.setCurrentRow(self.authors_list.count() - 1)
    
    def _delete(self):
        current_row = self.authors_list.currentRow()
        if current_row >= 0:
            self.authors_list.takeItem(current_row)
    
    def _save(self):
        self.authors = []
        for i in range(self.authors_list.count()):
            author = self.authors_list.item(i).text().strip()
            if author:
                self.authors.append(author)
        self.accept()
    
    def get_authors_text(self):
        return '; '.join(self.authors)


class OCRThread(QThread):
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, pdf_path: str):
        super().__init__()
        self.pdf_path = pdf_path
    
    def run(self):
        try:
            from core.ocr import ocr_pdf_page
            result = ocr_pdf_page(self.pdf_path, page_num=0)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DetailPanel(QWidget):
    data_changed = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_paper = None
        self.db = None
        self.parsed_data = None
        self.ocr_in_progress = False
        self.get_abs_path = None
        self.selected_papers = []  # 选中的论文列表
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        file_info = QHBoxLayout()
        
        self.open_btn = QPushButton()
        self.open_btn.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.open_btn.setToolTip("打开PDF")
        self.open_btn.setFixedSize(28, 28)
        self.open_btn.clicked.connect(self._open_pdf)
        file_info.addWidget(self.open_btn)
        
        self.filepath_label = QLabel("")
        self.filepath_label.setStyleSheet("font-size: 12px; color: #333;")
        self.filepath_label.setWordWrap(True)
        self.filepath_label.setMaximumWidth(600)
        file_info.addWidget(self.filepath_label, 1)
        
        layout.addLayout(file_info)
        
        info_group = QGroupBox("文献信息")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        form = QFormLayout()
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("论文标题")
        self.title_edit.setMinimumHeight(24)
        form.addRow("标题:", self.title_edit)
        
        authors_layout = QHBoxLayout()
        authors_layout.setSpacing(4)
        self.authors_edit = QLineEdit()
        self.authors_edit.setPlaceholderText("作者1; 作者2; ...")
        self.authors_edit.setMinimumHeight(24)
        authors_layout.addWidget(self.authors_edit, 1)
        
        self.authors_btn = QPushButton("顺序")
        self.authors_btn.setFixedWidth(50)
        self.authors_btn.setMinimumHeight(24)
        self.authors_btn.clicked.connect(self._open_authors_dialog)
        authors_layout.addWidget(self.authors_btn)
        
        form.addRow("作者:", authors_layout)
        
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("年份")
        self.year_edit.setFixedWidth(60)
        self.year_edit.setMinimumHeight(24)
        row2.addWidget(self.year_edit)
        
        self.venue_edit = QLineEdit()
        self.venue_edit.setPlaceholderText("期刊/会议")
        self.venue_edit.setMinimumHeight(24)
        row2.addWidget(self.venue_edit, 1)
        
        self.impact_factor_edit = QLineEdit()
        self.impact_factor_edit.setPlaceholderText("IF")
        self.impact_factor_edit.setFixedWidth(60)
        self.impact_factor_edit.setMinimumHeight(24)
        row2.addWidget(self.impact_factor_edit)
        
        self.if_btn = QPushButton("查询")
        self.if_btn.setFixedWidth(50)
        self.if_btn.setMinimumHeight(24)
        self.if_btn.clicked.connect(self._query_impact_factor)
        row2.addWidget(self.if_btn)
        
        form.addRow("年份/期刊/IF:", row2)
        
        doi_layout = QHBoxLayout()
        doi_layout.setSpacing(4)
        self.doi_edit = QLineEdit()
        self.doi_edit.setPlaceholderText("DOI")
        self.doi_edit.setMinimumHeight(24)
        doi_layout.addWidget(self.doi_edit, 1)
        
        self.doi_query_btn = QPushButton("查询")
        self.doi_query_btn.setFixedWidth(50)
        self.doi_query_btn.setMinimumHeight(24)
        self.doi_query_btn.clicked.connect(self._query_by_doi)
        doi_layout.addWidget(self.doi_query_btn)
        
        form.addRow("DOI:", doi_layout)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("URL")
        self.url_edit.setMinimumHeight(24)
        form.addRow("URL:", self.url_edit)
        
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(8)
        self.volume_edit = QLineEdit()
        self.volume_edit.setPlaceholderText("卷")
        self.volume_edit.setFixedWidth(60)
        self.volume_edit.setMinimumHeight(24)
        volume_layout.addWidget(self.volume_edit)
        
        self.issue_edit = QLineEdit()
        self.issue_edit.setPlaceholderText("期")
        self.issue_edit.setFixedWidth(40)
        self.issue_edit.setMinimumHeight(24)
        volume_layout.addWidget(self.issue_edit)
        
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("页码")
        self.pages_edit.setMinimumHeight(24)
        volume_layout.addWidget(self.pages_edit, 1)
        
        form.addRow("卷/期/页:", volume_layout)
        
        entry_layout = QHBoxLayout()
        entry_layout.setSpacing(8)
        self.entry_type_combo = QComboBox()
        self.entry_type_combo.addItems([
            'article',       # 期刊论文
            'inproceedings', # 会议论文
            'book',          # 专著
            'proceedings',   # 会议录
            'phdthesis',     # 博士学位论文
            'mastersthesis', # 硕士学位论文
            'misc',          # 其他
            'techreport',    # 技术报告
            'unpublished',   # 未发表
            'patent'         # 专利
        ])
        self.entry_type_combo.setMinimumHeight(24)
        self.entry_type_combo.setToolTip("BibTeX条目类型")
        entry_layout.addWidget(self.entry_type_combo)
        
        self.bibtex_key_edit = QLineEdit()
        self.bibtex_key_edit.setPlaceholderText("BibTeX Key")
        self.bibtex_key_edit.setMinimumHeight(24)
        entry_layout.addWidget(self.bibtex_key_edit, 1)
        
        self.bibtex_key_btn = QPushButton("重新生成")
        self.bibtex_key_btn.setFixedWidth(70)
        self.bibtex_key_btn.setMinimumHeight(24)
        self.bibtex_key_btn.clicked.connect(self._regenerate_bibtex_key)
        entry_layout.addWidget(self.bibtex_key_btn)
        
        form.addRow("类型/BibTeX Key:", entry_layout)
        
        # 标签行
        tag_layout = QHBoxLayout()
        tag_layout.setSpacing(4)
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("标签1; 标签2; ...")
        self.tag_edit.setMinimumHeight(24)
        tag_layout.addWidget(self.tag_edit, 1)
        form.addRow("标签:", tag_layout)
        
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(15)
        self.confidence_edit = QLineEdit()
        self.confidence_edit.setPlaceholderText("置信度")
        self.confidence_edit.setReadOnly(True)
        self.confidence_edit.setFixedWidth(80)
        self.confidence_edit.setMinimumHeight(24)
        meta_layout.addWidget(self.confidence_edit)
        
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("来源")
        self.source_edit.setReadOnly(True)
        self.source_edit.setMinimumHeight(24)
        meta_layout.addWidget(self.source_edit, 1)
        
        self.auto_tag_btn = QPushButton("自动标签")
        self.auto_tag_btn.setFixedWidth(70)
        self.auto_tag_btn.setMinimumHeight(24)
        self.auto_tag_btn.setToolTip("自动添加标签：期刊/会议、中文/英文")
        self.auto_tag_btn.clicked.connect(self._auto_tag_selected)
        meta_layout.addWidget(self.auto_tag_btn)
        
        form.addRow("元数据:", meta_layout)
        
        info_group.setLayout(form)
        layout.addWidget(info_group)
        
        ocr_group = QGroupBox("OCR / 文本解析")
        ocr_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        ocr_layout = QVBoxLayout()
        ocr_layout.setSpacing(6)
        
        self.ocr_result = QTextEdit()
        self.ocr_result.setPlaceholderText("点击\"触发OCR\"自动识别，或手动粘贴文本后点击\"解析文本\"")
        self.ocr_result.setMaximumHeight(100)
        ocr_layout.addWidget(self.ocr_result)
        
        ocr_btn_layout = QHBoxLayout()
        ocr_btn_layout.setSpacing(8)
        self.ocr_btn = QPushButton("触发OCR")
        self.ocr_btn.setMinimumHeight(24)
        self.ocr_btn.clicked.connect(self._trigger_ocr)
        ocr_btn_layout.addWidget(self.ocr_btn)
        
        self.parse_btn = QPushButton("解析并应用")
        self.parse_btn.setMinimumHeight(24)
        self.parse_btn.clicked.connect(self._parse_manual_text)
        self.parse_btn.setToolTip("解析文本并自动应用到表单字段")
        ocr_btn_layout.addWidget(self.parse_btn)
        
        ocr_btn_layout.addStretch(1)
        ocr_layout.addLayout(ocr_btn_layout)
        ocr_group.setLayout(ocr_layout)
        layout.addWidget(ocr_group)
        
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        self.save_btn = QPushButton("保存")
        self.save_btn.setMinimumHeight(28)
        self.save_btn.clicked.connect(self._save_changes)
        action_layout.addWidget(self.save_btn)
        
        self.doi_btn = QPushButton("查找DOI")
        self.doi_btn.setMinimumHeight(28)
        self.doi_btn.clicked.connect(self._resolve_doi)
        action_layout.addWidget(self.doi_btn)
        
        self.if_update_btn = QPushButton("更新IF")
        self.if_update_btn.setMinimumHeight(28)
        self.if_update_btn.setToolTip("更新选中文献的影响因子")
        self.if_update_btn.clicked.connect(self._update_selected_impact_factors)
        action_layout.addWidget(self.if_update_btn)
        
        self.doi_update_all_btn = QPushButton("按DOI更新")
        self.doi_update_all_btn.setMinimumHeight(28)
        self.doi_update_all_btn.setToolTip("通过DOI更新选中文献的信息")
        self.doi_update_all_btn.clicked.connect(self._update_selected_by_doi)
        action_layout.addWidget(self.doi_update_all_btn)
        
        self.bibkey_update_btn = QPushButton("更新BibKey")
        self.bibkey_update_btn.setMinimumHeight(28)
        self.bibkey_update_btn.setToolTip("重新生成选中文献的BibTeX Key")
        self.bibkey_update_btn.clicked.connect(self._update_selected_bibkeys)
        action_layout.addWidget(self.bibkey_update_btn)
        
        action_layout.addStretch(1)
        layout.addLayout(action_layout)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.status_label)
    
    def set_database(self, db, get_abs_path=None):
        self.db = db
        self.get_abs_path = get_abs_path
    
    def set_selected_papers(self, papers: list):
        """设置选中的论文列表"""
        self.selected_papers = papers or []
    
    def load_paper(self, paper: Dict):
        self.current_paper = paper
        if not paper:
            self._clear_fields()
            return
        
        self.filepath_label.setText(paper.get('file_path', '') or '')
        
        self.title_edit.setText(paper.get('title', '') or '')
        self.authors_edit.setText(paper.get('authors', '') or '')
        self.year_edit.setText(str(paper.get('year', '')) or '')
        self.venue_edit.setText(paper.get('venue', '') or '')
        self.doi_edit.setText(paper.get('doi', '') or '')
        self.url_edit.setText(paper.get('url', '') or '')
        self.volume_edit.setText(paper.get('volume', '') or '')
        self.issue_edit.setText(paper.get('issue', '') or '')
        self.pages_edit.setText(paper.get('pages', '') or '')
        self.entry_type_combo.setCurrentText(paper.get('entry_type', 'article'))
        
        self.bibtex_key_edit.setText(paper.get('bibtex_key', '') or '')
        self.confidence_edit.setText(f"{paper.get('confidence', 0):.1f}")
        
        impact_factor = paper.get('impact_factor')
        if impact_factor:
            self.impact_factor_edit.setText(f"{impact_factor:.1f}")
        else:
            self.impact_factor_edit.clear()
        
        source_map = {
            'pdf': 'PDF元数据',
            'doi_lookup': 'DOI查询',
            'auto': '自动匹配',
            'review': '待审核',
            'none': '无'
        }
        self.source_edit.setText(source_map.get(paper.get('source', ''), paper.get('source', '')))
        
        # 加载标签
        if self.db:
            tags = self.db.get_paper_tags(paper['id'])
            self.tag_edit.setText('; '.join([t['name'] for t in tags]))
        else:
            self.tag_edit.clear()
        
        self.ocr_result.clear()
        self.parsed_data = None
        self.ocr_in_progress = False
    
    def _clear_fields(self):
        self.filepath_label.clear()
        for edit in [self.title_edit, self.authors_edit, self.year_edit, 
                     self.venue_edit, self.doi_edit, self.url_edit,
                     self.volume_edit, self.issue_edit, self.pages_edit,
                     self.bibtex_key_edit, self.confidence_edit, self.source_edit,
                     self.impact_factor_edit, self.tag_edit]:
            edit.clear()
        self.entry_type_combo.setCurrentIndex(0)
        self.ocr_result.clear()
        self.parsed_data = None
    
    def _open_authors_dialog(self):
        authors_text = self.authors_edit.text()
        dialog = AuthorsDialog(self, authors_text)
        if dialog.exec() == QDialog.Accepted:
            new_authors = dialog.get_authors_text()
            if new_authors != authors_text:
                self.authors_edit.setText(new_authors)
                self.status_label.setText("作者顺序已更新，请保存")
                self.status_label.setStyleSheet("color: green;")
    
    def _open_pdf(self):
        if not self.current_paper:
            return
        file_path = self.current_paper.get('file_path')
        if file_path:
            abs_path = self.get_abs_path(file_path) if self.get_abs_path else file_path
            if abs_path and os.path.exists(abs_path):
                try:
                    os.startfile(abs_path)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"无法打开文件: {e}")
            else:
                QMessageBox.warning(self, "错误", f"文件不存在: {abs_path}")
    
    def _trigger_ocr(self):
        if not self.current_paper:
            return
        
        if self.ocr_in_progress:
            self.status_label.setText("OCR 正在进行中，请稍候...")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        file_path = self.current_paper.get('file_path')
        if not file_path:
            self.status_label.setText("无PDF文件路径")
            self.status_label.setStyleSheet("color: red;")
            return
        
        from core.ocr import is_ocr_configured
        if not is_ocr_configured():
            self.status_label.setText("OCR未配置，请在设置中配置OCR服务")
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.warning(self, "OCR未配置", 
                "请在菜单 设置 → 扫描设置 中配置OCR服务\n\n"
                "推荐使用百度PaddleOCR:\n"
                "https://aistudio.baidu.com/paddleocr")
            return
        
        self.ocr_in_progress = True
        self.ocr_btn.setEnabled(False)
        self.ocr_btn.setText("识别中...")
        self.status_label.setText("OCR识别中，请稍候...")
        self.status_label.setStyleSheet("color: blue;")
        self.ocr_result.setPlainText("正在调用OCR服务...")
        
        abs_path = self.get_abs_path(file_path) if self.get_abs_path else file_path
        self.ocr_thread = OCRThread(abs_path)
        self.ocr_thread.finished.connect(self._on_ocr_finished)
        self.ocr_thread.error.connect(self._on_ocr_error)
        self.ocr_thread.start()
    
    def _on_ocr_finished(self, result: str):
        self.ocr_in_progress = False
        self.ocr_btn.setEnabled(True)
        self.ocr_btn.setText("触发OCR")
        
        self.ocr_result.setPlainText(result)
        
        if result.startswith("[OCR Error]"):
            self.status_label.setText("OCR失败")
            self.status_label.setStyleSheet("color: red;")
        elif result.startswith("[OCR Warning]") or result.startswith("[OCR Result]") or len(result.strip()) < 10:
            self.status_label.setText("未识别到有效文本")
            self.status_label.setStyleSheet("color: orange;")
        else:
            char_count = len(result)
            self.status_label.setText(f"OCR成功，识别 {char_count} 字符")
            self.status_label.setStyleSheet("color: green;")
            # 自动解析并应用
            self._parse_manual_text()
    
    def _on_ocr_error(self, error: str):
        self.ocr_in_progress = False
        self.ocr_btn.setEnabled(True)
        self.ocr_btn.setText("触发OCR")
        self.status_label.setText(f"OCR错误: {error}")
        self.status_label.setStyleSheet("color: red;")
        self.ocr_result.setPlainText(f"[OCR Error] {error}")
    
    def _parse_manual_text(self):
        """解析OCR文本并自动应用到表单"""
        text = self.ocr_result.toPlainText().strip()
        if not text:
            self.status_label.setText("请先在文本框中输入或粘贴内容")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        self.parsed_data = self._extract_from_ocr(text)
        
        if self.parsed_data and any(self.parsed_data.values()):
            # 自动应用解析结果
            self._apply_ocr_result()
        else:
            self.status_label.setText("未能从文本中解析出有效信息")
            self.status_label.setStyleSheet("color: orange;")
    
    def _regenerate_bibtex_key(self):
        if not self.current_paper:
            return
        from core.extractor import generate_bibtex_key
        paper = {
            'authors': self.authors_edit.text(),
            'year': int(self.year_edit.text()) if self.year_edit.text().isdigit() else None,
            'title': self.title_edit.text()
        }
        new_key = generate_bibtex_key(paper)
        self.bibtex_key_edit.setText(new_key)
        self.status_label.setText(f"BibTeX Key 已更新: {new_key}")
        self.status_label.setStyleSheet("color: green;")
    
    def _apply_ocr_result(self):
        if not self.parsed_data:
            self.status_label.setText("无解析结果，请先触发OCR或解析文本")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        extracted = self.parsed_data
        applied = []
        
        if extracted.get('title') and extracted['title'] != self.title_edit.text():
            self.title_edit.setText(extracted['title'])
            applied.append("标题")
        
        if extracted.get('authors') and extracted['authors'] != self.authors_edit.text():
            self.authors_edit.setText(extracted['authors'])
            applied.append("作者")
        
        current_year = int(self.year_edit.text()) if self.year_edit.text().isdigit() else None
        if extracted.get('year') and extracted['year'] != current_year:
            self.year_edit.setText(str(extracted['year']))
            applied.append("年份")
        
        if extracted.get('doi') and extracted['doi'] != self.doi_edit.text():
            self.doi_edit.setText(extracted['doi'])
            if extracted.get('url'):
                self.url_edit.setText(extracted['url'])
            applied.append("DOI")
        
        if applied:
            self.status_label.setText(f"已提取: {', '.join(applied)}，请确认后保存")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("未能从解析结果中提取到新信息")
            self.status_label.setStyleSheet("color: orange;")
    
    def _extract_from_ocr(self, text: str) -> Dict:
        from core.extractor import (
            extract_doi_from_text, extract_year_from_text, 
            extract_title_from_ocr, extract_authors_from_ocr,
            extract_emails_from_ocr, correct_ocr_text
        )
        
        text = correct_ocr_text(text)
        result = {'title': None, 'authors': None, 'year': None, 'doi': None, 'url': None}
        
        try:
            from core.llm_parser import parse_with_llm
            logger.info(f"[LLM Parsing] Input text length: {len(text)} chars")
            llm_result = parse_with_llm(text)
            if llm_result:
                logger.info(f"[LLM Parsing] Result: {llm_result}")
                if llm_result.get('title'):
                    result['title'] = llm_result['title']
                if llm_result.get('authors'):
                    result['authors'] = llm_result['authors']
                if llm_result.get('year'):
                    result['year'] = llm_result['year']
                if llm_result.get('venue'):
                    result['venue'] = llm_result['venue']
                return result
        except ImportError:
            pass
        
        title = extract_title_from_ocr(text)
        if title:
            result['title'] = title
        
        authors = extract_authors_from_ocr(text)
        if authors:
            result['authors'] = authors
        
        emails = extract_emails_from_ocr(text)
        if emails:
            result['emails'] = emails
        
        doi = extract_doi_from_text(text)
        if doi:
            result['doi'] = doi
            result['url'] = f"https://doi.org/{doi}"
        
        year = extract_year_from_text(text)
        if year:
            result['year'] = year
        
        return result
    
    def _infer_publication_type(self, entry_type: str) -> str:
        """从entry_type推断publication_type"""
        mapping = {
            'article': 'journal',
            'inproceedings': 'conference',
            'proceedings': 'conference',
            'book': 'book',
            'inbook': 'book',
            'incollection': 'book',
            'phdthesis': 'other',
            'mastersthesis': 'other',
            'techreport': 'other',
            'misc': 'other',
            'unpublished': 'other',
            'patent': 'other'
        }
        return mapping.get(entry_type, 'other')
    
    def _save_changes(self):
        if not self.current_paper or not self.db:
            return
        
        try:
            year_text = self.year_edit.text().strip()
            year = int(year_text) if year_text.isdigit() else None
            
            # 检查关键字段是否变化，用于决定是否自动更新bibkey
            old_title = self.current_paper.get('title') or ''
            old_authors = self.current_paper.get('authors') or ''
            old_year = self.current_paper.get('year')
            
            new_title = self.title_edit.text().strip() or None
            new_authors = self.authors_edit.text().strip() or None
            new_year = year
            
            key_fields_changed = (
                new_title != old_title or 
                new_authors != old_authors or 
                new_year != old_year
            )
            
            # 如果关键字段变化且bibkey未手动修改，则自动更新bibkey
            current_bibkey = self.bibtex_key_edit.text().strip() or None
            if key_fields_changed:
                from core.extractor import generate_bibtex_key
                new_bibkey = generate_bibtex_key({
                    'title': new_title,
                    'authors': new_authors,
                    'year': new_year
                })
                current_bibkey = new_bibkey
                self.bibtex_key_edit.setText(new_bibkey)
            
            updates = {
                'title': new_title,
                'authors': new_authors,
                'year': new_year,
                'venue': self.venue_edit.text().strip() or None,
                'doi': self.doi_edit.text().strip() or None,
                'url': self.url_edit.text().strip() or None,
                'volume': self.volume_edit.text().strip() or None,
                'issue': self.issue_edit.text().strip() or None,
                'pages': self.pages_edit.text().strip() or None,
                'entry_type': self.entry_type_combo.currentText(),
                'publication_type': self._infer_publication_type(self.entry_type_combo.currentText()),
                'bibtex_key': current_bibkey,
                'impact_factor': float(self.impact_factor_edit.text()) if self.impact_factor_edit.text().strip() else None
            }
            self.db.update_paper(self.current_paper['id'], **updates)
            
            # 保存标签
            tag_names = [t.strip() for t in self.tag_edit.text().split(';') if t.strip()]
            self.db.set_paper_tags(self.current_paper['id'], tag_names)
            
            # 自动添加期刊/会议标签
            self.db.auto_tag_paper_by_type(
                self.current_paper['id'],
                entry_type=updates.get('entry_type'),
                publication_type=updates.get('publication_type')
            )
            
            # 更新current_paper以反映新值
            self.current_paper.update(updates)
            
            self.status_label.setText("已保存")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.data_changed.emit(self.current_paper)
        except Exception as e:
            self.status_label.setText(f"保存失败: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    def _resolve_doi(self):
        if not self.current_paper:
            return
        self.status_label.setText("DOI查找已触发，请稍后刷新查看结果")
        self.status_label.setStyleSheet("color: blue;")

    def _query_impact_factor(self):
        if not self.db or not self.current_paper:
            return
        
        journal = self.venue_edit.text().strip()
        if not journal:
            self.status_label.setText("请先输入期刊名称")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        self.if_btn.setEnabled(False)
        self.if_btn.setText("查询中...")
        
        try:
            from core.journal_impact import query_impact_factor
            impact_factor = query_impact_factor(journal)
            
            if impact_factor and impact_factor > 0:
                self.impact_factor_edit.setText(f"{impact_factor:.1f}")
                self.status_label.setText(f"已获取 {journal} IF: {impact_factor:.1f}")
                self.status_label.setStyleSheet("color: green;")
                
                if self.current_paper:
                    self.db.update_paper(self.current_paper['id'], impact_factor=impact_factor)
                    self.status_label.setText(f"已获取并保存 {journal} IF: {impact_factor:.1f}")
            else:
                self.status_label.setText(f"未找到 {journal} 的影响因子")
                self.status_label.setStyleSheet("color: orange;")
        except Exception as e:
            self.status_label.setText(f"查询失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.if_btn.setEnabled(True)
            self.if_btn.setText("查询")

    def _update_selected_impact_factors(self):
        """更新选中文献的影响因子"""
        if not self.db:
            return
        
        papers = self.selected_papers if self.selected_papers else ([self.current_paper] if self.current_paper else [])
        if not papers:
            self.status_label.setText("请先选择要更新的文献")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        self.status_label.setText(f"正在更新 {len(papers)} 篇文献的影响因子...")
        self.status_label.setStyleSheet("color: blue;")
        self.if_update_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            from core.journal_impact import query_impact_factor
            updated = 0
            
            for paper in papers:
                venue = paper.get('venue')
                if venue:
                    impact_factor = query_impact_factor(venue)
                    if impact_factor and impact_factor > 0:
                        self.db.update_paper(paper['id'], impact_factor=impact_factor)
                        self.db.upsert_journal_impact_factor(venue, impact_factor)
                        updated += 1
            
            self.status_label.setText(f"更新完成，更新了 {updated}/{len(papers)} 篇文献的IF")
            self.status_label.setStyleSheet("color: green;")
            self.data_changed.emit({'action': 'refresh'})
        except Exception as e:
            self.status_label.setText(f"更新失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.if_update_btn.setEnabled(True)
    
    def _query_by_doi(self):
        """通过DOI查询文献信息"""
        if not self.current_paper:
            return
        
        doi = self.doi_edit.text().strip()
        if not doi:
            self.status_label.setText("请先输入DOI")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        self.doi_query_btn.setEnabled(False)
        self.doi_query_btn.setText("查询中...")
        self.status_label.setText("正在通过DOI查询...")
        self.status_label.setStyleSheet("color: blue;")
        
        try:
            from core.resolver import query_crossref_by_doi
            result = query_crossref_by_doi(doi)
            
            if result:
                applied = []
                
                if result.get('title') and result['title'] != self.title_edit.text():
                    self.title_edit.setText(result['title'])
                    applied.append("标题")
                
                if result.get('authors') and result['authors'] != self.authors_edit.text():
                    self.authors_edit.setText(result['authors'])
                    applied.append("作者")
                
                if result.get('year') and str(result['year']) != self.year_edit.text():
                    self.year_edit.setText(str(result['year']))
                    applied.append("年份")
                
                if result.get('venue') and result['venue'] != self.venue_edit.text():
                    self.venue_edit.setText(result['venue'])
                    applied.append("出版物")
                
                if result.get('volume') and result['volume'] != self.volume_edit.text():
                    self.volume_edit.setText(result['volume'])
                    applied.append("卷")
                
                if result.get('issue') and result['issue'] != self.issue_edit.text():
                    self.issue_edit.setText(result['issue'])
                    applied.append("期")
                
                if result.get('pages') and result['pages'] != self.pages_edit.text():
                    self.pages_edit.setText(result['pages'])
                    applied.append("页码")
                
                if result.get('url') and not self.url_edit.text():
                    self.url_edit.setText(result['url'])
                
                if applied:
                    self.status_label.setText(f"已获取: {', '.join(applied)}，请确认后保存")
                    self.status_label.setStyleSheet("color: green;")
                else:
                    self.status_label.setText("DOI信息与当前数据一致")
                    self.status_label.setStyleSheet("color: orange;")
            else:
                self.status_label.setText("未找到该DOI的文献信息")
                self.status_label.setStyleSheet("color: orange;")
        
        except Exception as e:
            self.status_label.setText(f"查询失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.doi_query_btn.setEnabled(True)
            self.doi_query_btn.setText("查询")
    
    def _update_selected_by_doi(self):
        """通过DOI更新选中文献的信息"""
        if not self.db:
            return
        
        papers = self.selected_papers if self.selected_papers else ([self.current_paper] if self.current_paper else [])
        if not papers:
            self.status_label.setText("请先选择要更新的文献")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        from core.resolver import query_crossref_by_doi
        
        self.status_label.setText(f"正在通过DOI更新 {len(papers)} 篇文献...")
        self.status_label.setStyleSheet("color: blue;")
        self.doi_update_all_btn.setEnabled(False)
        self.doi_update_all_btn.setText("更新中...")
        QApplication.processEvents()
        
        try:
            updated = 0
            skipped = 0
            failed = 0
            
            for paper in papers:
                doi = paper.get('doi')
                if not doi:
                    skipped += 1
                    continue
                
                try:
                    result = query_crossref_by_doi(doi)
                    if result:
                        updates = {}
                        for field in ['title', 'authors', 'year', 'venue', 'volume', 'issue', 'pages', 'url']:
                            val = result.get(field)
                            if val and str(val) != str(paper.get(field) or ''):
                                updates[field] = val
                        
                        if updates:
                            updates['source'] = 'doi_lookup'
                            updates['confidence'] = 100
                            self.db.update_paper(paper['id'], **updates)
                            updated += 1
                            logger.info(f"Updated paper {paper['id']} by DOI: {doi}")
                        else:
                            skipped += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to update paper {paper['id']}: {e}")
            
            self.status_label.setText(f"DOI更新完成：更新 {updated} 篇，跳过 {skipped} 篇，失败 {failed} 篇")
            self.status_label.setStyleSheet("color: green;")
            self.data_changed.emit({'action': 'refresh'})
            
        except Exception as e:
            self.status_label.setText(f"批量更新失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.doi_update_all_btn.setEnabled(True)
            self.doi_update_all_btn.setText("更新选中DOI")
    
    def _update_selected_bibkeys(self):
        """重新生成选中文献的BibTeX Key"""
        if not self.db:
            return
        
        papers = self.selected_papers if self.selected_papers else ([self.current_paper] if self.current_paper else [])
        if not papers:
            self.status_label.setText("请先选择要更新的文献")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        from core.extractor import generate_bibtex_key
        
        self.status_label.setText(f"正在更新 {len(papers)} 篇文献的BibKey...")
        self.status_label.setStyleSheet("color: blue;")
        self.bibkey_update_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            updated = 0
            
            for paper in papers:
                new_key = generate_bibtex_key(paper)
                if new_key and new_key != paper.get('bibtex_key'):
                    self.db.update_paper(paper['id'], bibtex_key=new_key)
                    updated += 1
                    logger.info(f"Updated bibkey for paper {paper['id']}: {new_key}")
            
            self.status_label.setText(f"BibKey更新完成，更新了 {updated}/{len(papers)} 篇文献")
            self.status_label.setStyleSheet("color: green;")
            self.data_changed.emit({'action': 'refresh'})
            
            # 如果当前论文被更新，刷新显示
            if self.current_paper and self.current_paper in papers:
                new_key = generate_bibtex_key(self.current_paper)
                self.bibtex_key_edit.setText(new_key)
            
        except Exception as e:
            self.status_label.setText(f"更新失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.bibkey_update_btn.setEnabled(True)
    
    def _auto_tag_selected(self):
        """根据类型自动为选中文献添加期刊/会议/中文/英文标签"""
        if not self.db:
            return
        
        papers = self.selected_papers if self.selected_papers else ([self.current_paper] if self.current_paper else [])
        if not papers:
            self.status_label.setText("请先选择要标记的文献")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        self.status_label.setText(f"正在为 {len(papers)} 篇文献添加标签...")
        self.status_label.setStyleSheet("color: blue;")
        self.auto_tag_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            tagged = 0
            
            for paper in papers:
                entry_type = paper.get('entry_type')
                publication_type = paper.get('publication_type')
                title = paper.get('title')
                
                # 调用数据库方法自动添加标签（期刊/会议 + 中文/英文）
                self.db.auto_tag_paper_by_type(
                    paper['id'],
                    entry_type=entry_type,
                    publication_type=publication_type,
                    title=title
                )
                tagged += 1
            
            self.status_label.setText(f"标签添加完成，处理了 {tagged} 篇文献")
            self.status_label.setStyleSheet("color: green;")
            
            # 刷新当前论文的标签显示
            if self.current_paper:
                tags = self.db.get_paper_tags(self.current_paper['id'])
                self.tag_edit.setText('; '.join([t['name'] for t in tags]))
            
            self.data_changed.emit({'action': 'refresh'})
            
        except Exception as e:
            self.status_label.setText(f"标签添加失败: {e}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.auto_tag_btn.setEnabled(True)
