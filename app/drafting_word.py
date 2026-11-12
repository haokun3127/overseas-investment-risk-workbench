"""Readable Chinese business drafts; references are separated from the actual instrument."""
import io
import re
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from .presentation import clean_reference, clean_preparation_markers

PENDING = re.compile(r'(【(?:待补充|请填写|待核实)[：:][^】]*】)')


def add_text(p, text):
    for piece in PENDING.split(clean_preparation_markers(text)):
        run=p.add_run(piece)
        if PENDING.fullmatch(piece):
            run.font.color.rgb=RGBColor.from_string('B42318')


def build_docx(name, result):
    doc=Document()
    section=doc.sections[0]
    section.page_width=Cm(21);section.page_height=Cm(29.7)
    section.top_margin=section.bottom_margin=Cm(2.5)
    section.left_margin=section.right_margin=Cm(2.6)
    for style_name,size,chinese in [('Normal',12,'宋体'),('Title',20,'黑体'),('Heading 1',14,'黑体')]:
        style=doc.styles[style_name]
        style.font.name='Times New Roman';style.font.size=Pt(size);style.font.color.rgb=RGBColor(0,0,0)
        fonts=style.element.get_or_add_rPr().rFonts
        fonts.set(qn('w:eastAsia'),chinese);fonts.set(qn('w:cs'),'Times New Roman')
        fmt=style.paragraph_format
        fmt.line_spacing=1.6;fmt.space_after=Pt(8)
        if style_name=='Heading 1':fmt.space_before=Pt(14);fmt.keep_with_next=True
    title=doc.add_paragraph(clean_preparation_markers(name)+'（草稿）',style='Title')
    title.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for block in result['blocks']:
        if block.get('heading'):
            p=doc.add_paragraph(style='Heading 1');add_text(p,block['heading'])
        lines=block['text'].splitlines()
        for i,line in enumerate(lines):
            if not line.strip():continue
            p=doc.add_paragraph();p.paragraph_format.first_line_indent=Pt(24)
            add_text(p,line.strip())
            if i==len(lines)-1 and block.get('citations'):
                r=p.add_run(' '+''.join(f'[{n}]' for n in block['citations']))
                r.font.size=Pt(9);r.font.color.rgb=RGBColor.from_string('52647C')
    doc.add_page_break()
    doc.add_heading('核对事项与引用来源',level=1)
    doc.add_paragraph('请核实事实、适用法律及条款后使用。引用原文匹配不等于法律适用性已获确认。')
    if result.get('manually_edited'):
        doc.add_paragraph('正文含人工修改，保留的引用用于追溯生成依据，未对修改内容重新进行自动核验。')
    pending=list(dict.fromkeys(result.get('missing_fields',[])+
        [m.group(1) for b in result['blocks'] for m in re.finditer(r'【(?:待补充|请填写|待核实)[：:]([^】]+)】',b['text'])]))
    if pending:doc.add_paragraph('待补充：'+'；'.join(pending))
    for warning in result.get('warnings',[]):doc.add_paragraph('待核对：'+warning)
    roles={'facts':'事项事实','template':'文书模板','knowledge':'参考依据'}
    for source in result.get('sources',[]):
        source=clean_reference(source)
        doc.add_heading(f"[{source['number']}] {source['title']}",level=1)
        doc.add_paragraph(roles.get(source.get('role'),'参考资料'))
        add_text(doc.add_paragraph(),source['quote'])
        meta=' · '.join(str(source.get(k) or '') for k in ('source','date','locator'))
        if meta:doc.add_paragraph(meta)
        if source.get('url'):doc.add_paragraph('来源：'+source['url'])
    footer=section.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE')
    # Include a cached display value for readers that do not evaluate fields.
    run=OxmlElement('w:r');text=OxmlElement('w:t');text.text='1'
    run.append(text);field.append(run);footer._p.append(field)
    doc.core_properties.title=clean_preparation_markers(name)
    output=io.BytesIO();doc.save(output)
    return output.getvalue()
