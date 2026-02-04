import json
import time
import logging
import requests
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
import re
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def make_request(url: str, params: Dict = None, headers: Dict = None, 
                 timeout: int = 10, retries: int = 2) -> Optional[Dict]:
    from core.proxy import get_proxies
    
    headers = headers or {}
    headers['User-Agent'] = config.RESOLVER_USER_AGENT
    headers['Accept'] = 'application/json'
    
    proxies = get_proxies()
    
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, 
                                    timeout=timeout, proxies=proxies)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            wait_time = (2 ** attempt) * 1
            logger.warning(f"Request failed (attempt {attempt+1}/{retries}): {e}, retry in {wait_time}s")
            if attempt < retries - 1:
                time.sleep(wait_time)
    return None

def format_author_from_parts(family: str, given: str) -> str:
    """格式化作者姓名，Crossref格式：family=姓, given=名 → '姓, 名'
    中文名保持原样输出
    """
    family = (family or '').strip()
    given = (given or '').strip()
    
    # 如果姓或名包含中文字符，保持原样输出
    if any('\u4e00' <= c <= '\u9fff' for c in family + given):
        if family and given:
            return f"{family}{given}"
        elif family:
            return family
        elif given:
            return given
        return ''
    
    if family and given:
        return f"{family}, {given}"
    elif family:
        return family
    elif given:
        return given
    return ''

def query_crossref_by_doi(doi: str) -> Optional[Dict]:
    """通过DOI直接查询Crossref获取完整元数据"""
    if not doi:
        return None
    url = f"{config.CROSSREF_API_URL}/{quote(doi)}"
    result = make_request(url)
    if result and 'message' in result:
        item = result['message']
        authors_list = []
        for a in item.get('author', []):
            if a:
                formatted = format_author_from_parts(a.get('family', ''), a.get('given', ''))
                if formatted:
                    authors_list.append(formatted)
        
        # 获取卷、期、页码
        volume = None
        issue = None
        pages = None
        
        volume_info = item.get('volume', '')
        if volume_info:
            volume = str(volume_info)
        
        issue_info = item.get('issue', '')
        if issue_info:
            issue = str(issue_info)
        
        page_info = item.get('page', '')
        if page_info:
            pages = str(page_info)
        
        return {
            'doi': item.get('DOI'),
            'title': item.get('title', [''])[0] if item.get('title') else '',
            'authors': '; '.join(authors_list),
            'year': int(item.get('published-print', {}).get('date-parts', [[0]])[0][0]) if item.get('published-print') else None,
            'year_online': int(item.get('published-online', {}).get('date-parts', [[0]])[0][0]) if item.get('published-online') else None,
            'venue': item.get('container-title', [''])[0] if item.get('container-title') else '',
            'url': item.get('URL', ''),
            'type': item.get('type', 'article'),
            'volume': volume,
            'issue': issue,
            'pages': pages
        }
    return None

def query_crossref(title: str = None, authors: str = None, year: int = None, 
                   venue: str = None) -> List[Dict]:
    """查询Crossref API"""
    query_parts = []
    if title:
        query_parts.append(title)
    if authors:
        first_author = authors.split(';')[0].strip().split()[-1]
        query_parts.append(first_author)
    if year:
        query_parts.append(str(year))
    
    query = ' '.join(query_parts) if query_parts else ''
    if not query:
        return []
    
    url = config.CROSSREF_API_URL
    params = {
        'query.bibliographic': query[:500],
        'rows': 5,
        'mailto': config.RESOLVER_EMAIL
    }
    
    result = make_request(url, params)
    if result and 'message' in result and 'items' in result['message']:
        items = []
        for item in result['message']['items'][:5]:
            authors_list = []
            for a in item.get('author', []):
                if a:
                    formatted = format_author_from_parts(a.get('family', ''), a.get('given', ''))
                    if formatted:
                        authors_list.append(formatted)
            items.append({
                'doi': item.get('DOI'),
                'title': item.get('title', [''])[0] if item.get('title') else '',
                'authors': '; '.join(authors_list),
                'year': int(item.get('published-print', {}).get('date-parts', [[0]])[0][0]) if item.get('published-print') else None,
                'venue': item.get('container-title', [''])[0] if item.get('container-title') else '',
                'score': item.get('score', 0),
                'url': item.get('URL', '')
            })
        return items
    return []

def format_author_from_display_name(name: str) -> str:
    """格式化OpenAlex显示名称：'FirstName LastName' → 'LastName, FirstName'
    中文名保持原样输出
    """
    if not name:
        return ''
    
    # 如果包含中文字符，保持原样
    if any('\u4e00' <= c <= '\u9fff' for c in name):
        return name.strip()
    
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name

