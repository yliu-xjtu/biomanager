from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from typing import List, Dict, Any

COLUMNS = ['', '软件名称', '登记号', '版本号', '著作权人', '开发完成日期', '权利范围']
COL_WIDTHS = [35, 250, 100, 60, 150, 100, 120]

class SoftwareTableModel(QAbstractTableModel):
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
                1: 'software_name',
                2: 'registration_number',
                3: 'version',
                4: 'copyright_holder',
                5: 'development_date',
                6: 'rights_scope'
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
    
    def get_software_at(self, row: int) -> Dict[str, Any]:
        return self._data[row] if 0 <= row < len(self._data) else None
    
    def get_selected_softwares(self, rows: List[int]) -> List[Dict[str, Any]]:
        return [self._data[r] for r in rows if 0 <= r < len(self._data)]
