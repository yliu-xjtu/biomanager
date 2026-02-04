from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from typing import List, Dict, Any

COLUMNS = ['', '标题', '作者', '年份', '刊物', '文件名', '识别状态', '识别分数']
COL_WIDTHS = [35, 280, 160, 50, 120, 160, 80, 70]

def format_author_name(author: str) -> str:
    if not author or ';' in author:
        return author
    return author
    parts = author.strip().split()
    if len(parts) >= 2:
        last_name = parts[-1]
        first_name = ' '.join(parts[:-1])
        return f"{last_name}, {first_name}"
    return author

def format_authors_for_display(authors_text: str) -> str:
    if not authors_text:
        return ''
    authors = [a.strip() for a in authors_text.split(';') if a.strip()]
    formatted = [format_author_name(a) for a in authors]
    return '; '.join(formatted)

class PaperTableModel(QAbstractTableModel):
    def __init__(self, data: List[Dict[str, Any]] = None):
        super().__init__()
        self._data = data or []
    
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)
    
    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)
    
    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if role == Qt.DisplayRole:
            if col == 0:
                return str(row + 1)
            field_map = {
                1: 'title',
                2: 'authors',
                3: 'year',
                4: 'venue',
                5: 'file_name',
                6: 'parse_status',
                7: 'confidence'
            }
            field = field_map.get(col, '')
            value = self._data[row].get(field, '')
            if col == 2:
                return format_authors_for_display(str(value)) if value else ''
            if col == 6:
                status_map = {
                    'pending': '等待解析',
                    'success': '成功',
                    'needs_review': '需审核',
                    'needs_ocr': '需OCR',
                    'failed': '失败'
                }
                return status_map.get(value, value or '')
            if col == 7:
                return f"{value:.1f}" if value else "0.0"
            return str(value) if value else ''
        
        if role == Qt.BackgroundRole and col == 7:
            confidence = self._data[row].get('confidence', 0)
            if confidence < 50:
                return Qt.lightGray
            elif confidence < 80:
                return Qt.yellow
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        if role == Qt.SizeHintRole and orientation == Qt.Horizontal:
            return COL_WIDTHS[section]
        return None
    
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled
    
    def update_data(self, data: List[Dict[str, Any]]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()
    
    def get_paper_at(self, row: int) -> Dict[str, Any]:
        return self._data[row] if 0 <= row < len(self._data) else None
    
    def get_selected_papers(self, rows: List[int]) -> List[Dict[str, Any]]:
        return [self._data[r] for r in rows if 0 <= r < len(self._data)]
