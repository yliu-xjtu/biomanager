import logging
import time
from typing import Optional, Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def query_impact_factor(journal_name: str) -> Optional[float]:
    """
    查询期刊影响因子
    优先使用pip impact_factor包，其次使用本地数据库
    """
    if not journal_name or not journal_name.strip():
        return None
    
    journal_clean = journal_name.strip()
    
    try:
        try:
            from impact_factor.core import Factor
            fa = Factor()
            results = fa.search(journal_clean)
            if results and len(results) > 0:
                first = results[0]
                if_value = first.get('factor')
                if if_value and float(if_value) > 0:
                    logger.info(f"[Impact Factor] API: {journal_clean}: {if_value}")
                    return float(if_value)
        except ImportError:
            logger.warning("impact_factor package not installed, trying local DB")
        except Exception as e:
            logger.warning(f"impact_factor package error: {e}")
        
        try:
            from core.journal_if_database import get_impact_factor_from_db
            result = get_impact_factor_from_db(journal_clean)
            if result:
                logger.info(f"[Impact Factor] Local DB: {journal_clean}: {result}")
                return result
        except Exception as e:
            logger.debug(f"Local DB lookup failed: {e}")
        
        try:
            from core.journal_if_database import search_journal_in_db
            results = search_journal_in_db(journal_clean)
            if results:
                first = results[0]
                logger.info(f"[Impact Factor] Fuzzy match: {journal_clean} -> {first['journal_name']}: {first['impact_factor']}")
                return first['impact_factor']
        except Exception as e:
            logger.debug(f"Fuzzy search failed: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to query impact factor for {journal_name}: {e}")
        return None

def batch_query_impact_factors(journals: List[str]) -> Dict[str, float]:
    """
    批量查询期刊影响因子
    """
    results = {}
    for journal in set(journals):
        if journal:
            if_query = query_impact_factor(journal)
            if if_query:
                results[journal] = if_query
            time.sleep(0.1)
    return results
