import json
import os
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """这是一篇论文的文本内容，请你从中提取以下信息：
1. 论文标题
2. 作者列表（用分号分隔）
3. 期刊/会议名称
4. 出版年份

请只返回能够明确识别的信息，格式如下（不要添加任何解释）：
标题: xxx
作者: xxx; xxx; xxx
期刊: xxx
年份: xxxx

如果某项信息无法识别，请在该行写"未知"。"""

def load_settings():
    config_path = 'preferences.json'
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'use_llm': False, 'api_url': '', 'api_key': ''}

def parse_with_llm(text: str) -> dict:
    settings = load_settings()
    if not settings.get('use_llm', False):
        return None
    
    api_url = settings.get('api_url', '').strip()
    api_key = settings.get('api_key', '').strip()
    
    if not api_url or not api_key:
        logger.warning("LLM API not configured")
        return None
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    full_prompt = f"{DEFAULT_PROMPT}\n\n论文文本内容：\n{text[:3000]}"
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 500
    }
    
    try:
        from core.proxy import get_proxies
        proxies = get_proxies()
        response = requests.post(api_url, headers=headers, json=data, timeout=60, proxies=proxies)
        if response.status_code == 200:
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            return _parse_llm_response(content)
        else:
            logger.error(f"LLM API error: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return None

def _parse_llm_response(content: str) -> dict:
    result = {'title': None, 'authors': None, 'venue': None, 'year': None}
    
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('标题:'):
            val = line[3:].strip()
            if val and val != '未知':
                result['title'] = val
        elif line.startswith('作者:'):
            val = line[3:].strip()
            if val and val != '未知':
                result['authors'] = val
        elif line.startswith('期刊:'):
            val = line[3:].strip()
            if val and val != '未知':
                result['venue'] = val
        elif line.startswith('年份:'):
            val = line[3:].strip()
            if val and val.isdigit() and len(val) == 4:
                result['year'] = int(val)
    
    return result if any(result.values()) else None
