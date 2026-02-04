from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from typing import List, Dict, Any

COLUMNS = ['', '专利名称', '专利类型', '专利号', '发明人', '申请日期', '授权日期', '权利人']
COL_WIDTHS = [35, 250, 50, 180, 200, 90, 90, 150]

class PatentTableModel(QAbstractTableModel):
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
                2: 'patent_type',
                3: 'patent_number',
                4: 'inventors',
                5: 'application_date',
                6: 'grant_date',
                7: 'patentee'
            }
            field = field_map.get(col, '')
            value = self._data[row].get(field, '')
            return str(value) if value else ''
        
        if role == Qt.BackgroundRole:
            confidence = self._data[row].get('confidence', 100)
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
    
    def get_patent_at(self, row: int) -> Dict[str, Any]:
        return self._data[row] if 0 <= row < len(self._data) else None
    
    def get_selected_patents(self, rows: List[int]) -> List[Dict[str, Any]]:
        return [self._data[r] for r in rows if 0 <= r < len(self._data)]
