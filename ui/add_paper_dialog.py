"""
添加论文对话框
支持通过DOI或标题检索论文信息，并可选下载PDF
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                QLineEdit, QPushButton, QGroupBox, QFormLayout,
                                QTextEdit, QProgressBar, QMessageBox, QComboBox,
                                QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
                                QApplication)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
import logging
import os
import re
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SearchThread(QThread):
    """检索论文信息的线程"""
    finished = Signal(list)  # 返回检索结果列表
    error = Signal(str)
    progress = Signal(str)
    
    def __init__(self, query: str, search_type: str = 'auto'):
        super().__init__()
        self.query = query.strip()
        self.search_type = search_type  # 'doi', 'title', 'auto'
    
    def run(self):
        try:
            from core.resolver import query_crossref_by_doi, query_crossref, query_openalex
            
            results = []
            
            # 自动检测是DOI还是标题
            if self.search_type == 'auto':
                # DOI格式: 10.xxxx/xxxxx
                if re.match(r'^10\.\d{4,}/', self.query):
                    self.search_type = 'doi'
                else:
                    self.search_type = 'title'
            
            if self.search_type == 'doi':
                self.progress.emit("正在通过DOI查询...")
                result = query_crossref_by_doi(self.query)
                if result:
                    results.append(result)
                else:
                    self.progress.emit("DOI查询无结果，尝试标题搜索...")
                    # 如果DOI查询失败，尝试作为标题搜索
                    results.extend(query_crossref(title=self.query))
                    results.extend(query_openalex(title=self.query))
            else:
                self.progress.emit("正在搜索Crossref...")
                results.extend(query_crossref(title=self.query))
                self.progress.emit("正在搜索OpenAlex...")
                results.extend(query_openalex(title=self.query))
            
            # 去重（基于DOI）
            seen_dois = set()
            unique_results = []
            for r in results:
                doi = r.get('doi')
                if doi and doi not in seen_dois:
                    seen_dois.add(doi)
                    unique_results.append(r)
                elif not doi:
                    unique_results.append(r)
            
            self.finished.emit(unique_results[:10])  # 最多返回10条
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.error.emit(str(e))


class DownloadThread(QThread):
    """下载PDF的线程"""
    finished = Signal(str)  # 返回下载的文件路径
    error = Signal(str)
    progress = Signal(int, str)  # 进度百分比, 状态文本
    
    def __init__(self, doi: str, url: str, save_dir: str, filename: str = None):
        super().__init__()
        self.doi = doi
        self.url = url
        self.save_dir = save_dir
        self.filename = filename
    
    def run(self):
        try:
            from core.proxy import get_proxies
            proxies = get_proxies()
            
            # 尝试多种下载源
            pdf_urls = self._get_pdf_urls()
            
            for i, (source_name, pdf_url) in enumerate(pdf_urls):
                self.progress.emit(int((i / len(pdf_urls)) * 50), f"尝试: {source_name}...")
                
                try:
                    pdf_content = self._try_download(pdf_url, proxies, source_name)
                    
                    if pdf_content:
                        # 生成文件名
                        if not self.filename:
                            self.filename = self._generate_filename()
                        
                        save_path = os.path.join(self.save_dir, self.filename)
                        
                        with open(save_path, 'wb') as f:
                            f.write(pdf_content)
                        
                        self.progress.emit(100, f"下载完成 ({source_name})")
                        self.finished.emit(save_path)
                        return
                        
                except Exception as e:
                    logger.warning(f"Download failed from {source_name}: {e}")
                    continue
            
            self.error.emit("无法从任何源下载PDF\n\n提示：如果您有机构订阅，请确保：\n1. 已连接校园网或VPN\n2. 在设置中配置了正确的代理")
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            self.error.emit(str(e))
    
    def _try_download(self, url: str, proxies: dict, source_name: str) -> Optional[bytes]:
        """尝试从指定URL下载PDF"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }
        
        # Unpaywall需要特殊处理
        if 'unpaywall' in url:
            return self._try_unpaywall(url, proxies, headers)
        
        response = requests.get(url, headers=headers, proxies=proxies, 
                              timeout=60, stream=True, allow_redirects=True)
        
        # 检查是否是PDF
        content_type = response.headers.get('Content-Type', '')
        
        # 读取内容
        content = b''
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content += chunk
                downloaded += len(chunk)
                if total_size > 0:
                    progress = 50 + int((downloaded / total_size) * 50)
                    self.progress.emit(progress, f"下载中... {downloaded // 1024}KB")
        
        # 验证是否是PDF
        if content[:4] == b'%PDF' or 'pdf' in content_type.lower():
            return content
        
        return None
    
    def _try_unpaywall(self, url: str, proxies: dict, headers: dict) -> Optional[bytes]:
        """通过Unpaywall API获取开放获取PDF"""
        try:
            response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # 获取最佳开放获取链接
                best_oa = data.get('best_oa_location')
                if best_oa:
                    pdf_url = best_oa.get('url_for_pdf') or best_oa.get('url')
                    if pdf_url:
                        self.progress.emit(60, "找到开放获取链接...")
                        return self._try_download(pdf_url, proxies, "Open Access")
        except Exception as e:
            logger.warning(f"Unpaywall failed: {e}")
        return None
    
    def _get_pdf_urls(self) -> List[tuple]:
        """获取可能的PDF下载链接，返回 (来源名称, URL) 列表"""
        urls = []
        
        if self.doi:
            # 1. 出版商直接链接（需要机构订阅）
            # IEEE
            if '10.1109' in self.doi:
                # IEEE Xplore PDF链接格式
                # 从DOI提取文章ID
                urls.append(("IEEE Xplore", f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={self._extract_ieee_id()}&ref="))
                urls.append(("IEEE Direct", f"https://doi.org/{self.doi}"))
            
            # Elsevier (ScienceDirect)
            elif '10.1016' in self.doi:
                urls.append(("ScienceDirect", f"https://doi.org/{self.doi}"))
            
            # Springer
            elif '10.1007' in self.doi:
                urls.append(("Springer", f"https://link.springer.com/content/pdf/{self.doi}.pdf"))
                urls.append(("Springer Direct", f"https://doi.org/{self.doi}"))
            
            # Wiley
            elif '10.1002' in self.doi:
                urls.append(("Wiley", f"https://doi.org/{self.doi}"))
            
            # ACM
            elif '10.1145' in self.doi:
                urls.append(("ACM DL", f"https://dl.acm.org/doi/pdf/{self.doi}"))
            
            # 2. DOI直接解析（通用）
            urls.append(("DOI Resolver", f"https://doi.org/{self.doi}"))
            
            # 3. Unpaywall (合法开放获取)
            urls.append(("Unpaywall", f"https://api.unpaywall.org/v2/{self.doi}?email=biomanager@example.com"))
            
            # 4. arXiv (如果有)
            if 'arxiv' in self.doi.lower():
                arxiv_id = self.doi.split('/')[-1]
                urls.append(("arXiv", f"https://arxiv.org/pdf/{arxiv_id}.pdf"))
        
        # 5. 直接URL
        if self.url:
            urls.append(("Direct URL", self.url))
        
        return urls
    
    def _extract_ieee_id(self) -> str:
        """从IEEE DOI中提取文章ID"""
        # IEEE DOI格式: 10.1109/TIFS.2024.1234567
        # 文章ID通常是最后的数字部分
        if self.doi:
            parts = self.doi.split('.')
            for part in reversed(parts):
                if part.isdigit():
                    return part
            # 尝试从最后一部分提取数字
            last_part = self.doi.split('/')[-1]
            numbers = re.findall(r'\d+', last_part)
            if numbers:
                return numbers[-1]
        return ""
    
    def _generate_filename(self) -> str:
        """生成PDF文件名"""
        if self.doi:
            # 使用DOI生成文件名，替换特殊字符
            safe_doi = re.sub(r'[<>:"/\\|?*]', '_', self.doi)
            return f"{safe_doi}.pdf"
        return "downloaded_paper.pdf"


class AddPaperDialog(QDialog):
    """添加论文对话框"""
    
    paper_added = Signal(dict)  # 论文添加成功信号
    
    def __init__(self, parent=None, db=None, root_dir=None):
        super().__init__(parent)
        self.db = db
        self.root_dir = root_dir
        self.search_results = []
        self.selected_paper = None
        self.search_thread = None
        self.download_thread = None
        
        self.setWindowTitle("添加论文")
        self.setMinimumSize(700, 600)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 搜索区域
        search_group = QGroupBox("搜索论文")
        search_layout = QVBoxLayout()
        
        hint_label = QLabel("输入DOI（如 10.1109/xxx）或论文标题进行搜索")
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        search_layout.addWidget(hint_label)
        
        search_input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入DOI或论文标题...")
        self.search_input.returnPressed.connect(self._on_search)
        search_input_layout.addWidget(self.search_input)
        
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._on_search)
        search_input_layout.addWidget(self.search_btn)
        
        search_layout.addLayout(search_input_layout)
        
        self.search_status = QLabel("")
        self.search_status.setStyleSheet("color: blue;")
        search_layout.addWidget(self.search_status)
        
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        # 搜索结果表格
        results_group = QGroupBox("搜索结果（点击选择）")
        results_layout = QVBoxLayout()
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["标题", "作者", "年份", "期刊/会议"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        self.results_table.itemSelectionChanged.connect(self._on_result_selected)
        self.results_table.setMaximumHeight(200)
        
        results_layout.addWidget(self.results_table)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        # 论文详情（可编辑）
        detail_group = QGroupBox("论文详情")
        detail_layout = QFormLayout()
        detail_layout.setSpacing(8)
        
        self.title_edit = QLineEdit()
        detail_layout.addRow("标题:", self.title_edit)
        
        self.authors_edit = QLineEdit()
        self.authors_edit.setPlaceholderText("作者1; 作者2; ...")
        detail_layout.addRow("作者:", self.authors_edit)
        
        self.year_edit = QLineEdit()
        self.year_edit.setMaximumWidth(100)
        detail_layout.addRow("年份:", self.year_edit)
        
        self.venue_edit = QLineEdit()
        detail_layout.addRow("期刊/会议:", self.venue_edit)
        
        self.doi_edit = QLineEdit()
        detail_layout.addRow("DOI:", self.doi_edit)
        
        self.url_edit = QLineEdit()
        detail_layout.addRow("URL:", self.url_edit)
        
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)
        
        # PDF下载选项
        download_group = QGroupBox("PDF下载")
        download_layout = QVBoxLayout()
        
        self.download_check = QCheckBox("尝试下载PDF到文献库根目录")
        self.download_check.setChecked(True)
        download_layout.addWidget(self.download_check)
        
        download_hint = QLabel("注意：PDF下载依赖开放获取源，部分论文可能无法下载")
        download_hint.setStyleSheet("color: gray; font-size: 11px;")
        download_layout.addWidget(download_hint)
        
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        download_layout.addWidget(self.download_progress)
        
        self.download_status = QLabel("")
        self.download_status.setVisible(False)
        download_layout.addWidget(self.download_status)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.add_btn = QPushButton("添加论文")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._on_add_paper)
        btn_layout.addWidget(self.add_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_search(self):
        """执行搜索"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "提示", "请输入DOI或论文标题")
            return
        
        self.search_btn.setEnabled(False)
        self.search_status.setText("搜索中...")
        self.search_status.setStyleSheet("color: blue;")
        self.results_table.setRowCount(0)
        self.search_results = []
        
        self.search_thread = SearchThread(query)
        self.search_thread.finished.connect(self._on_search_finished)
        self.search_thread.error.connect(self._on_search_error)
        self.search_thread.progress.connect(lambda msg: self.search_status.setText(msg))
        self.search_thread.start()
    
    def _on_search_finished(self, results: List[Dict]):
        """搜索完成"""
        self.search_btn.setEnabled(True)
        self.search_results = results
        
        if not results:
            self.search_status.setText("未找到匹配的论文")
            self.search_status.setStyleSheet("color: orange;")
            return
        
        self.search_status.setText(f"找到 {len(results)} 条结果")
        self.search_status.setStyleSheet("color: green;")
        
        # 填充表格
        self.results_table.setRowCount(len(results))
        for i, paper in enumerate(results):
            self.results_table.setItem(i, 0, QTableWidgetItem(paper.get('title', '')[:80]))
            authors = paper.get('authors', '')
            if len(authors) > 50:
                authors = authors[:50] + '...'
            self.results_table.setItem(i, 1, QTableWidgetItem(authors))
            self.results_table.setItem(i, 2, QTableWidgetItem(str(paper.get('year', ''))))
            self.results_table.setItem(i, 3, QTableWidgetItem(paper.get('venue', '')[:30]))
        
        # 自动选择第一条
        if results:
            self.results_table.selectRow(0)
    
    def _on_search_error(self, error: str):
        """搜索出错"""
        self.search_btn.setEnabled(True)
        self.search_status.setText(f"搜索失败: {error}")
        self.search_status.setStyleSheet("color: red;")
    
    def _on_result_selected(self):
        """选择搜索结果"""
        selected = self.results_table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        if row < len(self.search_results):
            paper = self.search_results[row]
            self.selected_paper = paper
            
            # 填充详情表单
            self.title_edit.setText(paper.get('title', ''))
            self.authors_edit.setText(paper.get('authors', ''))
            self.year_edit.setText(str(paper.get('year', '')))
            self.venue_edit.setText(paper.get('venue', ''))
            self.doi_edit.setText(paper.get('doi', ''))
            self.url_edit.setText(paper.get('url', ''))
            
            self.add_btn.setEnabled(True)
    
    def _on_add_paper(self):
        """添加论文"""
        if not self.db:
            QMessageBox.warning(self, "错误", "数据库未连接")
            return
        
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请输入论文标题")
            return
        
        # 收集论文信息
        paper_data = {
            'title': title,
            'authors': self.authors_edit.text().strip(),
            'year': int(self.year_edit.text()) if self.year_edit.text().isdigit() else None,
            'venue': self.venue_edit.text().strip(),
            'doi': self.doi_edit.text().strip(),
            'url': self.url_edit.text().strip(),
        }
        
        # 检测出版物类型
        from core.resolver import detect_publication_type
        publication_type = detect_publication_type(paper_data['venue'])
        paper_data['publication_type'] = publication_type
        
        # 生成BibTeX key
        from core.extractor import generate_bibtex_key
        paper_data['bibtex_key'] = generate_bibtex_key(paper_data)
        
        # 如果需要下载PDF
        if self.download_check.isChecked() and paper_data.get('doi') and self.root_dir:
            self._start_download(paper_data)
        else:
            self._save_paper(paper_data)
    
    def _start_download(self, paper_data: Dict):
        """开始下载PDF"""
        self.add_btn.setEnabled(False)
        self.download_progress.setVisible(True)
        self.download_progress.setValue(0)
        self.download_status.setVisible(True)
        self.download_status.setText("准备下载...")
        
        self.download_thread = DownloadThread(
            doi=paper_data.get('doi'),
            url=paper_data.get('url'),
            save_dir=self.root_dir
        )
        self.download_thread.finished.connect(lambda path: self._on_download_finished(path, paper_data))
        self.download_thread.error.connect(lambda err: self._on_download_error(err, paper_data))
        self.download_thread.progress.connect(self._on_download_progress)
        self.download_thread.start()
    
    def _on_download_progress(self, percent: int, status: str):
        """下载进度更新"""
        self.download_progress.setValue(percent)
        self.download_status.setText(status)
    
    def _on_download_finished(self, pdf_path: str, paper_data: Dict):
        """下载完成"""
        self.download_status.setText(f"下载成功: {os.path.basename(pdf_path)}")
        self.download_status.setStyleSheet("color: green;")
        
        # 关联PDF文件
        rel_path = os.path.relpath(pdf_path, self.root_dir)
        paper_data['file_path'] = rel_path
        
        self._save_paper(paper_data, pdf_path)
    
    def _on_download_error(self, error: str, paper_data: Dict):
        """下载失败"""
        self.download_status.setText(f"下载失败: {error}")
        self.download_status.setStyleSheet("color: orange;")
        
        # 询问是否仍然添加论文（不带PDF）
        reply = QMessageBox.question(
            self, "下载失败",
            f"PDF下载失败: {error}\n\n是否仍然添加论文条目（不带PDF文件）？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self._save_paper(paper_data)
        else:
            self.add_btn.setEnabled(True)
    
    def _save_paper(self, paper_data: Dict, pdf_path: str = None):
        """保存论文到数据库"""
        try:
            # 如果有PDF文件，先添加PDF记录
            pdf_id = None
            if pdf_path and os.path.exists(pdf_path):
                import hashlib
                with open(pdf_path, 'rb') as f:
                    sha256 = hashlib.sha256(f.read()).hexdigest()
                
                rel_path = os.path.relpath(pdf_path, self.root_dir)
                stat = os.stat(pdf_path)
                
                pdf_id = self.db.upsert_pdf_file(
                    path=rel_path,
                    sha256=sha256,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    parse_status='success',
                    filename=os.path.basename(pdf_path)
                )
            
            # 添加论文记录
            paper_id = self.db.upsert_paper(
                title=paper_data.get('title'),
                authors=paper_data.get('authors'),
                year=paper_data.get('year'),
                venue=paper_data.get('venue'),
                doi=paper_data.get('doi'),
                url=paper_data.get('url'),
                entry_type='article',
                publication_type=paper_data.get('publication_type', 'other'),
                bibtex_key=paper_data.get('bibtex_key'),
                confidence=100,
                source='manual'
            )
            
            # 关联PDF和论文
            if pdf_id and paper_id:
                self.db.link_paper_pdf(paper_id, pdf_id)
            
            paper_data['id'] = paper_id
            self.paper_added.emit(paper_data)
            
            QMessageBox.information(self, "成功", 
                f"论文已添加: {paper_data.get('title', '')[:50]}...")
            self.accept()
            
        except Exception as e:
            logger.error(f"Failed to save paper: {e}")
            QMessageBox.critical(self, "错误", f"保存失败: {e}")
            self.add_btn.setEnabled(True)
