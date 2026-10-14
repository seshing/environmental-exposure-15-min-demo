"""Recalculate model ranks from latest publication inputs, read-only over SSH."""
from pathlib import Path
import argparse,json,gzip,subprocess,shlex,shutil
from datetime import datetime
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cbsa');parser.add_argument('--model-dir',type=Path);parser.add_argument('--name');args=parser.parse_args()
    entries=json.loads((ROOT/'scripts/demo_chips.json').read_text());entries=[e for e in entries if args.cbsa is None or e['city']==args.cbsa]
    if args.model_dir:
        assert args.cbsa,'--cbsa is required with --model-dir'
        manifest=json.loads((args.model_dir/'model.json').read_text());entries=[{'id':manifest['id'],'city':args.cbsa,'name':args.name or manifest['name'],'folder':str(args.model_dir)}]
    assert entries,'No registered models selected'
    parameters=json.loads((ROOT/'source/publication_latest/common_parameters.json').read_text())
    models=[]
    for e in entries:
        folder=Path(e['folder']) if 'folder' in e else ROOT/'dist/data/chips'/e['id'];model=json.loads((folder/'model.json').read_text());info=model['attributes'];p=folder/model['assets']['surfaceData'];raw=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
        def attribute(key):a=info[key];return np.frombuffer(raw,dtype=a['type'],count=a['count'],offset=a['offset'])
        veg,op,code=attribute('values'),attribute('openness'),attribute('buildings');valid=np.isfinite(veg)&np.isfinite(op);n=len(model['buildingIds']);counts=np.bincount(code[valid].astype(int),minlength=n);v=np.bincount(code[valid].astype(int),weights=veg[valid],minlength=n);o=np.bincount(code[valid].astype(int),weights=op[valid],minlength=n)
        shapes=gpd.read_file(folder/'buildings.geojson').to_crs(4326);shapes.building_id=shapes.building_id.astype(str);points=shapes.groupby('building_id').geometry.apply(lambda g:g.union_all().representative_point()).to_dict();matrix=np.array(model['modelMatrix']).reshape(4,4,order='F');rows=[]
        for i,bid in enumerate(model['buildingIds']):
            point=points.get(str(bid))
            if point is None:
                box=model['buildingBounds'][i];center=(np.array(box['min'])+np.array(box['max']))/2;merc=matrix@np.array([center[0],center[1],0,1]);point=Point((merc[0]-.5)*360,np.degrees(np.arctan(np.sinh((.5-merc[1])*2*np.pi))))
            rows.append({'id':bid,'point':[point.x,point.y],'nature':model['buildingInfo'][i]['meanExposure'],'openness':model['buildingInfo'][i]['meanOpenness'],'pairedNature':float(v[i]/counts[i]) if counts[i] else None,'pairedOpenness':float(o[i]/counts[i]) if counts[i] else None})
        models.append({'id':e['id'],'city':e['city'],'name':e['name'],'buildings':rows})
    payload=gzip.compress(json.dumps({'parameters':parameters,'models':models},allow_nan=False).encode(),mtime=0)
    command='/data/xiucheng/miniconda3/envs/voxcity/bin/python -c '+shlex.quote((ROOT/'scripts/building_rank_reference.py').read_text())
    target=ROOT/'source/latest-building-ranks.json.gz';part=target.with_suffix('.part')
    with part.open('wb') as out:
        process=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','5090',command],stdin=subprocess.PIPE,stdout=out,stderr=subprocess.PIPE)
        process.stdin.write(payload);process.stdin.close()
        with (ROOT/'source/latest-building-ranks.log').open('w') as log:
            for line in iter(process.stderr.readline,b''):
                text=line.decode();log.write(text);log.flush();print(text.strip(),flush=True)
        assert process.wait()==0,'Remote calculation failed; web files unchanged'
    result=json.loads(gzip.decompress(part.read_bytes()));assert len(result['models'])==len(entries)
    manifest=json.loads((ROOT/'source/publication_latest/inputs_manifest.json').read_text());assert result['readFloorRows']==manifest['input_floor_rows'],'Floor source row count does not match latest publication inputs'
    for e in entries:
        data=result['models'][e['id']];folder=Path(e['folder']) if 'folder' in e else ROOT/'dist/data/chips'/e['id'];model=json.loads((folder/'model.json').read_text());assert len(data['buildings'])==len(model['buildingIds']) and data['metricScale']=='z-score'
        for item in data['buildings']:
            for metric,ranks in item['ranks'].items():
                for rank in ranks.values():assert rank is None or 0<=rank<=100
    backup=ROOT/'source'/('building-ranks-before-latest-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir()
    for e in entries:
        folder=Path(e['folder']) if 'folder' in e else ROOT/'dist/data/chips'/e['id'];path=folder/'tradeoff-eei.json'
        if path.exists():shutil.copy2(path,backup/(e['id']+'.json'))
        path.write_text(json.dumps(result['models'][e['id']],separators=(',',':'),allow_nan=False))
    part.replace(target);(ROOT/'source/latest-building-ranks-summary.json').write_text(json.dumps({k:v for k,v in result.items() if k!='models'},indent=2))
    print('PASS:',len(entries),'models updated;',sum(row['baselineBuildings'] for row in result['summary']),'reference buildings;',sum(row['matched'] for row in result['summary']),'matched model buildings.')

if __name__=='__main__':main()
