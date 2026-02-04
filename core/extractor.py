import re
import logging
from typing import Dict, Tuple, Optional, List
import fitz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DOI_REGEX = r'\b(10\.\d{4,}/[-a-zA-Z0-9._%+]+)\b'
YEAR_REGEX = r'\b(19[5-9]\d|20[0-2]\d)\b'

OCR_CORRECTIONS = {
    "n'": "'", "Chin": "China", "Hfi": "Hefei", "Xi'n": "Xi'an",
    "Jin'o": "Jin'ao", "Tin": "Ting", "Hichun": "Haichuan", "Zhn": "Zhang",
    "Shn": "Shang", "Zin": "Zian", "Zisn": "Zisen", "Shilon": "Shilong",
    "Ji'o": "Jin'ao", "Yn Liu": "Yang Liu", "Liu Yn": "Yang Liu",
}

INSTITUTION_KEYWORDS = [
    'university', 'institute', 'college', 'school', 'technology',
    'department', 'research', 'laboratory', 'center', 'centre',
    'jiaotong', 'science', 'china', 'hefei', 'ustc', 'stu.', 'mail.',
    'jiot', 'univsity', 'scinc', 'tchnoloy'
]

def clean_author_line(line: str) -> str:
    result = line.strip()
    chars_to_remove = ['$', '*', '^', '#', '{', '}', '\\', '|']
    for c in chars_to_remove:
        result = result.replace(c, '')
    result = re.sub(r'\s+', ' ', result).strip()
    return result

def correct_ocr_text(text: str) -> str:
    corrected = text
    for wrong, right in OCR_CORRECTIONS.items():
        corrected = corrected.replace(wrong, right)
    return corrected

def extract_text_from_pdf(pdf_path: str, max_pages: int = 5) -> Tuple[str, int]:
    text = ""
    total_pages = 0
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        for i in range(min(max_pages, total_pages)):
            page = doc[i]
            text += page.get_text("text") + "\n"
        doc.close()
    except Exception as e:
        logger.error(f"Failed to extract text from {pdf_path}: {e}")
    return text, total_pages

def extract_metadata_from_pdf(pdf_path: str) -> Dict[str, any]:
    result = {
        'title': None, 'authors': None, 'year': None, 'venue': None,
        'doi': None, 'url': None, 'text': '', 'page_count': 0, 'char_count': 0
    }
    try:
        doc = fitz.open(pdf_path)
        meta = doc.metadata or {}
        result['title'] = meta.get('title') or meta.get('subject')
        result['authors'] = meta.get('author')
        text, total_pages = extract_text_from_pdf(pdf_path, max_pages=5)
        result['text'] = text
        result['page_count'] = total_pages
        result['char_count'] = len(text.strip())
        
        doi_from_text = extract_doi_from_text(text)
        if doi_from_text:
            result['doi'] = doi_from_text
        year_from_text = extract_year_from_text(text)
        if year_from_text and not result.get('year'):
            result['year'] = year_from_text
        if not result['title']:
            result['title'] = extract_title_from_text(text)
        if not result['authors']:
            result['authors'] = extract_authors_from_text(text)
        result['venue'] = extract_venue_from_text(text)
        doc.close()
    except Exception as e:
        logger.error(f"Failed to extract metadata from {pdf_path}: {e}")
        result['error'] = str(e)
    return result

def extract_doi_from_text(text: str) -> Optional[str]:
    matches = re.findall(DOI_REGEX, text, re.IGNORECASE)
    if matches:
        for match in matches[:10]:
            if '/' in match and len(match) > 10:
                return match.lower()
    return None

def extract_year_from_text(text: str) -> Optional[int]:
    matches = re.findall(YEAR_REGEX, text)
    if matches:
        year_counts = {}
        for y in matches:
            year_counts[y] = year_counts.get(y, 0) + 1
        if year_counts:
            most_common = max(year_counts.items(), key=lambda x: x[1])
            if most_common[1] >= 2:
                return int(most_common[0])
            years = [int(y) for y in matches]
            if years:
                candidate = max(set(years), key=years.count)
                if 1990 <= candidate <= 2025:
                    return candidate
    return None

