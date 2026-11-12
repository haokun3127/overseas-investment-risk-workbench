"""Adapt packaged renderer to native Word PDFs on Windows; no system LibreOffice."""
import importlib.util
import sys
from pathlib import Path
import pypdfium2 as pdfium

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/drafting-workspace-20261112'
SKILL=Path('C:/Users/10397/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/documents/skills/documents/render_docx.py')
spec=importlib.util.spec_from_file_location('drafting_packaged_renderer',SKILL)
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)


def convert(doc_path,user_profile,convert_tmp_dir,stem,verbose=False):
    path=QA/(stem+'.pdf')
    assert path.is_file()
    return str(path),'Native Word export, bundled PDFium rasterization'


def raster(pdf_path,dpi,fmt,thread_count,output_folder,paths_only,output_file):
    pdf=pdfium.PdfDocument(pdf_path);paths=[]
    for i,page in enumerate(pdf):
        path=Path(output_folder)/f'page-{i+1}.png'
        page.render(scale=dpi/72).to_pil().save(path);paths.append(str(path))
    pdf.close();return paths


renderer.convert_to_pdf=convert;renderer.convert_from_path=raster
for name in ('real-draft',):
    sys.argv=['render_docx.py',str(QA/(name+'.docx')),'--output_dir',str(QA/(name+'-pages')),'--dpi','120']
    renderer.main()
