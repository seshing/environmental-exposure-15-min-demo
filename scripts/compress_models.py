from pathlib import Path
import gzip,json,shutil,time
root=Path(__file__).resolve().parents[1]
web=root/'dist'
backup=root/'source/compression-originals'
rows=[]
for manifest in sorted(web.glob('data/**/model.json')):
    data=json.loads(manifest.read_text())
    for key,name in data['assets'].items():
        if name.endswith('.gz'):continue
        path=manifest.parent/name
        raw=path.read_bytes()
        packed=gzip.compress(raw,compresslevel=9,mtime=0)
        assert gzip.decompress(packed)==raw, str(path)
        target=path.with_name(path.name+'.gz')
        target.write_bytes(packed)
        data['assets'][key]=target.name
        rows.append({'file':str(path.relative_to(web)),'original':len(raw),'compressed':len(packed),'identical':True})
    manifest.write_text(json.dumps(data,separators=(',',':')))
    # Keep the originals locally outside the published website.
    for row in rows:
        path=web/row['file']
        if path.exists():
            saved=backup/row['file'];saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(path),str(saved))
    print(manifest.parent.name,flush=True)
if rows:
    report={'files':rows,'original_bytes':sum(x['original'] for x in rows),'compressed_bytes':sum(x['compressed'] for x in rows),'verified_files':len(rows)}
    (root/'source/compression-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='files'}),flush=True)
