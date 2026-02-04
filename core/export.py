import csv
import io


def export_ris(papers):
    """导出论文为RIS格式（EndNote/Zotero兼容）"""
    lines = []
    lines.append("TY  - JOUR")
    
    for paper in papers:
        if paper.get('title'):
            lines.append(f"TI  - {paper['title']}")
        
        if paper.get('authors'):
            authors = paper['authors'].split(';')
            for author in authors:
                author = author.strip()
                if author:
                    lines.append(f"AU  - {author}")
        
        if paper.get('year'):
            lines.append(f"PY  - {paper['year']}")
        
        if paper.get('venue'):
            lines.append(f"JO  - {paper['venue']}")
        
        if paper.get('doi'):
            lines.append(f"DO  - {paper['doi']}")
        
        if paper.get('url'):
            lines.append(f"UR  - {paper['url']}")
        
        if paper.get('volume'):
            lines.append(f"VL  - {paper['volume']}")
        
        if paper.get('issue'):
            lines.append(f"IS  - {paper['issue']}")
        
        if paper.get('pages'):
            pages = paper['pages']
            if '-' in pages:
                sp, ep = pages.split('-', 1)
                lines.append(f"SP  - {sp.strip()}")
                lines.append(f"EP  - {ep.strip()}")
            else:
                lines.append(f"SP  - {pages}")
        
        if paper.get('entry_type'):
            type_map = {
                'article': 'JOUR',
                'inproceedings': 'CONF',
                'book': 'BOOK',
                'phdthesis': 'THES',
                'mastersthesis': 'THES',
            }
            lines.append(f"TY  - {type_map.get(paper['entry_type'], 'JOUR')}")
        
        lines.append("ER  -")
        lines.append("")
    
    return "\n".join(lines)


def export_patents_csv(patents):
    """导出专利为CSV格式"""
    if not patents:
        return ""
    
    fieldnames = [
        'id', 'title', 'patent_type', 'patent_number', 
        'inventors', 'patentee', 'application_date', 'grant_date',
        'abstract', 'url', 'file_path', 'confidence'
    ]
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for patent in patents:
        row = {}
        for field in fieldnames:
            value = patent.get(field, '')
            if value is None:
                value = ''
            row[field] = str(value)
        writer.writerow(row)
    
    return output.getvalue()


def export_softwares_csv(softwares):
    """导出软著为CSV格式"""
    if not softwares:
        return ""
    
    fieldnames = [
        'id', 'title', 'registration_number', 'version',
        'copyright_holder', 'development_date', 'rights_scope',
        'abstract', 'url', 'file_path', 'confidence'
    ]
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for software in softwares:
        row = {}
        for field in fieldnames:
            value = software.get(field, '')
            if value is None:
                value = ''
            row[field] = str(value)
        writer.writerow(row)
    
    return output.getvalue()


def format_patent_gbt7714(patent: dict) -> str:
    """将专利格式化为GB/T 7714-2015标准格式
    
    格式: 发明人. 题名: 专利号[P]. 专利权人. 申请日. 授权日.
    """
    parts = []
    
    inventors = patent.get('inventors', '')
    if inventors:
        inventors_formatted = inventors.replace(';', '. ').replace('；', '. ')
        if not inventors_formatted.endswith('.'):
            inventors_formatted += '.'
        parts.append(inventors_formatted)
    
    title = patent.get('title', '')
    if title:
        parts.append(f"{title}: ")
    
    patent_number = patent.get('patent_number', '')
    if patent_number:
        parts.append(f"{patent_number}[P]. ")
    
    patentee = patent.get('patentee', '')
    if patentee:
        parts.append(f"{patentee}. ")
    
    application_date = patent.get('application_date', '')
    if application_date:
        parts.append(f"{application_date}. ")
    
    grant_date = patent.get('grant_date', '')
    if grant_date:
        parts.append(f"{grant_date}.")
    
    return ''.join(parts).strip()


def export_patents_gbt7714(patents) -> str:
    """导出专利为GB/T 7714-2015格式"""
    if not patents:
        return ""
    return '\n\n'.join([format_patent_gbt7714(p) for p in patents])


def format_software_gbt7714(software: dict) -> str:
    """将软著格式化为GB/T 7714-2015标准格式
    
    格式: 著作权人. 软件名称: 登记号[软著]. 权利范围. 开发完成日期.
    """
    parts = []
    
    copyright_holder = software.get('copyright_holder', '')
    if copyright_holder:
        parts.append(f"{copyright_holder}. ")
    
    software_name = software.get('software_name', '') or software.get('title', '')
    if software_name:
        parts.append(f"{software_name}: ")
    
    registration_number = software.get('registration_number', '')
    if registration_number:
        parts.append(f"{registration_number}[软著]. ")
    
    rights_scope = software.get('rights_scope', '')
    if rights_scope and rights_scope != '全部权利':
        parts.append(f"{rights_scope}. ")
    
    development_date = software.get('development_date', '')
    if development_date:
        parts.append(f"{development_date}.")
    
    return ''.join(parts).strip()


def export_softwares_gbt7714(softwares) -> str:
    """导出软著为GB/T 7714-2015格式"""
    if not softwares:
        return ""
    return '\n\n'.join([format_software_gbt7714(s) for s in softwares])
