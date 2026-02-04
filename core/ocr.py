import logging
import base64
import requests
import json
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_ocr_config():
    """从preferences.json获取OCR配置，如果没有则回退到config.py"""
    # 优先从preferences.json读取
    config_path = 'preferences.json'
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            ocr_engines = settings.get('ocr_engines', {})
            current = ocr_engines.get('current', {})
            url = current.get('url', '').strip()
            key = current.get('key', '').strip()
            if url and key:
                return url, key
        except Exception as e:
            logger.warning(f"Failed to read preferences.json: {e}")
    
    # 回退到config.py
    try:
        import config
        return config.OCR_API_URL, config.OCR_API_KEY
    except:
        return '', ''

def ocr_pdf_page(pdf_path: str, page_num: int = 0) -> str:
    ocr_url, ocr_key = get_ocr_config()
    
    if not ocr_key or not ocr_url:
        logger.warning("OCR API not configured")
        return "[OCR Error] OCR 未配置，请在 设置 → 扫描设置 中配置OCR服务"

    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            doc.close()
            return f"[OCR Error] 页码超出范围 (共 {len(doc)} 页)"

        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes()
        doc.close()

        img_base64 = base64.b64encode(img_bytes).decode('ascii')

        headers = {
            "Authorization": f"token {ocr_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "file": img_base64,
            "fileType": 1
        }

        logger.info(f"调用OCR API: {ocr_url}")
        from core.proxy import get_proxies
        proxies = get_proxies()
        response = requests.post(
            ocr_url,
            json=payload,
            headers=headers,
            timeout=60,
            proxies=proxies
        )

        logger.info(f"OCR响应状态码: {response.status_code}")

        if response.status_code != 200:
            return f"[OCR Error] HTTP {response.status_code}: {response.text[:200]}"

        result = response.json()
        logger.info(f"OCR响应内容: {json.dumps(result, ensure_ascii=False)[:500]}")

        if "result" in result:
            texts = []
            for item in result.get("result", {}).get("layoutParsingResults", []):
                text = item.get("markdown", {}).get("text", "")
                if text:
                    texts.append(text)
            if texts:
                return "\n\n".join(texts)
            return "[OCR Warning] 未识别到文本"
        elif "error" in result:
            return f"[OCR Error] {result['error']}"
        else:
            return f"[OCR Result] {json.dumps(result, ensure_ascii=False)[:300]}"

    except requests.exceptions.Timeout:
        logger.error("OCR请求超时")
        return "[OCR Error] 请求超时 (60秒)"
    except requests.exceptions.RequestException as e:
        logger.error(f"OCR网络请求失败: {e}")
        return f"[OCR Error] 网络请求失败: {str(e)}"
    except json.JSONDecodeError as e:
        logger.error(f"OCR响应解析失败: {e}")
        return f"[OCR Error] 响应解析失败: {str(e)}"
    except Exception as e:
        logger.error(f"OCR处理失败: {e}")
        return f"[OCR Error] {str(e)}"

def extract_text_via_ocr(pdf_path: str, page_num: int = 0) -> str:
    return ocr_pdf_page(pdf_path, page_num)

def is_ocr_configured() -> bool:
    """检查OCR是否已配置"""
    url, key = get_ocr_config()
    return bool(url and key)