def is_chinese_text(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def extract_title_from_ocr(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines[:50]):
        line_clean = re.sub(r'[^\w\s\-–—:()]', '', line)
        if len(line_clean) < 20:
            continue
        if line.lower().startswith('abstract') or line.lower().startswith('introduction'):
            continue
        if any(kw in line.lower() for kw in ['index terms', 'keywords', 'doi:', 'copyright']):
            continue
        if line.startswith('I.') or re.match(r'^\d+\.\s', line):
            continue
        return line
    return None

def extract_authors_from_ocr(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    email_to_name = {}
    
    for i, line in enumerate(lines):
        email_match = re.search(r'([a-zA-Z0-9._-]+@[\w.-]+\.\w+)', line)
        if email_match:
            email = email_match.group(1).lower()
            
            for j in range(i-1, max(0, i-10), -1):
                prev_clean = clean_author_line(lines[j])
                prev_lower = prev_clean.lower()
                
                if not prev_clean or len(prev_clean) < 2:
                    continue
                
                if '@' in prev_clean:
                    continue
                
                is_institution = any(kw in prev_lower for kw in INSTITUTION_KEYWORDS)
                if is_institution:
                    continue
                
                is_chinese = bool(re.search(r'[\u4e00-\u9fff]', prev_clean))
                if is_chinese:
                    email_to_name[email] = prev_clean
                    break
                
                words = prev_clean.split()
                if 1 <= len(words) <= 4:
                    all_alpha = all(c.isalpha() or c in ["'", "-", " "] for c in prev_clean)
                    first_cap = words[0][0].isupper() if words[0] else False
                    has_letter = any(c.isalpha() for c in prev_clean)
                    
                    if all_alpha and first_cap and has_letter:
                        email_to_name[email] = prev_clean
                        break
    
    authors = list(email_to_name.values())
    authors = [correct_ocr_text(a) for a in authors if a]
    
    seen = set()
    unique_authors = []
    for a in authors:
        if a.lower() not in seen:
            seen.add(a.lower())
            unique_authors.append(a)
    
    if unique_authors:
        return '; '.join(unique_authors)
    return None

def extract_emails_from_ocr(text: str) -> List[str]:
    emails = re.findall(r'([a-zA-Z0-9._-]+@[\w.-]+\.\w+)', text)
    return list(set(e.lower() for e in emails))

def extract_venue_from_text(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    venue_keywords = ['conference', 'proceedings', 'journal', 'symposium', 'workshop', 
                      'lecture notes', 'acm', 'ieee', 'springer', 'elsevier', 'arxiv']
    for line in lines[:50]:
        line_lower = line.lower()
        if any(kw in line_lower for kw in venue_keywords) and 5 < len(line) < 150:
            return line
    return None

def extract_title_from_text(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if is_chinese_text(text):
        for i, line in enumerate(lines[:10]):
            line_clean = re.sub(r'[^\w\s\u4e00-\u9fff\-–—]', '', line)
            if 10 < len(line_clean) < 200 and not line.lower().startswith('http'):
                if i > 0 and lines[i-1].strip():
                    continue
                return line
    else:
        for i, line in enumerate(lines[:8]):
            line_clean = re.sub(r'[^\w\s\-–—]', '', line)
            if 15 < len(line_clean) < 400 and not line.lower().startswith('http'):
                if i > 0 and lines[i-1].strip():
                    continue
                return line
        for line in lines[:10]:
            line_clean = re.sub(r'[^\w\s\-–—]', '', line)
            if 20 < len(line_clean) < 300:
                return line
    return None

def extract_authors_from_text(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if is_chinese_text(text):
        for line in lines[:15]:
            if any(kw in line.lower() for kw in ['@', 'mailto', 'http', 'www']):
                continue
            if 4 <= len(line) <= 100 and re.search(r'[\u4e00-\u9fff]', line):
                return line
    else:
        for line in lines[:15]:
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['university', 'institute', '@', 'mailto']):
                continue
            parts = line.split()
            if 2 <= len(parts) <= 8:
                has_letters = sum(1 for p in parts if re.search(r'[a-zA-Z]', p))
                if has_letters >= 2:
                    return line
    return None

def needs_ocr(text: str) -> bool:
    return len(text.strip()) < 200

def format_author_name(author: str) -> str:
    if not author:
        return ''
    parts = author.strip().split()
    if len(parts) >= 2:
        last_name = parts[-1]
        first_name = ' '.join(parts[:-1])
        return f"{last_name}, {first_name}"
    return author

def format_authors_for_bibtex(authors_text: str) -> str:
    if not authors_text:
        return ''
    authors = [a.strip() for a in authors_text.split(';') if a.strip()]
    formatted = [format_author_name(a) for a in authors]
    return ' and '.join(formatted)


# BibKey 生成模式
BIBKEY_MODE_SHORT = 'short'      # author2024
BIBKEY_MODE_MEDIUM = 'medium'    # author2024keyword
BIBKEY_MODE_LONG = 'long'        # author2024keywordtitle (3 words)

# 默认模式
_bibkey_mode = BIBKEY_MODE_MEDIUM

def set_bibkey_mode(mode: str):
    """设置BibKey生成模式"""
    global _bibkey_mode
    if mode in [BIBKEY_MODE_SHORT, BIBKEY_MODE_MEDIUM, BIBKEY_MODE_LONG]:
        _bibkey_mode = mode

def get_bibkey_mode() -> str:
    """获取当前BibKey生成模式"""
    return _bibkey_mode

def generate_bibtex_key(paper: Dict, mode: str = None) -> str:
    """
    生成BibTeX Key
    
    模式:
    - short: author2024 (仅作者+年份)
    - medium: author2024keyword (作者+年份+标题首个关键词)
    - long: author2024keywordtitle (作者+年份+标题前3个词)
    
    Args:
        paper: 论文信息字典
        mode: 生成模式，None则使用全局设置
    """
    use_mode = mode or _bibkey_mode
    
    # 提取第一作者姓氏
    authors = paper.get('authors', '') or ''
    first_author = 'unknown'
    if authors:
        first_author_full = authors.split(';')[0].strip()
        # 处理中文名和英文名
        if re.search(r'[\u4e00-\u9fff]', first_author_full):
            # 中文名：取第一个字（姓）
            first_author = first_author_full[0] if first_author_full else 'unknown'
        else:
            # 英文名：取最后一个词（姓）
            parts = first_author_full.split()
            first_author = parts[-1].lower() if parts else 'unknown'
    
    # 清理作者名中的特殊字符
    first_author = re.sub(r'[^a-zA-Z\u4e00-\u9fff]', '', first_author).lower()
    if not first_author:
        first_author = 'unknown'
    
    # 年份
    year = paper.get('year', '0000') or '0000'
    
    # 根据模式生成key
    if use_mode == BIBKEY_MODE_SHORT:
        return f"{first_author}{year}"
    
    # 提取标题关键词
    title = paper.get('title') or ''
    # 移除常见的停用词
    stopwords = {'a', 'an', 'the', 'of', 'for', 'and', 'or', 'in', 'on', 'to', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'at', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'over'}
    
    # 提取标题中的单词
    title_words = re.findall(r'\b[a-zA-Z]+\b', title.lower())
    # 过滤停用词和太短的词
    keywords = [w for w in title_words if w not in stopwords and len(w) > 2]
    
    if use_mode == BIBKEY_MODE_MEDIUM:
        # 取第一个关键词
        keyword = keywords[0] if keywords else ''
        return f"{first_author}{year}{keyword}"
    
    # BIBKEY_MODE_LONG: 取前3个关键词
    short_title = ''.join(keywords[:3]) if keywords else ''
    return f"{first_author}{year}{short_title}"


# 专利证书正则表达式 - 适配多种格式
# 标准专利号格式: ZL 2022 1 1551727.X 或 ZL202211551727X
# 注意：PDF直接提取可能有空格，如 "专 利 号：ZL 2022 1 1713574.4"
PATENT_NUMBER_REGEX = r'专\s*利\s*号[：:\s]*((?:ZL|zl)[\s\d\.X]+)'
PATENT_NUMBER_REGEX2 = r'(?:ZL|zl)\s*(\d{4})\s*(\d{1})\s*(\d{6,8})\s*[\.。]?\s*([X\d])'
PATENT_NUMBER_REGEX3 = r'专利号[:\s]*((?:ZL|zl)\d{9,15}[\.X\d]?)'
# OCR容错格式
PATENT_NUMBER_REGEX4 = r'专利号[：:\s]*((?:ZL|zl)\d{4,6}\d{5,8}[\.X\d]?)'
# 直接匹配ZL开头的专利号（无前缀）
PATENT_NUMBER_REGEX5 = r'(ZL\s*\d{4}\s*\d{1}\s*\d{6,8}\s*[\.。]?\s*[X\d])'

# 授权公告号格式: CN 116055099 B  或  授 权 公 告 号：
GRANT_NUMBER_REGEX = r'授\s*权\s*公\s*告\s*号[：:\s]*((?:CN|cn)[\s\d]+[A-Za-z]?)'
GRANT_NUMBER_REGEX2 = r'授权公告号[:\s]*([A-Z]{2}\d+[A-Z]?)'

# 申请日/授权日 - 支持空格分隔
APPLICATION_DATE_REGEX = r'(?:专\s*利\s*)?申\s*请\s*日[：:\s]*(\d{4}[年\-\/.]\s*\d{1,2}[月\-\/.]\s*\d{1,2}\s*日?)'
GRANT_DATE_REGEX = r'授\s*权\s*公?\s*告?\s*日[：:\s]*(\d{4}[年\-\/.]\s*\d{1,2}[月\-\/.]\s*\d{1,2}\s*日?)'

# 发明名称 - 支持空格分隔的字段名
INVENTION_TITLE_REGEX = r'(?:发\s*明\s*名\s*称|专\s*利\s*名\s*称)[：:\s]*([^\n]+?)(?=\n专|\n发|\n地|\n申)'

# 专利权人 - 支持空格分隔，匹配到地址或换行
PATENTEE_REGEX = r'专\s*利\s*权\s*人[：:\s]*([^\n]+?)(?=\n|地\s*址|$)'
PATENTEE_REGEX2 = r'申请日时申请人[：:\s]*([^\n]+?)(?=\n|申请日时发明人|$)'

# 发明人 - 关键改进：支持多行，匹配到下一个字段
# PDF格式可能是: 发\n明\n人：刘杨;... 或 发明人：\n刘杨;...
INVENTORS_REGEX = r'发\s*明\s*人[：:\s]*([^专地授国]+?)(?=专\s*利|地\s*址|授\s*权|国家知识|申请日时申请人|$)'
INVENTORS_REGEX2 = r'申请日时发明人[：:\s]*([^国专地]+?)(?=国家知识|专利权|地址|$)'
# 通用格式：匹配 "人：" 或 "人:" 后面跟着分号分隔的名字列表（适配编码问题的PDF）
# 格式如: ��\n��\n�ˣ�名字1;名字2;...  (其中 ��\n��\n�ˣ� 是乱码的 "发\n明\n人：")
INVENTORS_REGEX3 = r'[^\n]*\n[^\n]*\n[^\n]*[：:]\s*([^;；\n]+(?:[;；][^;；\n]+)+)\nר'


def extract_patent_info_from_text(text: str) -> Dict[str, any]:
    """从文本中提取专利信息"""
    result = {
        'patent_number': None,
        'grant_number': None,
        'title': None,
        'inventors': None,
        'patentee': None,
        'application_date': None,
        'grant_date': None,
        'patent_type': '发明'
    }
    
    try:
        text_clean = re.sub(r'\s+', ' ', text)
        
        # 专利号 - 尝试多种格式
        for regex in [PATENT_NUMBER_REGEX, PATENT_NUMBER_REGEX5, PATENT_NUMBER_REGEX3, PATENT_NUMBER_REGEX4]:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                pn = match.group(1).upper()
                # 清理所有空格和中文句号
                pn = re.sub(r'[\s。]+', '', pn)
                # 确保小数点格式正确
                if '.' not in pn and len(pn) >= 14:
                    # 在倒数第二位前插入小数点
                    pn = pn[:-1] + '.' + pn[-1]
                result['patent_number'] = pn
                logger.info(f"Matched patent number: {pn}")
                break
        
        # 如果上面没匹配到，尝试分段匹配
        if not result['patent_number']:
            match = re.search(PATENT_NUMBER_REGEX2, text, re.IGNORECASE)
            if match:
                result['patent_number'] = f"ZL{match.group(1)}{match.group(2)}{match.group(3)}.{match.group(4)}"
        
        # 授权公告号
        for regex in [GRANT_NUMBER_REGEX, GRANT_NUMBER_REGEX2]:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                gn = match.group(1).upper()
                gn = re.sub(r'\s+', '', gn)
                result['grant_number'] = gn
                break
        
        # 发明名称
        match = re.search(INVENTION_TITLE_REGEX, text, re.DOTALL)
        if match:
            title = match.group(1).strip()
            title = re.sub(r'\s+', '', title)  # 移除所有空白
            result['title'] = title[:200]
        
        # 发明人 - 改进清理逻辑
        for regex in [INVENTORS_REGEX, INVENTORS_REGEX2, INVENTORS_REGEX3]:
            match = re.search(regex, text, re.DOTALL | re.IGNORECASE)
            if match:
                inventors = match.group(1).strip()
                # 清理：移除换行，合并空格
                inventors = re.sub(r'[\n\r]+', '', inventors)
                inventors = re.sub(r'\s+', '', inventors)
                # 标准化分隔符
                inventors = re.sub(r'[,，、]+', ';', inventors)
                # 移除末尾多余分号
                inventors = inventors.strip(';')
                if inventors and len(inventors) > 1:
                    result['inventors'] = inventors[:500]
                    logger.info(f"Matched inventors: {inventors[:100]}")
                    break
        
        # 如果还没匹配到发明人，尝试从文本结构中提取
        # 格式: 发明名称后面紧跟着发明人列表（分号分隔）
        if not result['inventors']:
            # 查找分号分隔的名字列表
            # 匹配格式: 任意字符：名字1;名字2;名字3... 
            matches = re.findall(r'[：:]\s*([^;；\n]{1,15}(?:[;；][^;；\n]{1,15})+)', text)
            for m in matches:
                # 清理并验证
                inventors = m.strip()
                inventors = re.sub(r'[\n\r\s]+', '', inventors)
                # 检查是否看起来像名字列表（至少2个分号分隔的项）
                parts = re.split(r'[;；]', inventors)
                if len(parts) >= 2 and all(1 <= len(p) <= 15 for p in parts if p):
                    result['inventors'] = inventors[:500]
                    logger.info(f"Matched inventors (pattern): {inventors[:100]}")
                    break
        
        # 专利权人
        for regex in [PATENTEE_REGEX, PATENTEE_REGEX2]:
            match = re.search(regex, text, re.DOTALL | re.IGNORECASE)
            if match:
                patentee = match.group(1).strip()
                patentee = re.sub(r'[\n\r\s]+', '', patentee)
                result['patentee'] = patentee[:200]
                logger.info(f"Matched patentee: {patentee}")
                break
        
        # 申请日
        match = re.search(APPLICATION_DATE_REGEX, text)
        if match:
            date_str = match.group(1)
            date_str = re.sub(r'\s+', '', date_str)
            result['application_date'] = date_str
        
        # 授权公告日
        match = re.search(GRANT_DATE_REGEX, text)
        if match:
            date_str = match.group(1)
            date_str = re.sub(r'\s+', '', date_str)
            result['grant_date'] = date_str
        
        # 判断专利类型
        if '实用新型' in text:
            result['patent_type'] = '实用新型'
        elif '外观设计' in text:
            result['patent_type'] = '外观设计'
        else:
            result['patent_type'] = '发明'
            
    except Exception as e:
        logger.error(f"Failed to extract patent info: {e}")
    
    return result


# 软著正则 - 支持空格分隔的字段名
# 软 件 名 称： 或 软件名称：
SOFTWARE_NAME_REGEX = r'软\s*件\s*名\s*称[：:\s]*([^\n]+?)(?=\n|简称|V\d|著)'
SOFTWARE_NAME_REGEX2 = r'软件名称[：:\s]*([^\n;；]+)'
VERSION_REGEX = r'[Vv][\d.]+(?:\.\d+)?(?:版)?'
# 登\n记\n号： 或 登记号：
REGISTRATION_NUMBER_REGEX = r'登\s*记\s*号[：:\s]*(\d{4}SR\d+)'
REGISTRATION_NUMBER_REGEX2 = r'(\d{4}SR\d+)'
# 著 作 权 人： 或 著作权人：
COPYRIGHT_HOLDER_REGEX = r'著\s*作\s*权\s*人[：:\s]*([^\n]+?)(?=\n|开发|首次)'
COPYRIGHT_HOLDER_REGEX2 = r'著作权人[：:\s]*([^\n;；]+)'
# 开发完成日期
DEV_COMPLETE_DATE_REGEX = r'开\s*发\s*完\s*成\s*日\s*期[：:\s]*(\d{4}[年\-\/.]\s*\d{1,2}[月\-\/.]\s*\d{1,2}\s*日?)'
DEV_COMPLETE_DATE_REGEX2 = r'开发完成日期[：:\s]*(\d{4}[年\-\/.]\d{1,2}[月\-\/.]\d{1,2}日?)'


def extract_software_info_from_text(text: str) -> Dict[str, any]:
    result = {
        'software_name': None,
        'version': None,
        'registration_number': None,
        'copyright_holder': None,
        'development_date': None
    }
    try:
        # 软件名称
        for regex in [SOFTWARE_NAME_REGEX, SOFTWARE_NAME_REGEX2]:
            match = re.search(regex, text, re.DOTALL)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'\s+', '', name)  # 移除所有空白
                
                # 提取版本号
                version_match = re.search(VERSION_REGEX, text)
                if version_match:
                    version = version_match.group(0)
                    result['version'] = version if version.lower().endswith('版') else version
                    # 从名称中移除版本号
                    name = re.sub(r'[Vv][\d.]+(?:\.\d+)?(?:版)?', '', name).strip()
                
                result['software_name'] = name
                logger.info(f"Matched software name: {name}")
                break
        
        # 登记号
        for regex in [REGISTRATION_NUMBER_REGEX, REGISTRATION_NUMBER_REGEX2]:
            match = re.search(regex, text)
            if match:
                result['registration_number'] = match.group(1)
                logger.info(f"Matched registration number: {match.group(1)}")
                break
        
        # 著作权人
        for regex in [COPYRIGHT_HOLDER_REGEX, COPYRIGHT_HOLDER_REGEX2]:
            match = re.search(regex, text, re.DOTALL)
            if match:
                holder = match.group(1).strip()
                holder = re.sub(r'\s+', '', holder)
                result['copyright_holder'] = holder
                logger.info(f"Matched copyright holder: {holder}")
                break
        
        # 开发完成日期
        for regex in [DEV_COMPLETE_DATE_REGEX, DEV_COMPLETE_DATE_REGEX2]:
            match = re.search(regex, text)
            if match:
                date_str = match.group(1)
                date_str = re.sub(r'\s+', '', date_str)
                result['development_date'] = date_str
                logger.info(f"Matched development date: {date_str}")
                break

    except Exception as e:
        logger.error(f"Failed to extract software copyright info: {e}")

    return result


def is_patent_info_complete(patent_info: Dict[str, any]) -> bool:
    """
    检查专利信息是否完整
    关键字段：专利号、发明名称、发明人、专利权人
    """
    critical_fields = ['patent_number', 'title', 'inventors', 'patentee']
    missing_fields = []
    
    for field in critical_fields:
        if not patent_info.get(field):
            missing_fields.append(field)
    
    if missing_fields:
        logger.warning(f"Patent info incomplete, missing: {missing_fields}")
        return False
    
    return True


def is_software_info_complete(software_info: Dict[str, any]) -> bool:
    """
    检查软著信息是否完整
    关键字段：软件名称、登记号、著作权人、开发完成日期
    """
    critical_fields = ['software_name', 'registration_number', 'copyright_holder', 'development_date']
    missing_fields = []
    
    for field in critical_fields:
        if not software_info.get(field):
            missing_fields.append(field)
    
    if missing_fields:
        logger.warning(f"Software info incomplete, missing: {missing_fields}")
        return False
    
    return True


def is_patent_certificate(text: str) -> bool:
    patent_keywords = ['专利号', '发明名称', '发明人', '专利权人', '申请日', '授权公告日', 'ZL']
    text_lower = text.lower()
    matches = sum(1 for kw in patent_keywords if kw in text)
    return matches >= 3


def validate_patent_number(patent_number: str) -> tuple[bool, str]:
    """
    验证专利号格式
    返回: (是否有效, 错误信息)
    标准格式: ZL + 4位年 + 1位类型 + 7位序号 + . + 1位校验位
    例如: ZL202211551727.X
    """
    if not patent_number or not patent_number.strip():
        return False, "专利号不能为空"
    
    pn = patent_number.strip().upper()
    
    if not pn.startswith('ZL'):
        return False, "专利号必须以'ZL'开头"
    
    pn = pn.replace(' ', '')
    
    if len(pn) != 16:
        return False, f"专利号必须为16位，当前: {len(pn)}位"
    
    if not re.match(r'^ZL\d{4}[1-9]\d{6,7}[.][X\d]$', pn):
        return False, "专利号格式不正确，请检查: ZL202211551727.X"
    
    return True, ""


def is_software_certificate(text: str) -> bool:
    software_keywords = ['软件名称', '登记号', '著作权人', '开发完成日期', 'SR', '软著']
    text_lower = text.lower()
    matches = sum(1 for kw in software_keywords if kw in text)
    return matches >= 3


def extract_certificate_info(certificate_path: str, use_ocr: bool = False) -> Dict[str, any]:
    """
    提取证书信息
    1. 优先使用PDF直接文本提取
    2. 如果关键字段缺失较多，自动尝试OCR补救
    3. use_ocr=True时强制使用OCR
    
    Args:
        certificate_path: 证书文件路径
        use_ocr: 是否强制使用OCR
    """
    from core.ocr import ocr_pdf_page
    result = {
        'type': None,
        'data': {},
        'extraction_method': None
    }

    try:
        text = ""
        ocr_text = None
        
        if certificate_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
            # 图片文件必须使用OCR
            try:
                text = ocr_pdf_page(certificate_path, 0)
                result['extraction_method'] = 'ocr'
            except Exception as e:
                logger.warning(f"OCR failed for image: {e}")
                return result
        elif certificate_path.lower().endswith('.pdf'):
            # PDF文件先尝试直接提取文本
            text, _ = extract_text_from_pdf(certificate_path, max_pages=2)
            result['extraction_method'] = 'pdf_text'
            logger.info(f"PDF direct extraction: {len(text)} chars")
            
            # 如果文本太少，尝试OCR
            if len(text.strip()) < 100:
                try:
                    logger.info(f"PDF text too short, trying OCR...")
                    text = ocr_pdf_page(certificate_path, 0)
                    result['extraction_method'] = 'ocr'
                except Exception as e:
                    logger.warning(f"OCR failed: {e}")
        else:
            # 其他文件直接读取
            with open(certificate_path, 'r', encoding='utf-8') as f:
                text = f.read()
            result['extraction_method'] = 'text_file'

        # 尝试识别专利
        if is_patent_certificate(text):
            result['type'] = 'patent'
            result['data'] = extract_patent_info_from_text(text)
            
            # 检查关键字段缺失情况，如果缺失>=4个则尝试OCR补救
            missing_count = sum(1 for k in ['patent_number', 'title', 'inventors', 'patentee', 'grant_number', 'application_date', 'grant_date'] 
                               if not result['data'].get(k))
            
            if missing_count >= 4 and result['extraction_method'] == 'pdf_text':
                try:
                    logger.info(f"Patent info incomplete (missing {missing_count} fields), trying OCR...")
                    ocr_text = ocr_pdf_page(certificate_path, 0)
                    ocr_result = extract_patent_info_from_text(ocr_text)
                    
                    # 用OCR结果补充缺失字段
                    for key in result['data']:
                        if not result['data'].get(key) and ocr_result.get(key):
                            result['data'][key] = ocr_result[key]
                            logger.info(f"Filled {key} from OCR")
                    
                    result['extraction_method'] = 'pdf+ocr'
                except Exception as e:
                    logger.warning(f"OCR remedy failed: {e}")
            
            logger.info(f"Extracted patent: {result['data'].get('patent_number')}, {result['data'].get('title', '')[:30]}")
            
        elif is_software_certificate(text):
            result['type'] = 'software'
            result['data'] = extract_software_info_from_text(text)
            result['data']['software_name'] = result['data'].get('software_name') or result['data'].get('title')
            
            # 检查关键字段缺失情况，如果缺失>=4个则尝试OCR补救
            missing_count = sum(1 for k in ['software_name', 'registration_number', 'copyright_holder', 'development_date', 'version'] 
                               if not result['data'].get(k))
            
            if missing_count >= 4 and result['extraction_method'] == 'pdf_text':
                try:
                    logger.info(f"Software info incomplete (missing {missing_count} fields), trying OCR...")
                    ocr_text = ocr_pdf_page(certificate_path, 0)
                    ocr_result = extract_software_info_from_text(ocr_text)
                    ocr_result['software_name'] = ocr_result.get('software_name') or ocr_result.get('title')
                    
                    # 用OCR结果补充缺失字段
                    for key in result['data']:
                        if not result['data'].get(key) and ocr_result.get(key):
                            result['data'][key] = ocr_result[key]
                            logger.info(f"Filled {key} from OCR")
                    
                    result['extraction_method'] = 'pdf+ocr'
                except Exception as e:
                    logger.warning(f"OCR remedy failed: {e}")
            
            logger.info(f"Extracted software: {result['data'].get('registration_number')}, {result['data'].get('software_name', '')[:30]}")
        else:
            logger.info(f"No certificate detected in text (first 200 chars): {text[:200]}")

        result['raw_text'] = text

    except Exception as e:
        logger.error(f"Failed to extract certificate info: {e}")
        result['error'] = str(e)

    return result
