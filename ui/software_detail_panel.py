from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
                                QTextEdit, QPushButton, QLabel, QFileDialog, QMessageBox,
                                QGroupBox, QComboBox, QFrame)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPainter, QPen, QBrush, QColor
from typing import Dict, Any, Callable, Optional
import os
import logging

logger = logging.getLogger(__name__)


class SoftwareOCRThread(QThread):
    """软著证书OCR识别线程"""
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


class SoftwareValidationIndicator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.validation_state = None
        self._update_visual()
    
    def set_valid(self, is_valid: bool, message: str = ""):
        self.validation_state = is_valid
        self.toolTip = message if message else ("信息完整" if is_valid else "信息缺失")
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
                    background-color: #FF9800;
                    border-radius: 12px;
                    border: 2px solid #F57C00;
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
            painter.drawLine(7, 10, 17, 10)
            painter.drawLine(12, 7, 12, 17)


class SoftwareDetailPanel(QWidget):
    data_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = None
        self.current_software = None
        self.get_abs_path = None
        self.ocr_in_progress = False
        self.parsed_data = None
        self._setup_ui()
    
    def set_database(self, db, get_abs_path: Callable, software_model=None):
        self.db = db
        self.get_abs_path = get_abs_path
        self.software_model = software_model
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        
        # 软件名称（原来在group里的title_edit）
        self.title_edit = QTextEdit()
        self.title_edit.setMaximumHeight(60)
        self.title_edit.setPlaceholderText("软件名称（根据证书自动提取）")
        form_layout.addRow("软件名称:", self.title_edit)
        
        self.software_name_edit = QLineEdit()
        self.software_name_edit.setPlaceholderText("软件全称（与证书一致）")
        self.software_name_edit.setVisible(False)  # 隐藏，用title_edit代替
        
        self.registration_number_edit = QLineEdit()
        self.registration_number_edit.setPlaceholderText("登记号")
        form_layout.addRow("登记号:", self.registration_number_edit)
        
        self.version_edit = QLineEdit()
        self.version_edit.setPlaceholderText("版本号，如 V1.0")
        form_layout.addRow("版本号:", self.version_edit)
        
        self.copyright_holder_edit = QLineEdit()
        self.copyright_holder_edit.setPlaceholderText("著作权人")
        form_layout.addRow("著作权人:", self.copyright_holder_edit)
        
        self.development_date_edit = QLineEdit()
        self.development_date_edit.setPlaceholderText("YYYY-MM-DD")
        form_layout.addRow("开发完成日期:", self.development_date_edit)
        
        self.rights_scope_combo = QComboBox()
        self.rights_scope_combo.addItems(["全部权利", "发表权", "署名权", "复制权", "发行权", "出租权", "信息网络传播权", "翻译权", "改编权", "汇编权", "其他"])
        form_layout.addRow("权利范围:", self.rights_scope_combo)
        
        layout.addLayout(form_layout)
        
        ocr_group = QGroupBox("OCR识别")
        ocr_layout = QVBoxLayout()
        
        self.status_label = QLabel("点击'触发OCR'识别证书内容")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        ocr_layout.addWidget(self.status_label)
        
        self.ocr_result = QTextEdit()
        self.ocr_result.setMaximumHeight(150)
        self.ocr_result.setPlaceholderText("OCR识别结果将显示在这里，也可手动粘贴文本进行解析")
        ocr_layout.addWidget(self.ocr_result)
        
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
        
        # 官方链接 - 隐藏
        self.url_edit = QLineEdit()
        self.url_edit.setVisible(False)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save)
        btn_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._delete)
        btn_layout.addWidget(self.delete_btn)
        
        layout.addLayout(btn_layout)
    
    def _trigger_ocr(self):
        """触发OCR识别"""
        if not self.current_software:
            self.status_label.setText("请先选择一个软著")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        if self.ocr_in_progress:
            self.status_label.setText("OCR正在进行中，请稍候...")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        file_path = self.current_software.get('file_path')
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
        self.ocr_thread = SoftwareOCRThread(abs_path)
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
        """从OCR文本中提取软著信息"""
        from core.extractor import extract_software_info_from_text, is_software_info_complete
        import re
        
        cleaned_text = re.sub(r'<[^>]+>', '', text)
        cleaned_text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', '', cleaned_text)
        cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
        cleaned_text = re.sub(r'^#+\s*', '', cleaned_text, flags=re.MULTILINE)
        
        logger.info(f"Cleaned OCR text (first 200 chars): {cleaned_text[:200]}")
        
        result = extract_software_info_from_text(cleaned_text)
        result['software_name'] = result.get('software_name') or result.get('title')
        
        logger.info(f"Extracted software info: {result}")
        
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
        
        field_mapping = [
            ('software_name', self.software_name_edit, "软件名称"),
            ('version', self.version_edit, "版本号"),
            ('registration_number', self.registration_number_edit, "登记号"),
            ('copyright_holder', self.copyright_holder_edit, "著作权人"),
            ('development_date', self.development_date_edit, "开发完成日期"),
        ]
        
        for key, edit_field, display_name in field_mapping:
            extracted_value = extracted.get(key, '').strip()
            current_value = edit_field.text().strip()
            
            if not extracted_value:
                not_found.append(display_name)
            elif current_value:
                skipped.append(f"{display_name}(已有: {current_value[:20]}...)")
            else:
                edit_field.setText(extracted_value)
                applied.append(display_name)
        
        messages = []
        if applied:
            messages.append(f"已填充: {', '.join(applied)}")
        if skipped:
            messages.append(f"已跳过(有值): {', '.join(skipped)}")
        if not_found:
            messages.append(f"未识别: {', '.join(not_found)}")
        
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
    
    def load_software(self, software: Optional[Dict[str, Any]]):
        self.current_software = software
        
        if not software:
            self.title_edit.clear()
            self.software_name_edit.clear()
            self.registration_number_edit.clear()
            self.version_edit.clear()
            self.copyright_holder_edit.clear()
            self.development_date_edit.clear()
            self.ocr_result.clear()
            self.url_edit.clear()
            self.tag_edit.clear()
            self.status_label.setText("点击'触发OCR'识别证书内容")
            self.status_label.setStyleSheet("color: gray;")
            self.save_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
        
        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        
        self.title_edit.setPlainText(software.get('software_name', '') or software.get('title', ''))
        self.software_name_edit.setText(software.get('software_name', ''))
        self.registration_number_edit.setText(software.get('registration_number', ''))
        self.version_edit.setText(software.get('version', ''))
        self.copyright_holder_edit.setText(software.get('copyright_holder', ''))
        self.development_date_edit.setText(software.get('development_date', ''))
        
        rights_scope = software.get('rights_scope', '全部权利')
        idx = self.rights_scope_combo.findText(rights_scope)
        if idx >= 0:
            self.rights_scope_combo.setCurrentIndex(idx)
        
        self.url_edit.setText(software.get('url', ''))
        
        # 加载标签
        if self.db:
            tags = self.db.get_software_tags(software['id'])
            self.tag_edit.setText('; '.join([t['name'] for t in tags]))
    
    def _save(self):
        if not self.db or not self.current_software:
            return
        
        try:
            self.db.update_software(
                self.current_software['id'],
                software_name=self.software_name_edit.text().strip(),
                title=self.title_edit.toPlainText().strip(),
                registration_number=self.registration_number_edit.text().strip(),
                version=self.version_edit.text().strip(),
                copyright_holder=self.copyright_holder_edit.text().strip(),
                development_date=self.development_date_edit.text().strip(),
                rights_scope=self.rights_scope_combo.currentText(),
                abstract="",
                url=self.url_edit.text().strip()
            )
            
            # 保存标签
            tag_names = [t.strip() for t in self.tag_edit.text().split(';') if t.strip()]
            self.db.set_software_tags(self.current_software['id'], tag_names)
            
            softwares = self.db.get_all_softwares()
            self.software_model.update_data(softwares)
            
            self.status_label.setText("软著信息已保存")
            self.status_label.setStyleSheet("color: green;")
        except Exception as e:
            self.status_label.setText(f"保存失败: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    def _delete(self):
        if not self.db or not self.current_software:
            return
        
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除此软著吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        try:
            self.db.delete_software(self.current_software['id'])
            self.data_changed.emit(-1)
            self.load_software(None)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除失败: {e}")