def query_openalex(title: str = None, year: int = None) -> List[Dict]:
    if not title:
        return []
    
    query = f'title.search:"{title}"'
    if year:
        query += f' AND publication_year:{year}'
    
    url = f"{config.OPENALEX_API_URL}?filter={quote(query)}&per-page=5"
    
    result = make_request(url)
    if result and 'results' in result:
        items = []
        for work in result['results'][:5]:
            authors_list = []
            for a in work.get('authorships', [])[:3]:
                display_name = a.get('display_name', '')
                formatted = format_author_from_display_name(display_name)
                if formatted:
                    authors_list.append(formatted)
            items.append({
                'doi': work.get('doi'),
                'title': work.get('title'),
                'authors': '; '.join(authors_list),
                'year': work.get('publication_year'),
                'venue': work.get('host_venue', {}).get('display_name', '') if work.get('host_venue') else '',
                'score': work.get('relevance_score', 0),
                'url': work.get('doi') or work.get('id', '')
            })
        return items
    return []

def normalize_title(title: str) -> str:
    if not title:
        return ''
    return re.sub(r'[^\w\s]', '', title.lower())

def title_similarity(t1: str, t2: str) -> float:
    if not t1 or not t2:
        return 0.0
    s1 = normalize_title(t1)
    s2 = normalize_title(t2)
    words1 = set(s1.split())
    words2 = set(s2.split())
    if not words1 or not words2:
        return 0.0
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union * 100 if union > 0 else 0.0

def calculate_confidence(paper: Dict, candidate: Dict) -> float:
    score = 0
    
    title_sim = title_similarity(paper.get('title'), candidate.get('title'))
    score += title_sim * 0.4
    
    paper_year = paper.get('year')
    cand_year = candidate.get('year')
    if paper_year and cand_year:
        if paper_year == cand_year:
            score += 20
        elif abs(paper_year - cand_year) <= 1:
            score += 10
    
    p_authors = (paper.get('authors') or '').lower().split(';')[0].strip()
    c_authors = (candidate.get('authors') or '').lower().split(';')[0].strip()
    if p_authors and c_authors:
        if p_authors[:10] == c_authors[:10]:
            score += 20
        elif p_authors.split() and c_authors.split() and p_authors.split()[-1] == c_authors.split()[-1]:
            score += 10
    
    p_venue = (paper.get('venue') or '').lower()
    c_venue = (candidate.get('venue') or '').lower()
    if p_venue and c_venue and any(w in c_venue for w in p_venue.split()[:3]):
        score += 20
    
    return min(score, 100)

def resolve_doi(paper: Dict) -> Tuple[Optional[str], float, str, Dict]:
    """
    解析DOI，返回 (doi, confidence, source, full_metadata)
    如果有DOI，优先通过DOI直接查询获取完整元数据
    """
    pdf_doi = paper.get('doi')
    
    if pdf_doi:
        by_doi = query_crossref_by_doi(pdf_doi)
        if by_doi:
            logger.info(f"Found metadata by DOI: {pdf_doi}")
            return pdf_doi, 100, 'doi_lookup', by_doi
    
    results = []
    if paper.get('title'):
        results.extend(query_crossref(
            paper.get('title'), paper.get('authors'), 
            paper.get('year'), paper.get('venue')
        ))
        results.extend(query_openalex(paper.get('title'), paper.get('year')))
    
    if not results:
        return None, 0, 'none', {}
    
    best_match = None
    best_score = 0
    for candidate in results:
        score = calculate_confidence(paper, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate
    
    if best_match and best_score >= config.DOI_MATCH_THRESHOLD:
        logger.info(f"Auto-matched DOI: {best_match.get('doi')} (score: {best_score})")
        return best_match['doi'], best_score, 'auto', best_match
    elif best_match:
        logger.info(f"Candidate found but below threshold: {best_match.get('doi')} (score: {best_score})")
        return None, best_score, 'review', best_match
    
    return None, 0, 'none', {}


CONFERENCE_KEYWORDS = [
    'proceedings', 'conference', 'ccs', 'ndss', 'sp', 'oakland', 
    'usenix security', ' ieee symposium', 'acm conference', 
    'icml', 'neurips', 'cvpr', 'iccv', 'eccv', 'iclr',
    'acl', 'emnlp', 'naacl', 'ijcai', 'aaai', 'sigir',
    'kdd', 'www', 'icde', 'vldb', 'sigmod', 'icdm',
    'icassp', 'interspeech', 'icra', 'iros',
    'workshop', 'symposium', 'colloquium'
]

JOURNAL_KEYWORDS = [
    'journal', 'transactions', 'letters', 'ieee', 'acm', 
    'elsevier', 'springer', 'wiley', 'taylor', 'francis',
    'scie', 'sci', 'nature', 'science', 'cell',
    'physica', 'applied physics', 'review'
]


def detect_publication_type(venue: str) -> str:
    """
    根据出版物名称自动检测是期刊还是会议
    返回: 'journal', 'conference', 'book', 或 'other'
    """
    if not venue:
        return 'other'
    
    venue_lower = venue.lower().strip()
    
    for kw in CONFERENCE_KEYWORDS:
        if kw in venue_lower:
            return 'conference'
    
    for kw in JOURNAL_KEYWORDS:
        if kw in venue_lower:
            return 'journal'
    
    return 'other'
