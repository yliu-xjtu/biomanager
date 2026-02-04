# 配置文件 - OCR与网络API占位

# OCR API配置（预留）
# 使用百度PaddleOCR服务，请前往 https://aistudio.baidu.com/paddleocr 申请API
OCR_API_KEY = ""  # 如使用在线OCR服务，在此填入API Key
OCR_API_URL = ""  # OCR服务地址，例如 https://xxx.aistudio-app.com/layout-parsing

# DOI解析配置
RESOLVER_EMAIL = "researcher@example.com"  # 建议填写真实邮箱以提高API响应
RESOLVER_USER_AGENT = "LocalPDFManager/1.0 (Python)"

# Crossref API
CROSSREF_API_URL = "https://api.crossref.org/works"

# OpenAlex API
OPENALEX_API_URL = "https://api.openalex.org/works"

# CSL样式文件路径
CSL_STYLE_PATH = "csl/gb-t-7714-2015.csl"

# 应用配置
WINDOW_TITLE = "本地 PDF 文献管理器"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# 评分阈值
DOI_MATCH_THRESHOLD = 80  # 低于此分数不自动写入DOI
