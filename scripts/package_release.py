"""Create a source-only delivery archive, excluding data, secrets and test output."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
FILES=['README.md','PRODUCT.md','DESIGN.md','.env.example','.gitignore','.dockerignore',
       'requirements.txt','requirements-dev.txt','requirements-lock.txt','Dockerfile','compose.yaml','start.ps1','start.cmd']

def main():
    target=ROOT/'dist'/'risk-workbench-v0.1.0.zip'
    target.parent.mkdir(exist_ok=True)
    files=[ROOT/name for name in FILES]
    for folder in ['app','web','scripts','tests','docs']:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log'))
    sidecar=ROOT/'.impeccable'/'design.json'
    if sidecar.is_file():files.append(sidecar)
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for file in sorted(set(files)):
            archive.write(file,file.relative_to(ROOT).as_posix())
    with ZipFile(target) as archive:
        names=archive.namelist()
        assert '.env' not in names
        assert not any(name.startswith(('data/','qa/','.venv/')) for name in names)
        assert archive.testzip() is None
    print(f'{target}\n{len(files)} source files; no secrets, live data or QA databases.')

if __name__=='__main__':main()
