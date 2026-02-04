from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
                                QTextEdit, QPushButton, QLabel, QFileDialog, QMessageBox,
                                QGroupBox, QComboBox, QFrame, QVBoxLayout)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QColor, QPalette, QPainter, QPen, QBrush
from typing import Dict, Any, Callable, Optional
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PatentValidationIndicator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.validation_state = None
        self._update_visual()
    
    def set_valid(self, is_valid: bool, message: str = ""):
        self.validation_state = is_valid
        self.toolTip = message if message else ("专利号格式正确" if is_valid else "专利号格式错误")
        self._update_visual()
        self.update()
    
    def clear(self):
        self.validation_state = None
        self.toolTip = ""
        self._update_visual()
        self.update()
    
    def _update_visual(self):
        if self.validation_state is None:
            self.setStyleSheet("background-color: transparent; border: none;")
        elif self.validation_state:
            self.setStyleSheet("""
                QFrame {
                    background-color: #4CAF50;
                    border-radius: 12px;
                    border: 2px solid #388E3C;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #f44336;
                    border-radius: 12px;
                    border: 2px solid #D32F2F;
                }
            """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.validation_state is None:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.validation_state:
            painter.setPen(QPen(Qt.white, 2, Qt.SolidLine))
            painter.setBrush(QBrush(Qt.white, Qt.SolidPattern))
            painter.drawLine(7, 12, 10, 15)
            painter.drawLine(10, 15, 17, 8)
        else:
            painter.setPen(QPen(Qt.white, 2, Qt.SolidLine))
            painter.setBrush(QBrush(Qt.white, Qt.SolidPattern))
            painter.drawLine(8, 8, 16, 16)
            painter.drawLine(16, 8, 8, 16)


class PatentOCRThread(QThread):
    """专利证书OCR识别线程"""
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
            logger.error(f"OCR failed: {e}")
            self.error.emit(str(e))


class PatentDetailPanel(QWidget):
    data_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = None
        self.current_patent = None
        self.get_abs_path = None
        self.ocr_in_progress = False
        self.parsed_data = None
        self._setup_ui()
    
    def set_database(self, db, get_abs_path: Callable, patent_model=None):
        self.db = db
        self.get_abs_path = get_abs_path
        self.patent_model = patent_model
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        
        # 发明名称
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("发明名称")
        form_layout.addRow("发明名称:", self.title_edit)
        
        # 专利类型
        self.patent_type_combo = QComboBox()
        self.patent_type_combo.addItems(["发明", "实用新型", "外观设计"])
        form_layout.addRow("专利类型:", self.patent_type_combo)
        
        # 专利号
        patent_number_layout = QHBoxLayout()
        self.patent_number_edit = QLineEdit()
        self.patent_number_edit.setPlaceholderText("如: ZL202211551727.X")
        self.patent_number_edit.textChanged.connect(self._on_patent_number_changed)
        patent_number_layout.addWidget(self.patent_number_edit)
        
        self.patent_validation = PatentValidationIndicator()
        patent_number_layout.addWidget(self.patent_validation)
        
        form_layout.addRow("专利号:", patent_number_layout)
        
        # 授权公告号
        self.grant_number_edit = QLineEdit()
        self.grant_number_edit.setPlaceholderText("如: CN116055099B")
        form_layout.addRow("授权公告号:", self.grant_number_edit)
        
        # 发明人
        self.inventors_edit = QLineEdit()
        self.inventors_edit.setPlaceholderText("多个发明人用分号分隔")
        form_layout.addRow("发明人:", self.inventors_edit)
        
        # 专利权人
        self.patentee_edit = QLineEdit()
        self.patentee_edit.setPlaceholderText("专利权人")
        form_layout.addRow("权利人:", self.patentee_edit)
        
        # 申请日期
        self.application_date_edit = QLineEdit()
        self.application_date_edit.setPlaceholderText("YYYY-MM-DD")
        form_layout.addRow("申请日期:", self.application_date_edit)
        
        # 授权日期
        self.grant_date_edit = QLineEdit()
        self.grant_date_edit.setPlaceholderText("YYYY-MM-DD")
        form_layout.addRow("授权日期:", self.grant_date_edit)
        
        # 官方链接 - 隐藏
        self.url_edit = QLineEdit()
        self.url_edit.setVisible(False)
        
        layout.addLayout(form_layout)
        
        # OCR识别区域（替代原来的摘要框）
        ocr_group = QGroupBox("OCR识别")
        ocr_layout = QVBoxLayout()
        
        # 状态标签
        self.status_label = QLabel("点击'触发OCR'识别证书内容")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        ocr_layout.addWidget(self.status_label)
        
        # OCR结果显示框
        self.ocr_result = QTextEdit()
        self.ocr_result.setMaximumHeight(150)
        self.ocr_result.setPlaceholderText("OCR识别结果将显示在这里，也可手动粘贴文本进行解析")
        ocr_layout.addWidget(self.ocr_result)
        
        # OCR按钮组
        ocr_btn_layout = QHBoxLayout()
        
        self.ocr_btn = QPushButton("触发OCR")
        self.ocr_btn.clicked.connect(self._trigger_ocr)
        ocr_btn_layout.addWidget(self.ocr_btn)
        
        self.parse_btn = QPushButton("解析并应用")
        self.parse_btn.clicked.connect(self._parse_ocr_text)
        self.parse_btn.setToolTip("解析文本并自动应用到表单字段")
        ocr_btn_layout.addWidget(self.parse_btn)
        
        ocr_layout.addLayout(ocr_btn_layout)
        ocr_group.setLayout(ocr_layout)
        layout.addWidget(ocr_group)
        
        # 标签编辑
        tag_layout = QHBoxLayout()
        tag_layout.addWidget(QLabel("标签:"))
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("标签1; 标签2; ...")
        tag_layout.addWidget(self.tag_edit, 1)
        layout.addLayout(tag_layout)
        
        # 证书文件组 - 暂时隐藏
        # file_group = QGroupBox("证书文件")
        # file_layout = QVBoxLayout()
        # 
        # file_btn_layout = QHBoxLayout()
        # self.file_path_edit = QLineEdit()
        # self.file_path_edit.setReadOnly(True)
        # file_btn_layout.addWidget(self.file_path_edit)
        # 
        # self.file_btn = QPushButton("选择文件")
        # self.file_btn.clicked.connect(self._select_file)
        # file_btn_layout.addWidget(self.file_btn)
        # file_layout.addLayout(file_btn_layout)
        # 
        # open_btn_layout = QHBoxLayout()
        # self.open_file_btn = QPushButton("打开证书")
        # self.open_file_btn.clicked.connect(self._open_file)
        # self.open_file_btn.setEnabled(False)
        # open_btn_layout.addWidget(self.open_file_btn)
        # open_btn_layout.addStretch()
        # file_layout.addLayout(open_btn_layout)
        # 
        # file_group.setLayout(file_layout)
        # layout.addWidget(file_group)
        
        # 保留file_path_edit但隐藏
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setVisible(False)
        self.open_file_btn = QPushButton()
        self.open_file_btn.setVisible(False)
        
        layout.addStretch()
        
        # 保存和删除按钮
        btn_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save)
        btn_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._delete)
        btn_layout.addWidget(self.delete_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_patent_number_changed(self, text: str):
        """专利号输入变化时实时验证"""
        from core.extractor import validate_patent_number
        if not text or not text.strip():
            self.patent_validation.clear()
            return
        
        is_valid, message = validate_patent_number(text)
        self.patent_validation.set_valid(is_valid, message)
    
    def load_patent(self, patent: Optional[Dict[str, Any]]):
        self.current_patent = patent
        
        if not patent:
            self.title_edit.clear()
            self.patent_type_combo.setCurrentIndex(0)
            self.patent_number_edit.clear()
            self.patent_validation.clear()
            self.grant_number_edit.clear()
            self.inventors_edit.clear()
            self.patentee_edit.clear()
            self.application_date_edit.clear()
            self.grant_date_edit.clear()
            self.url_edit.clear()
            self.file_path_edit.clear()
            self.tag_edit.clear()
            self.ocr_result.clear()
            self.status_label.setText("点击'触发OCR'识别证书内容")
            self.status_label.setStyleSheet("color: gray;")
            self.open_file_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
        
        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        
        self.title_edit.setText(patent.get('title', ''))
        
        patent_type = patent.get('patent_type', '发明')
        idx = self.patent_type_combo.findText(patent_type)
        if idx >= 0:
            self.patent_type_combo.setCurrentIndex(idx)
        
        self.patent_number_edit.setText(patent.get('patent_number', ''))
        if patent.get('patent_number'):
            self._on_patent_number_changed(patent.get('patent_number', ''))
        else:
            self.patent_validation.clear()
        
        self.grant_number_edit.setText(patent.get('grant_number', ''))
        self.inventors_edit.setText(patent.get('inventors', ''))
        self.patentee_edit.setText(patent.get('patentee', ''))
        self.application_date_edit.setText(patent.get('application_date', ''))
        self.grant_date_edit.setText(patent.get('grant_date', ''))
        self.url_edit.setText(patent.get('url', ''))
        
        file_path = patent.get('file_path', '')
        self.file_path_edit.setText(file_path)
        self.open_file_btn.setEnabled(bool(file_path))
        
        # 加载标签
        if self.db:
            tags = self.db.get_patent_tags(patent['id'])
            self.tag_edit.setText('; '.join([t['name'] for t in tags]))
    
    def _trigger_ocr(self):
        """触发OCR识别"""
        if not self.current_patent:
            self.status_label.setText("请先选择一个专利")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        if self.ocr_in_progress:
            self.status_label.setText("OCR正在进行中，请稍候...")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        file_path = self.current_patent.get('file_path')
        if not file_path:
            self.status_label.setText("无证书文件路径")
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
        self.ocr_thread = PatentOCRThread(abs_path)
        self.ocr_thread.finished.connect(self._on_ocr_finished)
        self.ocr_thread.error.connect(self._on_ocr_error)
        self.ocr_thread.start()
    
    def _on_ocr_finished(self, result: str):
        """OCR完成回调"""
        self.ocr_in_progress = False
        self.ocr_btn.setEnabled(True)
        self.ocr_btn.setText("触发OCR")
        
        self.ocr_result.setPlainText(result)
        
        if result.startswith("[OCR Error]"):
            self.status_label.setText("OCR失败")
            self.status_label.setStyleSheet("color: red;")
        elif result.startswith("[OCR Warning]") or len(result.strip()) < 10:
            self.status_label.setText("未识别到有效文本")
            self.status_label.setStyleSheet("color: orange;")
        else:
            char_count = len(result)
            self.status_label.setText(f"OCR成功，识别 {char_count} 字符，点击'解析文本'")
            self.status_label.setStyleSheet("color: green;")
            # 自动解析
            self._parse_ocr_text()
    
    def _on_ocr_error(self, error: str):
        """OCR错误回调"""
        self.ocr_in_progress = False
        self.ocr_btn.setEnabled(True)
        self.ocr_btn.setText("触发OCR")
        self.status_label.setText(f"OCR错误: {error}")
        self.status_label.setStyleSheet("color: red;")
        self.ocr_result.setPlainText(f"[OCR Error] {error}")
    
    def _parse_ocr_text(self):
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
    
    def _extract_from_ocr(self, text: str) -> Dict:
        """从OCR文本中提取专利信息"""
        from core.extractor import extract_patent_info_from_text
        import re
        
        # 清理OCR文本中的HTML标签和Markdown格式
        # 移除<div>, <img>, <span>等HTML标签
        cleaned_text = re.sub(r'<[^>]+>', '', text)
        # 移除Markdown图片语法 ![...](...)
        cleaned_text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', '', cleaned_text)
        # 移除多余的空行
        cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
        # 移除行首的#号（Markdown标题）
        cleaned_text = re.sub(r'^#+\s*', '', cleaned_text, flags=re.MULTILINE)
        
        logger.info(f"Cleaned OCR text (first 200 chars): {cleaned_text[:200]}")
        
        result = extract_patent_info_from_text(cleaned_text)
        
        # 记录提取结果
        logger.info(f"Extracted patent info: {result}")
        
        return result
    
    def _apply_ocr_result(self):
        """将OCR解析结果应用到表单"""
        if not self.parsed_data:
            self.status_label.setText("无解析结果，请先触发OCR或解析文本")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        extracted = self.parsed_data
        applied = []
        skipped = []
        not_found = []
        
        # 字段映射：提取的key -> (表单控件, 显示名称)
        field_mapping = [
            ('title', self.title_edit, "发明名称"),
            ('patent_number', self.patent_number_edit, "专利号"),
            ('grant_number', self.grant_number_edit, "授权公告号"),
            ('inventors', self.inventors_edit, "发明人"),
            ('patentee', self.patentee_edit, "权利人"),
            ('application_date', self.application_date_edit, "申请日期"),
            ('grant_date', self.grant_date_edit, "授权日期"),
        ]
        
        for key, edit_field, display_name in field_mapping:
            extracted_value = extracted.get(key) or ''
            if isinstance(extracted_value, str):
                extracted_value = extracted_value.strip()
            else:
                extracted_value = str(extracted_value) if extracted_value else ''
            current_value = edit_field.text().strip()
            
            if not extracted_value:
                not_found.append(display_name)
            elif current_value:
                # 字段已有值，不覆盖
                skipped.append(f"{display_name}(已有: {current_value[:20]}...)")
            else:
                # 字段为空，应用新值
                edit_field.setText(extracted_value)
                applied.append(display_name)
        
        # 对专利号进行验证
        if self.patent_number_edit.text().strip():
            self._on_patent_number_changed(self.patent_number_edit.text())
        
        # 构建详细的反馈信息
        messages = []
        if applied:
            messages.append(f"✓ 已填充: {', '.join(applied)}")
        if skipped:
            messages.append(f"⊘ 已跳过(有值): {', '.join(skipped)}")
        if not_found:
            messages.append(f"✗ 未识别: {', '.join(not_found)}")
        
        if applied:
            self.status_label.setText(f"已应用 {len(applied)} 个字段，请确认后保存")
            self.status_label.setStyleSheet("color: green;")
            QMessageBox.information(self, "应用结果", "\n".join(messages))
        elif skipped:
            self.status_label.setText(f"{len(skipped)} 个字段已有值未覆盖")
            self.status_label.setStyleSheet("color: orange;")
            QMessageBox.warning(self, "应用结果", "\n".join(messages) + "\n\n如需覆盖已有字段，请先清空对应字段")
        else:
            self.status_label.setText("未能从OCR文本中识别出字段信息")
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.warning(self, "应用结果", "\n".join(messages) + "\n\n请检查OCR结果是否正确识别了证书内容")
    
    def _select_file(self):
        if not self.current_patent:
            QMessageBox.warning(self, "警告", "请先选择一个专利")
            return
        
        path, _ = QFileDialog.getOpenFileName(
            self, "选择证书PDF",
            self.get_abs_path('') if self.get_abs_path else '.',
            "PDF Files (*.pdf);;All Files (*)")
        if path:
            if self.get_abs_path:
                rel_path = os.path.relpath(path, self.get_abs_path(''))
                self.file_path_edit.setText(rel_path)
            else:
                self.file_path_edit.setText(path)
            self.open_file_btn.setEnabled(True)
    
    def _open_file(self):
        file_path = self.file_path_edit.text()
        if not file_path:
            return
        
        abs_path = self.get_abs_path(file_path) if self.get_abs_path else file_path
        if abs_path and os.path.exists(abs_path):
            try:
                os.startfile(abs_path)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法打开文件: {e}")
        else:
            QMessageBox.warning(self, "错误", f"文件不存在: {abs_path}")
    
    def _save(self):
        if not self.db or not self.current_patent:
            return
        
        try:
            self.db.update_patent(
                self.current_patent['id'],
                title=self.title_edit.text().strip(),
                patent_type=self.patent_type_combo.currentText(),
                patent_number=self.patent_number_edit.text().strip(),
                grant_number=self.grant_number_edit.text().strip(),
                inventors=self.inventors_edit.text().strip(),
                patentee=self.patentee_edit.text().strip(),
                application_date=self.application_date_edit.text().strip(),
                grant_date=self.grant_date_edit.text().strip(),
                url=self.url_edit.text().strip(),
                file_path=self.file_path_edit.text().strip())
            
            # 保存标签
            tag_names = [t.strip() for t in self.tag_edit.text().split(';') if t.strip()]
            self.db.set_patent_tags(self.current_patent['id'], tag_names)
            
            patents = self.db.get_all_patents()
            self.patent_model.update_data(patents)
            
            self.status_label.setText("专利信息已保存")
            self.status_label.setStyleSheet("color: green;")
        except Exception as e:
            self.status_label.setText(f"保存失败: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    def _delete(self):
        if not self.db or not self.current_patent:
            return
        
        reply = QMessageBox.question(self, "确认删除", "确定要删除此专利吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return
        
        try:
            self.db.delete_patent(self.current_patent['id'])
            self.data_changed.emit(-1)
            self.load_patent(None)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除失败: {e}")
