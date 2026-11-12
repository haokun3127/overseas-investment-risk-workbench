"""Record deterministic Word checks separately from an unavailable visual PDF conversion."""
import json
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/drafting-workspace-20261112'
result=json.loads((QA/'real-draft.json').read_text(encoding='utf-8'))
doc=Document(QA/'real-draft.docx')
paragraphs=[p.text for p in doc.paragraphs]
for block in result['blocks']:
    assert block['heading'] in paragraphs
    for line in block['text'].splitlines():
        if line.strip():assert any(line.strip() in p for p in paragraphs)
assert abs(doc.sections[0].page_width.cm-21)<.01
assert abs(doc.sections[0].page_height.cm-29.7)<.01
assert doc.styles['Normal'].element.rPr.rFonts.get(qn('w:eastAsia'))=='宋体'
assert doc.styles['Normal'].font.name=='Times New Roman'
assert doc.styles['Heading 1'].element.rPr.rFonts.get(qn('w:eastAsia'))=='黑体'
assert any('核对事项与引用来源'==p for p in paragraphs)
assert doc.sections[0].footer._element.xpath('.//w:fldSimple')
report={'content_and_structure_passed':True,'sections':len(result['blocks']),
    'a4':True,'chinese_fonts':True,'western_fonts':True,'references_separate':True,
    'visual_pdf_conversion_passed':False,
    'limitation':'Native Word automation opened and paginated the draft but stalled during PDF conversion; a minimal blank document also stalled. No visual PDF claim is made.'}
(QA/'word-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report))
