-- PDF文件表
CREATE TABLE IF NOT EXISTS pdf_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    parse_status TEXT DEFAULT 'pending' CHECK(parse_status IN ('pending', 'success', 'needs_review', 'needs_ocr', 'failed')),
    parse_error TEXT,
    added_at REAL DEFAULT (strftime('%s', 'now')),
    last_scanned_at REAL DEFAULT (strftime('%s', 'now'))
);

-- 文献元数据表
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    authors TEXT,
    year INTEGER,
    venue TEXT,
    doi TEXT UNIQUE,
    url TEXT,
    entry_type TEXT DEFAULT 'article',
    publication_type TEXT DEFAULT 'journal',
    bibtex_key TEXT,
    confidence REAL DEFAULT 0,
    source TEXT DEFAULT 'pdf',
    impact_factor REAL,
    volume TEXT,
    issue TEXT,
    pages TEXT,
    abstract TEXT,
    notes TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- PDF与文献关联表
CREATE TABLE IF NOT EXISTS paper_files (
    paper_id INTEGER NOT NULL,
    pdf_file_id INTEGER NOT NULL,
    UNIQUE(paper_id, pdf_file_id),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (pdf_file_id) REFERENCES pdf_files(id) ON DELETE CASCADE
);

-- 专利表
CREATE TABLE IF NOT EXISTS patents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    patent_type TEXT DEFAULT '发明',
    patent_number TEXT,
    grant_number TEXT,  -- 授权公告号，如：CN116055099B
    inventors TEXT,
    patentee TEXT,
    application_date TEXT,
    grant_date TEXT,
    abstract TEXT,
    url TEXT,
    file_path TEXT,
    tags TEXT,
    confidence REAL DEFAULT 100,
    sort_order INTEGER DEFAULT 0,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- 专利证书文件表
CREATE TABLE IF NOT EXISTS patent_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    added_at REAL DEFAULT (strftime('%s', 'now'))
);

-- 专利与证书关联表
CREATE TABLE IF NOT EXISTS patent_files_link (
    patent_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    UNIQUE(patent_id, file_id),
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES patent_files(id) ON DELETE CASCADE
);

-- 软著表
CREATE TABLE IF NOT EXISTS softwares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
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
    sort_order INTEGER DEFAULT 0,
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);

-- 软著证书文件表
CREATE TABLE IF NOT EXISTS software_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    added_at REAL DEFAULT (strftime('%s', 'now'))
);

-- 软著与证书关联表
CREATE TABLE IF NOT EXISTS software_files_link (
    software_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    UNIQUE(software_id, file_id),
    FOREIGN KEY (software_id) REFERENCES softwares(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES software_files(id) ON DELETE CASCADE
);

-- 期刊影响因子表
CREATE TABLE IF NOT EXISTS journal_impact_factors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_name TEXT UNIQUE NOT NULL,
    impact_factor REAL,
    query_date REAL DEFAULT (strftime('%s', 'now'))
);

-- 标签表
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT DEFAULT '#3498db',
    category TEXT DEFAULT 'paper',
    created_at REAL DEFAULT (strftime('%s', 'now'))
);

-- 论文标签关联表
CREATE TABLE IF NOT EXISTS paper_tags (
    paper_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    UNIQUE(paper_id, tag_id),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- 专利标签关联表
CREATE TABLE IF NOT EXISTS patent_tags (
    patent_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    UNIQUE(patent_id, tag_id),
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- 软著标签关联表
CREATE TABLE IF NOT EXISTS software_tags (
    software_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    UNIQUE(software_id, tag_id),
    FOREIGN KEY (software_id) REFERENCES softwares(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_pdf_files_path ON pdf_files(path);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
CREATE INDEX IF NOT EXISTS idx_papers_publication_type ON papers(publication_type);
CREATE INDEX IF NOT EXISTS idx_patents_number ON patents(patent_number);
CREATE INDEX IF NOT EXISTS idx_softwares_number ON softwares(registration_number);
CREATE INDEX IF NOT EXISTS idx_journal_name ON journal_impact_factors(journal_name);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);
CREATE INDEX IF NOT EXISTS idx_paper_tags_paper ON paper_tags(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_tags_tag ON paper_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_patent_tags_patent ON patent_tags(patent_id);
CREATE INDEX IF NOT EXISTS idx_software_tags_software ON software_tags(software_id);

-- PDF全文内容表（用于全文搜索）
CREATE TABLE IF NOT EXISTS pdf_fulltext (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pdf_file_id INTEGER UNIQUE NOT NULL,
    content TEXT,
    indexed_at REAL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (pdf_file_id) REFERENCES pdf_files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pdf_fulltext_file ON pdf_fulltext(pdf_file_id);
