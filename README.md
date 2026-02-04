# BioManager - 本地文献管理工具

BioManager 是一款本地文献管理工具，帮助科研人员管理论文、专利和软著等学术成果。无需云端同步，所有数据存储在本地SQLite数据库中。

## 功能特性

### 论文管理
- 自动扫描本地PDF文件，提取元数据（标题、作者、年份、期刊等）
- **手动添加论文**：通过DOI或标题搜索，自动获取元数据，支持PDF下载
- 自动查找DOI并补全文献信息（通过Crossref和OpenAlex）
- 支持OCR识别扫描版PDF
- 导出BibTeX、RIS、GB/T 7714格式引用
- 期刊影响因子查询
- 全文搜索功能

### 专利管理
- 自动识别专利证书PDF
- OCR提取专利信息（专利号、发明人、授权日期等）
- 支持标签分类

### 软著管理
- 自动识别软著证书
- OCR提取软著信息（登记号、著作权人等）
- 支持标签分类

### 其他功能
- 深色/浅色主题切换
- 统计报表（年度发文、期刊分布等）
- 数据库备份与恢复
- 代理设置支持

## 截图

（待添加）

## 安装与使用

### 方式一：直接运行（Windows）

1. 下载 `dist/BioManager.exe`
2. 双击运行即可

### 方式二：从源码运行

#### 环境要求
- Python 3.10 或更高版本
- Windows 10/11（主要测试环境）
- macOS / Linux（理论支持，需自行测试）

#### 安装依赖

```bash
pip install PySide6 PyMuPDF requests matplotlib
```

| 依赖包 | 用途 |
|--------|------|
| PySide6 | GUI框架 |
| PyMuPDF (fitz) | PDF解析与文本提取 |
| requests | HTTP请求（DOI解析、OCR） |
| matplotlib | 统计图表绘制 |

#### 运行程序

```bash
python app/app.py
```

### 方式三：macOS / Linux 部署

由于项目主要在Windows上开发测试，macOS/Linux用户需要：

1. **安装Python 3.10+**
   ```bash
   # macOS (使用Homebrew)
   brew install python@3.10
   
   # Ubuntu/Debian
   sudo apt install python3.10 python3.10-venv
   ```

