import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Optional, List, Tuple, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "literature.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)
    
    @contextmanager
    def connection(self):
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def init_db(self):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = f.read()
            with self.connection() as conn:
                conn.executescript(schema)
        else:
            logger.warning("schema.sql not found, using inline schema")
        
        # 迁移：检查并添加缺失的列（每次打开都检查）
        with self.connection() as conn:
            cursor = conn.execute("PRAGMA table_info(papers)")
            columns = [row[1] for row in cursor.fetchall()]
            
            new_columns = {
                'impact_factor': 'REAL',
                'volume': 'TEXT',
                'issue': 'TEXT',
                'pages': 'TEXT',
                'publication_type': 'TEXT DEFAULT "journal"'
            }
            
            for col, type_ in new_columns.items():
                if col not in columns:
                    try:
                        conn.execute(f"ALTER TABLE papers ADD COLUMN {col} {type_}")
                        logger.info(f"Added {col} column to papers table")
                    except:
                        pass
            
            cursor = conn.execute("PRAGMA table_info(journal_impact_factors)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'impact_factor' not in columns:
                conn.execute("ALTER TABLE journal_impact_factors ADD COLUMN impact_factor REAL")
                logger.info("Added impact_factor column to journal_impact_factors table")
            
            # 迁移tags表添加category字段
            cursor = conn.execute("PRAGMA table_info(tags)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'category' not in columns:
                try:
                    conn.execute("ALTER TABLE tags ADD COLUMN category TEXT DEFAULT 'paper'")
                    logger.info("Added category column to tags table")
                except:
                    pass
            
            # 检查patents表是否存在，不存在则创建
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patents'")
            if cursor.fetchone() is None:
                logger.info("Creating patents and softwares tables...")
            
            # 迁移：为patents表添加grant_number字段（授权公告号）
            cursor = conn.execute("PRAGMA table_info(patents)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'grant_number' not in columns:
                try:
                    conn.execute("ALTER TABLE patents ADD COLUMN grant_number TEXT")
                    logger.info("Added grant_number column to patents table")
                except Exception as e:
                    logger.warning(f"Failed to add grant_number column: {e}")
            
            # 检查softwares表是否存在
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='softwares'")
            if cursor.fetchone() is None:
                conn.execute("""
                    CREATE TABLE softwares (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        software_name TEXT,
                        title TEXT,
                        registration_number TEXT,
                        version TEXT,
                        copyright_holder TEXT,
                        development_date TEXT,
                        rights_scope TEXT,
                        abstract TEXT,
                        url TEXT,
                        file_path TEXT,
                        tags TEXT,
                        confidence REAL DEFAULT 100,
                        created_at INTEGER,
                        updated_at INTEGER
                    )
                """)
                logger.info("Created softwares table")
            
            # 迁移：为softwares表添加software_name字段
            cursor = conn.execute("PRAGMA table_info(softwares)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'software_name' not in columns:
                try:
                    conn.execute("ALTER TABLE softwares ADD COLUMN software_name TEXT")
                    logger.info("Added software_name column to softwares table")
                except Exception as e:
                    logger.warning(f"Failed to add software_name column: {e}")
            
            # 迁移：为papers, patents, softwares表添加sort_order字段
            for table in ['papers', 'patents', 'softwares']:
                cursor = conn.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                if 'sort_order' not in columns:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN sort_order INTEGER DEFAULT 0")
                        logger.info(f"Added sort_order column to {table} table")
                    except Exception as e:
                        logger.warning(f"Failed to add sort_order column to {table}: {e}")
            
            # 迁移：为papers表添加abstract和notes字段
            cursor = conn.execute("PRAGMA table_info(papers)")
            columns = [row[1] for row in cursor.fetchall()]
            for col in ['abstract', 'notes']:
                if col not in columns:
                    try:
                        conn.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT")
                        logger.info(f"Added {col} column to papers table")
                    except Exception as e:
                        logger.warning(f"Failed to add {col} column to papers: {e}")
            
            logger.info("Database initialized")
    
    def get_all_papers(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.*, f.path as file_path, f.filename as file_name, f.parse_status, f.sha256
                FROM papers p
                LEFT JOIN paper_files pf ON p.id = pf.paper_id
                LEFT JOIN pdf_files f ON pf.pdf_file_id = f.id
                ORDER BY p.sort_order ASC, p.updated_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_paper_by_id(self, paper_id: int) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_pdf_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM pdf_files WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def upsert_pdf_file(self, path: str, sha256: str, size: int, mtime: float, 
                        parse_status: str = 'pending', parse_error: str = None, filename: str = None) -> int:
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO pdf_files (path, filename, sha256, size, mtime, parse_status, parse_error, last_scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                ON CONFLICT(path) DO UPDATE SET
                    filename = COALESCE(excluded.filename, filename),
                    sha256 = excluded.sha256,
                    size = excluded.size,
                    mtime = excluded.mtime,
                    parse_status = excluded.parse_status,
                    parse_error = excluded.parse_error,
                    last_scanned_at = strftime('%s', 'now')
            """, (path, filename, sha256, size, mtime, parse_status, parse_error))
            return cursor.lastrowid
    
    def upsert_paper(self, title: str = None, authors: str = None, year: int = None, 
                     venue: str = None, doi: str = None, url: str = None,
                     entry_type: str = 'article', publication_type: str = 'other',
                     bibtex_key: str = None,
                     confidence: float = 0, source: str = 'pdf',
                     volume: str = None, issue: str = None, pages: str = None) -> int:
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO papers (title, authors, year, venue, doi, url, entry_type, publication_type, bibtex_key, confidence, source, volume, issue, pages, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                ON CONFLICT(doi) DO UPDATE SET
                    title = COALESCE(excluded.title, title),
                    authors = COALESCE(excluded.authors, authors),
                    year = COALESCE(excluded.year, year),
                    venue = COALESCE(excluded.venue, venue),
                    url = COALESCE(excluded.url, url),
                    entry_type = COALESCE(excluded.entry_type, entry_type),
                    publication_type = COALESCE(excluded.publication_type, publication_type),
                    bibtex_key = COALESCE(excluded.bibtex_key, bibtex_key),
                    confidence = MAX(excluded.confidence, confidence),
                    source = excluded.source,
                    volume = COALESCE(excluded.volume, volume),
                    issue = COALESCE(excluded.issue, issue),
                    pages = COALESCE(excluded.pages, pages),
                    updated_at = strftime('%s', 'now')
            """, (title, authors, year, venue, doi, url, entry_type, publication_type, bibtex_key, confidence, source, volume, issue, pages))
            return cursor.lastrowid
    
    def link_paper_pdf(self, paper_id: int, pdf_file_id: int):
        with self.connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO paper_files (paper_id, pdf_file_id) VALUES (?, ?)
            """, (paper_id, pdf_file_id))
    
    def unlink_paper_pdfs(self, paper_id: int):
        """删除论文与所有PDF的关联"""
        with self.connection() as conn:
            conn.execute("DELETE FROM paper_files WHERE paper_id = ?", (paper_id,))
    
    def update_paper(self, paper_id: int, **kwargs):
        allowed = ['title', 'authors', 'year', 'venue', 'doi', 'url', 'entry_type', 'publication_type', 'bibtex_key', 'confidence', 'source', 'impact_factor', 'volume', 'issue', 'pages', 'abstract', 'notes']
        kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        if not kwargs:
            return
        kwargs['updated_at'] = 'strftime(\'%s\', \'now\')'
        set_clause = ', '.join([f"{k} = ?" for k in kwargs])
        values = list(kwargs.values())
        values.append(paper_id)
        with self.connection() as conn:
            conn.execute(f"UPDATE papers SET {set_clause} WHERE id = ?", values)
    
    def update_pdf_status(self, pdf_id: int, parse_status: str, parse_error: str = None):
        with self.connection() as conn:
            conn.execute("""
                UPDATE pdf_files SET parse_status = ?, parse_error = ?, last_scanned_at = strftime('%s', 'now')
                WHERE id = ?
            """, (parse_status, parse_error, pdf_id))
    
    def update_pdf_path(self, old_path: str, new_path: str, new_filename: str = None):
        """更新PDF文件路径（重命名后调用）"""
        with self.connection() as conn:
            if new_filename:
                conn.execute("""
                    UPDATE pdf_files SET path = ?, filename = ?, last_scanned_at = strftime('%s', 'now')
                    WHERE path = ?
                """, (new_path, new_filename, old_path))
            else:
                conn.execute("""
                    UPDATE pdf_files SET path = ?, last_scanned_at = strftime('%s', 'now')
                    WHERE path = ?
                """, (new_path, old_path))
    
    def delete_orphaned_papers(self):
        with self.connection() as conn:
            conn.execute("DELETE FROM papers WHERE id NOT IN (SELECT DISTINCT paper_id FROM paper_files)")
    
    def delete_paper(self, paper_id: int):
        with self.connection() as conn:
            cursor = conn.execute("SELECT pdf_file_id FROM paper_files WHERE paper_id = ?", (paper_id,))
            pdf_ids = [row[0] for row in cursor.fetchall()]
            
            conn.execute("DELETE FROM paper_files WHERE paper_id = ?", (paper_id,))
            conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
            
            for pdf_id in pdf_ids:
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM paper_files WHERE pdf_file_id = ?", (pdf_id,)
                ).fetchone()[0]
                if remaining == 0:
                    conn.execute("DELETE FROM pdf_files WHERE id = ?", (pdf_id,))
    
    def get_pending_files(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM pdf_files WHERE parse_status = 'pending'")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_for_export(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.*, GROUP_CONCAT(f.path, '; ') as file_paths
                FROM papers p
                LEFT JOIN paper_files pf ON p.id = pf.paper_id
                LEFT JOIN pdf_files f ON pf.pdf_file_id = f.id
                GROUP BY p.id
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_journal_impact_factor(self, journal_name: str) -> Optional[Dict[str, Any]]:
        if not journal_name:
            return None
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM journal_impact_factors WHERE journal_name = ?",
                (journal_name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def upsert_journal_impact_factor(self, journal_name: str, impact_factor: float) -> int:
        if not journal_name:
            return 0
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO journal_impact_factors (journal_name, impact_factor, query_date)
                VALUES (?, ?, strftime('%s', 'now'))
                ON CONFLICT(journal_name) DO UPDATE SET
                    impact_factor = excluded.impact_factor,
                    query_date = strftime('%s', 'now')
            """, (journal_name, impact_factor))
            return cursor.lastrowid
    
    def get_all_journals(self) -> List[str]:
        with self.connection() as conn:
            cursor = conn.execute("SELECT DISTINCT venue FROM papers WHERE venue IS NOT NULL AND venue != ''")
            return [row[0] for row in cursor.fetchall()]
    
    def get_papers_without_impact_factor(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.id, p.venue, p.title
                FROM papers p
                WHERE p.venue IS NOT NULL AND p.venue != ''
                AND (p.impact_factor IS NULL OR p.impact_factor = 0)
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def update_paper_impact_factor(self, paper_id: int, impact_factor: float):
        with self.connection() as conn:
            conn.execute("""
                UPDATE papers SET impact_factor = ?, updated_at = strftime('%s', 'now')
                WHERE id = ?
            """, (impact_factor, paper_id))
    
    def update_all_papers_impact_factor(self):
        papers = self.get_papers_without_impact_factor()
        updated = 0
        for paper in papers:
            if paper.get('venue'):
                journal_if = self.get_journal_impact_factor(paper['venue'])
                if journal_if and journal_if.get('impact_factor'):
                    self.update_paper_impact_factor(paper['id'], journal_if['impact_factor'])
                    updated += 1
        return updated
    
    # ========== Tag 相关方法 ==========
    
    def get_all_tags(self) -> List[Dict[str, Any]]:
        """获取所有标签"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tags ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_or_create_tag(self, name: str, color: str = '#3498db') -> int:
        """获取或创建标签，返回标签ID"""
        with self.connection() as conn:
            cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row[0]
            cursor = conn.execute(
                "INSERT INTO tags (name, color) VALUES (?, ?)",
                (name, color)
            )
            return cursor.lastrowid
    
    def delete_tag(self, tag_id: int):
        """删除标签"""
        with self.connection() as conn:
            conn.execute("DELETE FROM paper_tags WHERE tag_id = ?", (tag_id,))
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    
    def get_paper_tags(self, paper_id: int) -> List[Dict[str, Any]]:
        """获取论文的所有标签"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT t.* FROM tags t
                JOIN paper_tags pt ON t.id = pt.tag_id
                WHERE pt.paper_id = ?
                ORDER BY t.name
            """, (paper_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def add_tag_to_paper(self, paper_id: int, tag_id: int):
        """给论文添加标签"""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?, ?)",
                (paper_id, tag_id)
            )
    
    def remove_tag_from_paper(self, paper_id: int, tag_id: int):
        """从论文移除标签"""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM paper_tags WHERE paper_id = ? AND tag_id = ?",
                (paper_id, tag_id)
            )
    
    def set_paper_tags(self, paper_id: int, tag_names: List[str]):
        """设置论文的标签（替换所有现有标签）"""
        with self.connection() as conn:
            conn.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))
            for tag_name in tag_names:
                tag_name = tag_name.strip()
                if tag_name:
                    # 内联 get_or_create_tag 逻辑，避免嵌套连接导致数据库锁定
                    cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    row = cursor.fetchone()
                    if row:
                        tag_id = row[0]
                    else:
                        cursor = conn.execute(
                            "INSERT INTO tags (name, color) VALUES (?, ?)",
                            (tag_name, '#3498db')
                        )
                        tag_id = cursor.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?, ?)",
                        (paper_id, tag_id)
                    )
    
    def auto_tag_paper_by_type(self, paper_id: int, entry_type: str = None, publication_type: str = None, title: str = None):
        """根据entry_type或publication_type自动添加期刊/会议标签，根据title添加中文/英文标签"""
        tags_to_add = []
        
        # 1. 期刊/会议标签
        if entry_type:
            if entry_type.lower() in ['article', 'journal']:
                tags_to_add.append(('期刊', '#2ecc71'))
            elif entry_type.lower() in ['inproceedings', 'conference', 'proceedings']:
                tags_to_add.append(('会议', '#9b59b6'))
        
        if not any(t[0] in ['期刊', '会议'] for t in tags_to_add) and publication_type:
            if publication_type.lower() == 'journal':
                tags_to_add.append(('期刊', '#2ecc71'))
            elif publication_type.lower() == 'conference':
                tags_to_add.append(('会议', '#9b59b6'))
        
        # 2. 中文/英文标签（根据标题判断）
        if title:
            # 检测是否包含中文字符
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in title)
            if has_chinese:
                tags_to_add.append(('中文', '#e74c3c'))
            else:
                tags_to_add.append(('英文', '#3498db'))
        
        if not tags_to_add:
            return
        
        with self.connection() as conn:
            for tag_name, tag_color in tags_to_add:
                # 获取或创建标签
                cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                row = cursor.fetchone()
                if row:
                    tag_id = row[0]
                else:
                    cursor = conn.execute(
                        "INSERT INTO tags (name, color, category) VALUES (?, ?, ?)",
                        (tag_name, tag_color, 'paper')
                    )
                    tag_id = cursor.lastrowid
                
                # 检查是否已有该标签
                cursor = conn.execute(
                    "SELECT 1 FROM paper_tags WHERE paper_id = ? AND tag_id = ?",
                    (paper_id, tag_id)
                )
                if not cursor.fetchone():
                    conn.execute(
                        "INSERT INTO paper_tags (paper_id, tag_id) VALUES (?, ?)",
                        (paper_id, tag_id)
                    )
    
    def get_papers_by_tag(self, tag_id: int) -> List[Dict[str, Any]]:
        """根据标签获取论文列表"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.*, f.path as file_path, f.filename as file_name, f.parse_status, f.sha256
                FROM papers p
                JOIN paper_tags pt ON p.id = pt.paper_id
                LEFT JOIN paper_files pf ON p.id = pf.paper_id
                LEFT JOIN pdf_files f ON pf.pdf_file_id = f.id
                WHERE pt.tag_id = ?
                ORDER BY p.updated_at DESC
            """, (tag_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_papers_by_tag_name(self, tag_name: str) -> List[Dict[str, Any]]:
        """根据标签名获取论文列表"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.*, f.path as file_path, f.filename as file_name, f.parse_status, f.sha256
                FROM papers p
                JOIN paper_tags pt ON p.id = pt.paper_id
                JOIN tags t ON pt.tag_id = t.id
                LEFT JOIN paper_files pf ON p.id = pf.paper_id
                LEFT JOIN pdf_files f ON pf.pdf_file_id = f.id
                WHERE t.name = ?
                ORDER BY p.updated_at DESC
            """, (tag_name,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== Patent 相关方法 ==========
    
    def get_all_patents(self) -> List[Dict[str, Any]]:
        """获取所有专利"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM patents ORDER BY sort_order ASC, updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_patent_by_id(self, patent_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取专利"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM patents WHERE id = ?", (patent_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def upsert_patent(self, title: str = None, patent_type: str = '发明',
                      patent_number: str = None, grant_number: str = None,
                      inventors: str = None, patentee: str = None,
                      application_date: str = None, grant_date: str = None,
                      abstract: str = None, url: str = None, file_path: str = None,
                      tags: str = None, confidence: float = 100) -> int:
        """插入或更新专利"""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO patents (title, patent_type, patent_number, grant_number, inventors, patentee,
                    application_date, grant_date, abstract, url, file_path, tags, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
            """, (title, patent_type, patent_number, grant_number, inventors, patentee,
                  application_date, grant_date, abstract, url, file_path, tags, confidence))
            return cursor.lastrowid
    
    def update_patent(self, patent_id: int, **kwargs):
        """更新专利字段"""
        allowed = ['title', 'patent_type', 'patent_number', 'grant_number', 'inventors', 'patentee',
                   'application_date', 'grant_date', 'abstract', 'url', 'file_path', 'tags', 'confidence']
        kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        if not kwargs:
            return
        kwargs['updated_at'] = 'strftime(\'%s\', \'now\')'
        set_clause = ', '.join([f"{k} = ?" for k in kwargs])
        values = list(kwargs.values())
        values.append(patent_id)
        with self.connection() as conn:
            conn.execute(f"UPDATE patents SET {set_clause} WHERE id = ?", values)
    
    def delete_patent(self, patent_id: int):
        """删除专利"""
        with self.connection() as conn:
            conn.execute("DELETE FROM patents WHERE id = ?", (patent_id,))
    
    # ========== Software 相关方法 ==========
    
    def get_all_softwares(self) -> List[Dict[str, Any]]:
        """获取所有软著"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM softwares ORDER BY sort_order ASC, updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_software_by_id(self, software_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取软著"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM softwares WHERE id = ?", (software_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def upsert_software(self, software_name: str = None, title: str = None, registration_number: str = None,
                        version: str = None, copyright_holder: str = None,
                        development_date: str = None, rights_scope: str = None,
                        abstract: str = None, url: str = None, file_path: str = None,
                        tags: str = None, confidence: float = 100) -> int:
        """插入或更新软著"""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO softwares (software_name, title, registration_number, version, copyright_holder,
                    development_date, rights_scope, abstract, url, file_path, tags, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
            """, (software_name, title, registration_number, version, copyright_holder,
                  development_date, rights_scope, abstract, url, file_path, tags, confidence))
            return cursor.lastrowid
    
    def update_software(self, software_id: int, **kwargs):
        """更新软著字段"""
        allowed = ['software_name', 'title', 'registration_number', 'version', 'copyright_holder',
                   'development_date', 'rights_scope', 'abstract', 'url', 'file_path', 'tags', 'confidence']
        kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        if not kwargs:
            return
        kwargs['updated_at'] = 'strftime(\'%s\', \'now\')'
        set_clause = ', '.join([f"{k} = ?" for k in kwargs])
        values = list(kwargs.values())
        values.append(software_id)
        with self.connection() as conn:
            conn.execute(f"UPDATE softwares SET {set_clause} WHERE id = ?", values)
    
    def delete_software(self, software_id: int):
        """删除软著"""
        with self.connection() as conn:
            conn.execute("DELETE FROM softwares WHERE id = ?", (software_id,))
    
    # ========== Patent Tag 相关方法 ==========
    
    def get_patent_tags(self, patent_id: int) -> List[Dict[str, Any]]:
        """获取专利的所有标签"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT t.* FROM tags t
                JOIN patent_tags pt ON t.id = pt.tag_id
                WHERE pt.patent_id = ?
                ORDER BY t.name
            """, (patent_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def add_tag_to_patent(self, patent_id: int, tag_id: int):
        """给专利添加标签"""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO patent_tags (patent_id, tag_id) VALUES (?, ?)",
                (patent_id, tag_id)
            )
    
    def remove_tag_from_patent(self, patent_id: int, tag_id: int):
        """从专利移除标签"""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM patent_tags WHERE patent_id = ? AND tag_id = ?",
                (patent_id, tag_id)
            )
    
    def set_patent_tags(self, patent_id: int, tag_names: List[str]):
        """设置专利的标签（替换所有现有标签）"""
        with self.connection() as conn:
            conn.execute("DELETE FROM patent_tags WHERE patent_id = ?", (patent_id,))
            for tag_name in tag_names:
                tag_name = tag_name.strip()
                if tag_name:
                    cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    row = cursor.fetchone()
                    if row:
                        tag_id = row[0]
                    else:
                        cursor = conn.execute(
                            "INSERT INTO tags (name, color, category) VALUES (?, ?, ?)",
                            (tag_name, '#e74c3c', 'patent')
                        )
                        tag_id = cursor.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO patent_tags (patent_id, tag_id) VALUES (?, ?)",
                        (patent_id, tag_id)
                    )
    
    def get_patents_by_tag_name(self, tag_name: str) -> List[Dict[str, Any]]:
        """根据标签名获取专利列表"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.* FROM patents p
                JOIN patent_tags pt ON p.id = pt.patent_id
                JOIN tags t ON pt.tag_id = t.id
                WHERE t.name = ?
                ORDER BY p.updated_at DESC
            """, (tag_name,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_patent_tags(self) -> List[Dict[str, Any]]:
        """获取所有专利相关的标签"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT DISTINCT t.* FROM tags t
                JOIN patent_tags pt ON t.id = pt.tag_id
                ORDER BY t.name
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== Software Tag 相关方法 ==========
    
    def get_software_tags(self, software_id: int) -> List[Dict[str, Any]]:
        """获取软著的所有标签"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT t.* FROM tags t
                JOIN software_tags st ON t.id = st.tag_id
                WHERE st.software_id = ?
                ORDER BY t.name
            """, (software_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def add_tag_to_software(self, software_id: int, tag_id: int):
        """给软著添加标签"""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO software_tags (software_id, tag_id) VALUES (?, ?)",
                (software_id, tag_id)
            )
    
    def remove_tag_from_software(self, software_id: int, tag_id: int):
        """从软著移除标签"""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM software_tags WHERE software_id = ? AND tag_id = ?",
                (software_id, tag_id)
            )
    
    def set_software_tags(self, software_id: int, tag_names: List[str]):
        """设置软著的标签（替换所有现有标签）"""
        with self.connection() as conn:
            conn.execute("DELETE FROM software_tags WHERE software_id = ?", (software_id,))
            for tag_name in tag_names:
                tag_name = tag_name.strip()
                if tag_name:
                    cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    row = cursor.fetchone()
                    if row:
                        tag_id = row[0]
                    else:
                        cursor = conn.execute(
                            "INSERT INTO tags (name, color, category) VALUES (?, ?, ?)",
                            (tag_name, '#f39c12', 'software')
                        )
                        tag_id = cursor.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO software_tags (software_id, tag_id) VALUES (?, ?)",
                        (software_id, tag_id)
                    )
    
    def get_softwares_by_tag_name(self, tag_name: str) -> List[Dict[str, Any]]:
        """根据标签名获取软著列表"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT s.* FROM softwares s
                JOIN software_tags st ON s.id = st.software_id
                JOIN tags t ON st.tag_id = t.id
                WHERE t.name = ?
                ORDER BY s.updated_at DESC
            """, (tag_name,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_software_tags(self) -> List[Dict[str, Any]]:
        """获取所有软著相关的标签"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT DISTINCT t.* FROM tags t
                JOIN software_tags st ON t.id = st.tag_id
                ORDER BY t.name
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== 排序相关方法 ==========
    
    def swap_sort_order(self, table: str, id1: int, id2: int):
        """交换两条记录的sort_order"""
        if table not in ['papers', 'patents', 'softwares']:
            raise ValueError(f"Invalid table: {table}")
        
        with self.connection() as conn:
            # 获取两条记录的sort_order
            cursor = conn.execute(f"SELECT id, sort_order FROM {table} WHERE id IN (?, ?)", (id1, id2))
            rows = cursor.fetchall()
            if len(rows) != 2:
                return False
            
            order1 = rows[0][1] or 0
            order2 = rows[1][1] or 0
            
            # 交换sort_order
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (order2, rows[0][0]))
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (order1, rows[1][0]))
            return True
    
    def move_item_up(self, table: str, item_id: int, current_data: List[Dict]) -> bool:
        """将项目上移一位"""
        if table not in ['papers', 'patents', 'softwares']:
            raise ValueError(f"Invalid table: {table}")
        
        # 找到当前项目在列表中的位置
        current_idx = None
        for i, item in enumerate(current_data):
            if item['id'] == item_id:
                current_idx = i
                break
        
        if current_idx is None or current_idx == 0:
            return False  # 已经在最上面或找不到
        
        # 获取上一个项目
        prev_item = current_data[current_idx - 1]
        
        # 交换sort_order
        with self.connection() as conn:
            current_order = current_data[current_idx].get('sort_order') or current_idx
            prev_order = prev_item.get('sort_order') or (current_idx - 1)
            
            # 如果sort_order相同或未设置，使用索引作为新的sort_order
            if current_order == prev_order:
                current_order = current_idx
                prev_order = current_idx - 1
            
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (prev_order, item_id))
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (current_order, prev_item['id']))
        
        return True
    
    def move_item_down(self, table: str, item_id: int, current_data: List[Dict]) -> bool:
        """将项目下移一位"""
        if table not in ['papers', 'patents', 'softwares']:
            raise ValueError(f"Invalid table: {table}")
        
        # 找到当前项目在列表中的位置
        current_idx = None
        for i, item in enumerate(current_data):
            if item['id'] == item_id:
                current_idx = i
                break
        
        if current_idx is None or current_idx >= len(current_data) - 1:
            return False  # 已经在最下面或找不到
        
        # 获取下一个项目
        next_item = current_data[current_idx + 1]
        
        # 交换sort_order
        with self.connection() as conn:
            current_order = current_data[current_idx].get('sort_order') or current_idx
            next_order = next_item.get('sort_order') or (current_idx + 1)
            
            # 如果sort_order相同或未设置，使用索引作为新的sort_order
            if current_order == next_order:
                current_order = current_idx
                next_order = current_idx + 1
            
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (next_order, item_id))
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (current_order, next_item['id']))
        
        return True
    
    def reset_sort_order(self, table: str):
        """重置表的sort_order为默认顺序（按updated_at DESC）"""
        if table not in ['papers', 'patents', 'softwares']:
            raise ValueError(f"Invalid table: {table}")
        
        with self.connection() as conn:
            # 获取所有记录按updated_at排序
            cursor = conn.execute(f"SELECT id FROM {table} ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            
            # 重新设置sort_order
            for i, row in enumerate(rows):
                conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (i, row[0]))
    
    # ========== 统计数据方法 ==========
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计数据"""
        stats = {
            'papers': {'total': 0, 'journal': 0, 'conference': 0, 'other': 0},
            'patents': {'total': 0},
            'softwares': {'total': 0},
            'yearly': {},
            'journals': {}
        }
        
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            
            # 论文统计
            cursor = conn.execute("SELECT COUNT(*) as count, publication_type FROM papers GROUP BY publication_type")
            for row in cursor.fetchall():
                pt = row['publication_type'] or 'other'
                stats['papers'][pt] = row['count']
                stats['papers']['total'] += row['count']
            
            # 专利统计
            cursor = conn.execute("SELECT COUNT(*) as count FROM patents")
            stats['patents']['total'] = cursor.fetchone()[0]
            
            # 软著统计
            cursor = conn.execute("SELECT COUNT(*) as count FROM softwares")
            stats['softwares']['total'] = cursor.fetchone()[0]
            
            # 年度统计
            cursor = conn.execute("SELECT year, COUNT(*) as count FROM papers WHERE year IS NOT NULL GROUP BY year")
            for row in cursor.fetchall():
                stats['yearly'][str(row['year'])] = row['count']
            
            # 期刊分布
            cursor = conn.execute("SELECT venue, COUNT(*) as count FROM papers WHERE venue IS NOT NULL AND venue != '' GROUP BY venue ORDER BY count DESC LIMIT 10")
            for row in cursor.fetchall():
                stats['journals'][row['venue']] = row['count']
        
        return stats
    
    # ========== 全文搜索相关方法 ==========
    
    def save_fulltext(self, pdf_file_id: int, content: str):
        """保存PDF全文内容"""
        with self.connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pdf_fulltext (pdf_file_id, content, indexed_at)
                VALUES (?, ?, strftime('%s', 'now'))
            """, (pdf_file_id, content))
    
    def get_fulltext(self, pdf_file_id: int) -> Optional[str]:
        """获取PDF全文内容"""
        with self.connection() as conn:
            cursor = conn.execute("SELECT content FROM pdf_fulltext WHERE pdf_file_id = ?", (pdf_file_id,))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def search_fulltext(self, keyword: str) -> List[Dict[str, Any]]:
        """全文搜索"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT p.*, f.path as rel_path, f.filename, ft.content,
                       INSTR(LOWER(ft.content), LOWER(?)) as match_pos
                FROM pdf_fulltext ft
                JOIN pdf_files f ON ft.pdf_file_id = f.id
                LEFT JOIN paper_files pf ON f.id = pf.pdf_file_id
                LEFT JOIN papers p ON pf.paper_id = p.id
                WHERE LOWER(ft.content) LIKE LOWER(?)
                ORDER BY p.year DESC, p.title
            """, (keyword, f'%{keyword}%'))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_unindexed_pdfs(self) -> List[Dict[str, Any]]:
        """获取未建立全文索引的PDF"""
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT f.* FROM pdf_files f
                LEFT JOIN pdf_fulltext ft ON f.id = ft.pdf_file_id
                WHERE ft.id IS NULL AND f.parse_status = 'success'
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_fulltext_stats(self) -> Dict[str, int]:
        """获取全文索引统计"""
        with self.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM pdf_files WHERE parse_status = 'success'").fetchone()[0]
            indexed = conn.execute("SELECT COUNT(*) FROM pdf_fulltext").fetchone()[0]
            return {'total': total, 'indexed': indexed}

