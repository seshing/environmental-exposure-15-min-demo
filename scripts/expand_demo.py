"""Read-only SSH import: one verified 5 m chip for each selected research city."""
from pathlib import Path
import json,subprocess,sys,shlex,re,time,csv
from concurrent.futures import ThreadPoolExecutor
import geopandas as gpd
ROOT=Path(__file__).resolve().parents[1];PYTHON=sys.executable
plan=json.loads((ROOT/'scripts/demo_candidates.json').read_text());probe=json.loads((ROOT/'source/demo_remote_probe.json').read_text())
source=ROOT/'source';source.mkdir(exist_ok=True);project=ROOT/'dist/data/project';(project/'metro-chips').mkdir(exist_ok=True)
shapes=gpd.read_file('/Users/seshing/NUS/Projects/EnvirExpose_final/data/boundary/chip_cityname.geojson').to_crs(4326)
shapes['chipId']='chip_'+shapes.chip_index.astype(str)+'_pid_'+shapes.parent_id.astype(str)
status={'started':time.time(),'ready':[],'failures':[],'current':None}
def save(): (source/'expansion-status.json').write_text(json.dumps(status,indent=2))
def candidates(row):
 return [chip for chip in row['candidates'] if probe[chip].get('meshSize')==5 and probe[chip]['sizes']['voxcity_grid.npy']<60_000_000 and max(probe[chip]['sizes'][k] for k in ['bd_vegetation.csv','bd_openness.csv'])<170_000_000]
def download(chip):
 assert re.fullmatch(r'chip_[0-9]+_pid_[0-9]+_[0-9]+',chip)
 names=['building_gdf.geojson','building_id_grid.npy','voxcity_grid.npy','meshsize.npy','bd_vegetation.csv','bd_openness.csv'];folder=source/chip
 if all((folder/n).exists() and (folder/n).stat().st_size==probe[chip]['sizes'][n] for n in names):return
 command='tar -czf - -C /mnt/data/xiucheng/voxcity/from_data2/model/us_top500 '+ ' '.join(shlex.quote(chip+'/'+n) for n in names[:4])+' -C /data2/shared/xiucheng/voxcity/output/us_top500/simulation '+' '.join(shlex.quote(chip+'/'+n) for n in names[4:])
 for attempt in range(3):
  transport=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','5090',command],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  unpack=subprocess.run(['tar','-xzf','-','-C',str(source)],stdin=transport.stdout,stderr=subprocess.PIPE);transport.stdout.close();error=transport.stderr.read();code=transport.wait()
  if code==0 and unpack.returncode==0 and all((folder/n).exists() and (folder/n).stat().st_size==probe[chip]['sizes'][n] for n in names):return
  if attempt==2:raise RuntimeError('Transfer failed: '+error.decode()[-300:]+unpack.stderr.decode()[-300:])
def run(script,args,chip):
 output=subprocess.run([PYTHON,str(ROOT/'scripts'/script),*args],cwd=ROOT,capture_output=True,text=True)
 (source/chip/(script+'.log')).write_text(output.stdout+output.stderr)
 if output.returncode:raise RuntimeError(script+': '+(output.stdout+output.stderr)[-1400:])
 print(output.stdout.strip(),flush=True)
def register(row,chip):
 city=row['city'];out=ROOT/'dist/data/chips'/chip;m=json.loads((out/'model.json').read_text());t=json.loads((out/'tradeoff-eei.json').read_text())
 assert m['meshSize']==5 and m['surfaceCount']>0 and len(t['buildings'])==len(m['buildingIds']) and t['baselineBuildings']>1000
 assert sum(v['status']=='matched' for v in t['buildings'])>50
 entry={'id':chip,'city':city['id'],'manifest':'data/chips/'+chip+'/model.json','name':city['shortName']}
 shape=shapes[shapes.chipId.eq(chip)][['chipId','geometry']].copy();assert len(shape)==1;shape['available']=True
 path=project/'metro-chips'/f"{city['id']}.geojson";path.write_text(shape.to_json(drop_id=True))
 metro_path=project/'metros'/f"{city['id']}.json";metro=json.loads(metro_path.read_text());metro['hasChip']=True;metro['chipsFile']='data/project/metro-chips/'+city['id']+'.geojson';metro_path.write_text(json.dumps(metro,separators=(',',':')))
 idx_path=project/'index.json';idx=json.loads(idx_path.read_text());idx['chips']=[e for e in idx['chips'] if e['city']!=city['id']]+[entry];idx_path.write_text(json.dumps(idx,separators=(',',':')))
 size=sum(p.stat().st_size for p in out.iterdir() if p.is_file())/1024**2
 status['ready'].append({**entry,'buildings':len(m['buildingIds']),'faces':m['surfaceCount'],'sizeMB':round(size,1),'registrationError':m['registration']['medianErrorMercatorMeters']});save()
 with (source/'demo-cities.csv').open('w') as f:
  writer=csv.DictWriter(f,fieldnames=list(status['ready'][0]));writer.writeheader();writer.writerows(status['ready'])
 print('READY',len(status['ready']),city['shortName'],chip,'size',round(size,1),'MB',flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:
 futures={row['city']['id']:pool.submit(download,candidates(row)[0]) for row in plan if candidates(row)}
 for row in plan:
  city=row['city'];status['current']=city['shortName'];save();print('CITY',city['shortName'],flush=True)
  for attempt,chip in enumerate(candidates(row)[:5]):
   try:
    if attempt==0:futures[city['id']].result()
    else:download(chip)
    out=ROOT/'dist/data/chips'/chip
    if not (out/'model.json').exists():
     run('import_paper_chip.py',['--chip',chip],chip)
     run('prepare_model.py',['--source',str(source/chip),'--out',str(out),'--id',chip,'--name',city['shortName']],chip)
    if not (out/'tradeoff-eei.json').exists():run('prepare_eei_tradeoff.py',['--cbsa',city['id'],'--model-dir',str(out),'--name',city['shortName']],chip)
    register(row,chip);break
   except Exception as error:
    status['failures'].append({'city':city['shortName'],'chip':chip,'error':str(error)});save();print('RETRY',city['shortName'],str(error)[-350:],flush=True)
  else:print('FAILED CITY',city['shortName'],flush=True)
status['current']=None;status['finished']=time.time();save();print('COMPLETE',len(status['ready']),'cities',flush=True)
if len(status['ready'])!=30:sys.exit(1)