2. **创建虚拟环境（推荐）**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   ```

3. **安装依赖**
   ```bash
   pip install PySide6 PyMuPDF requests matplotlib
   ```

4. **运行程序**
   ```bash
   python app/app.py
   ```

5. **注意事项**
   - macOS可能需要安装额外的Qt依赖
   - 文件路径使用正斜杠 `/`
   - 双击打开PDF功能可能需要调整（使用 `xdg-open` 或 `open` 命令）

### 打包为可执行文件

```bash
pip install pyinstaller
pyinstaller build.spec
```

打包后的文件位于 `dist/BioManager.exe`（Windows）。

## OCR配置

本项目使用百度PaddleOCR服务进行OCR识别。

### 获取API

1. 访问 [百度PaddleOCR](https://aistudio.baidu.com/paddleocr)
2. 注册/登录账号
3. 创建应用，获取API URL和API Key

### 配置方法

**方法一：通过界面配置（推荐）**
1. 打开程序，点击菜单 `设置 → 扫描设置`
2. 在OCR设置区域填入API URL和API Key
3. 点击"测试OCR服务"验证配置
4. 点击"保存"

**方法二：编辑配置文件**

编辑 `config.py`：
```python
OCR_API_KEY = "your-api-key"
OCR_API_URL = "https://xxx.aistudio-app.com/layout-parsing"
```

### 备选方案：Tesseract OCR

如果不想使用在线OCR服务，可以安装本地Tesseract：

1. 下载安装 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
2. 在设置中填入Tesseract路径
3. 程序会在在线OCR不可用时自动回退到Tesseract

## 使用说明

### 首次使用

1. 启动程序，选择"新建数据库"
2. 选择存放文献的文件夹（数据库将创建在该文件夹下）
3. 程序自动扫描文件夹中的PDF文件
4. 扫描完成后，文献显示在主界面

### 手动添加论文

除了扫描本地PDF，还可以通过DOI或标题手动添加论文：

1. 点击菜单 **文件 → 添加论文** 或按 `Ctrl+P`
2. 输入论文的DOI（如 `10.1109/xxx`）或标题
3. 点击"搜索"，程序会从Crossref和OpenAlex检索论文信息
4. 从搜索结果中选择正确的论文
5. 可选：勾选"尝试下载PDF"，程序会尝试下载PDF
6. 点击"添加论文"完成

**PDF下载说明**：
- 支持从多个来源下载：IEEE、Elsevier、Springer、Wiley、ACM等
- 如果您的机构购买了数据库订阅，请确保：
  - 已连接校园网或VPN
  - 或在 **设置 → 代理设置** 中配置机构代理
- 开放获取论文会自动通过Unpaywall下载
- 如果下载失败，仍可添加论文条目，稍后通过右键菜单"绑定PDF文件"手动关联

### 绑定PDF文件

对于没有PDF的论文条目，可以后续绑定：

1. 在论文列表中右键点击论文
2. 选择 **"绑定PDF文件..."**
3. 选择本地的PDF文件
4. 完成绑定

### 拖放添加文件

支持直接拖放PDF文件到软件窗口：

1. 从文件管理器中选择一个或多个PDF文件
2. 拖放到BioManager窗口中
3. 文件会自动复制到文献库根目录
4. 根据当前标签页自动解析：
   - **论文标签页**：自动提取元数据、查找DOI
   - **专利标签页**：尝试OCR识别专利证书
   - **软著标签页**：尝试OCR识别软著证书

### 重命名PDF文件

右键点击论文 → **"重命名PDF文件..."** 可以重命名关联的PDF文件。

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+O | 打开数据库 |
| Ctrl+N | 新建数据库 |
| Ctrl+P | 添加论文 |
| Ctrl+W | 关闭数据库 |
| F5 | 刷新数据库 |
| Ctrl+F | 搜索框聚焦 |
| Enter / 双击 | 打开PDF文件 |
| Delete | 删除选中项目 |
| Ctrl+S | 保存修改 |
| Ctrl+1/2/3 | 切换论文/专利/软著标签 |
| Ctrl+Q | 退出程序 |

### 导出格式

- **BibTeX**: 标准BibTeX格式，可导入EndNote、Zotero等
- **RIS**: EndNote/Zotero兼容格式
- **GB/T 7714**: 中文参考文献标准格式

## 项目结构

```
biomanager/
├── app/                 # 程序入口
│   └── app.py
├── ui/                  # 用户界面
│   ├── main_window.py   # 主窗口
│   ├── table_model.py   # 论文表格模型
│   ├── patent_table_model.py   # 专利表格模型
│   ├── software_table_model.py # 软著表格模型
│   ├── detail_panel.py  # 论文详情面板
│   ├── patent_detail_panel.py  # 专利详情面板
│   ├── software_detail_panel.py # 软著详情面板
│   ├── add_paper_dialog.py # 添加论文对话框
│   └── theme.py         # 主题样式
├── core/                # 核心逻辑
│   ├── scanner.py       # 文件扫描
│   ├── extractor.py     # 元数据抽取
│   ├── resolver.py      # DOI在线解析
│   ├── ocr.py           # OCR接口
│   ├── bibtex.py        # BibTeX生成
│   ├── export.py        # 导出功能
│   ├── proxy.py         # 代理配置
│   ├── journal_impact.py # 影响因子查询
│   └── llm_parser.py    # LLM解析
├── db/                  # 数据层
│   ├── schema.sql       # 数据库结构
│   └── database.py      # 数据库操作
├── csl/                 # 引用样式
│   └── gb-t-7714-2015.csl
├── resources/           # 资源文件
│   └── icons/
├── config.py            # 配置文件
├── startup_dialog.py    # 启动对话框
├── build.spec           # PyInstaller打包配置
└── build.bat            # 打包脚本
```

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| 扫描很慢 | 检查网络连接，或配置代理 |
| DOI解析失败 | 检查网络连接和代理设置 |
| OCR按钮无效 | 需配置OCR API（见上方说明） |
| 无法打开PDF | 检查PDF文件路径是否有效 |
| 表格显示乱码 | 检查系统区域设置，程序支持UTF-8 |

## 技术栈

- **GUI**: PySide6 (Qt for Python)
- **数据库**: SQLite3
- **PDF解析**: PyMuPDF (fitz)
- **在线API**: Crossref, OpenAlex
- **OCR**: 百度PaddleOCR / Tesseract
- **图表**: Matplotlib

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 致谢

- [PySide6](https://doc.qt.io/qtforpython-6/)
- [PyMuPDF](https://pymupdf.readthedocs.io/)
- [Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [OpenAlex API](https://docs.openalex.org/)
- [百度PaddleOCR](https://aistudio.baidu.com/paddleocr)
