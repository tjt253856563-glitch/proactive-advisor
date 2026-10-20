#!/usr/bin/env python3
"""Build a skills-only plugin ZIP from the published source; does not install it."""
import argparse
import json
from pathlib import Path
import zipfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent/'plugin'
    output=args.output.resolve()
    if output.is_relative_to(root):
        parser.error('output must be outside plugin source')
    manifest=json.loads((root/'plugin.json').read_text(encoding='utf-8'))
    if manifest.get('$schema')!='https://agent-plugins.org/schemas/1.0.0/plugin.schema.json':
        parser.error('unexpected plugin schema')
    name=manifest['name']
    paths=sorted(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    if any(p.is_symlink() for p in root.rglob('*')):
        parser.error('symlinks are not packaged')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            info=zipfile.ZipInfo(name+'/'+path.relative_to(root).as_posix(),date_time=(2026,10,20,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            z.writestr(info,path.read_bytes())
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:
            raise RuntimeError('archive integrity failure')
        assert f'{name}/skills/freshness-guard/SKILL.md' in z.namelist()
    print(f'{output}: {len(paths)} files; not installed')

if __name__=='__main__':
    main()
