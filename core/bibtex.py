import logging
from typing import List, Dict
from xml.etree import ElementTree as ET

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_bibtex_entry(paper: Dict) -> str:
    key = paper.get('bibtex_key') or 'unknown0000'
    entry_type = paper.get('entry_type', 'article')
    
    fields = []
    if paper.get('title'):
        fields.append(f"  title = {{{paper['title']}}}")
    if paper.get('authors'):
        from core.extractor import format_authors_for_bibtex
        authors = format_authors_for_bibtex(paper['authors'])
        fields.append(f"  author = {{{authors}}}")
    if paper.get('year'):
        fields.append(f"  year = {{{paper['year']}}}")
    if paper.get('venue'):
        fields.append(f"  journal = {{{paper['venue']}}}")
    if paper.get('doi'):
        fields.append(f"  doi = {{{paper['doi']}}}")
    if paper.get('url'):
        fields.append(f"  url = {{{paper['url']}}}")
    if paper.get('volume'):
        fields.append(f"  volume = {{{paper['volume']}}}")
    if paper.get('issue'):
        fields.append(f"  number = {{{paper['issue']}}}")
    if paper.get('pages'):
        pages = paper['pages']
        if '--' in pages:
            pages = pages.replace('--', '--')
        fields.append(f"  pages = {{{pages}}}")
    
    return f"@{entry_type}{{{key},\n" + ",\n".join(fields) + "\n}"

def export_bibtex(papers: List[Dict]) -> str:
    entries = [generate_bibtex_entry(p) for p in papers]
    return '\n\n'.join(entries)

def parse_citation_style(csl_path: str) -> ET.Element:
    try:
        tree = ET.parse(csl_path)
        return tree.getroot()
    except Exception as e:
        logger.error(f"Failed to parse CSL: {e}")
        return None

def is_chinese_text(text: str) -> bool:
    """判断是否包含中文字符"""
    return any('\u4e00' <= c <= '\u9fff' for c in text)

def parse_author_name(author: str) -> tuple:
    """解析作者姓名，返回 (姓, 名)
    支持多种格式：
    - "LIU Y." -> ("LIU", "Y")
    - "LIU, Y." -> ("LIU", "Y")
    - "Liu Yang" -> ("LIU", "Yang")
    - "Yang Liu" -> ("LIU", "Yang")
    - 中文名直接返回原名
    """
    author = author.strip()
    
    if not author:
        return ("", "")
    
    if is_chinese_text(author):
        return (author, None)
    
    parts = author.replace(',', ' ').split()
    if len(parts) >= 2:
        part0 = parts[0].upper()
        part1 = parts[1]
        part0_is_upper = part0.isupper() and part0.isalpha()
        part1_is_upper = part1[0].isupper() if part1 else False
        
        if ',' in author or (part0_is_upper and len(part0) > 1 and part1_is_upper):
            if ',' in author:
                idx = author.find(',')
                surname = author[:idx].strip().upper()
                given = author[idx+1:].strip()
            else:
                surname = parts[0].upper()
                given = parts[1]
            given_initial = given[0].upper() if given else ''
            return (surname, given_initial)
        else:
            surname = parts[-1].upper()
            given = parts[0]
            given_initial = given[0].upper() if given else ''
            return (surname, given_initial)
    
    return (author.upper(), "")

def format_author_gbt7714(author: str) -> str:
    """将作者格式化为 GB/T 7714-2015 标准格式：姓, 名首字母.
    中文名保持原样输出
    """
    surname, given_initial = parse_author_name(author)
    
    if surname is None:
        return author
    
    if surname and given_initial:
        return f"{surname} {given_initial}."
    elif surname:
        return f"{surname}."
    return author

def render_gbt7714(paper: Dict, style_root: ET.Element) -> str:
    parts = []
    
    authors = paper.get('authors', '')
    if authors:
        author_list = [a.strip() for a in authors.split(';')]
        formatted_authors = [format_author_gbt7714(a) for a in author_list]
        parts.append(' '.join(formatted_authors))
    
    if paper.get('title'):
        parts.append(paper['title'] + '.')
    
    if paper.get('venue'):
        parts.append(paper['venue'] + ',')
    
    if paper.get('year'):
        parts.append(str(paper['year']) + '.')
    
    if paper.get('volume') or paper.get('issue') or paper.get('pages'):
        vol_issue_parts = []
        if paper.get('volume'):
            vol_issue_parts.append(paper['volume'])
        if paper.get('issue'):
            vol_issue_parts.append('(' + paper['issue'] + ')')
        if vol_issue_parts:
            parts.append(''.join(vol_issue_parts) + ',')
        if paper.get('pages'):
            parts.append(paper['pages'] + '.')
    
    if paper.get('doi'):
        parts.append(f"DOI: {paper['doi']}")
    
    return ' '.join(parts)

def export_gbt7714(papers: List[Dict], csl_path: str = 'csl/gb-t-7714-2015.csl') -> str:
    style_root = parse_citation_style(csl_path)
    if style_root is None:
        logger.warning("CSL parse failed, using fallback rendering")
        return '\n\n'.join([render_gbt7714(p, None) for p in papers])
    
    return '\n\n'.join([render_gbt7714(p, style_root) for p in papers])
