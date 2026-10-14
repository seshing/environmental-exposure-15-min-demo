"""Read-only 5090 computation. Input/output are gzip JSON streams; no remote writes."""
import sys,json,gzip,io
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import pyarrow.parquet as pq

request=json.loads(gzip.decompress(sys.stdin.buffer.read()))
models=request['models'];params=request['parameters'];cities={m['city'] for m in models}
base=Path('/home/xiucheng/projects/Voxcity/output/publication383_fig1245_preview_20261001/full/outputs')
assert params==json.loads((base/'00_common/common_parameters.json').read_text())
cbg=pd.read_parquet(base/'02_fig2/fig2_visualization_data.parquet',columns=['GEOID','cbsa_code','access_minutes'])
cbg.GEOID=cbg.GEOID.astype(str).str.zfill(12);cbg.cbsa_code=cbg.cbsa_code.astype(str)
cbg=cbg[cbg.cbsa_code.isin(cities)].set_index('GEOID')
assert cbg.index.is_unique
# Match model footprints using original, unsimplified repaired CBG boundaries.
access=gpd.read_parquet('/data/xiucheng/voxcity/data/accessibility_k3_383_msa_repaired_2020/accessibility_k3_383_msa.parquet',columns=['GEOID','CBSAFP','geometry','t_outdoor','t_exercise','t_eating','t_moving','t_cultural','t_services','t_learning','t_healthcare','t_supplies']).to_crs(4326)
access.GEOID=access.GEOID.astype(str).str.zfill(12);access.CBSAFP=access.CBSAFP.astype(str)
times=['t_outdoor','t_exercise','t_eating','t_moving','t_cultural','t_services','t_learning','t_healthcare','t_supplies']
values=access[times].clip(0,300);access['minutes']=values.mean(axis=1);access.loc[values.eq(300).all(axis=1),'minutes']=np.nan
for m in models:
    rows=m['buildings'];points=gpd.GeoDataFrame({'code':range(len(rows))},geometry=gpd.points_from_xy([r['point'][0] for r in rows],[r['point'][1] for r in rows]),crs=4326)
    own=access[access.CBSAFP.eq(m['city'])][['GEOID','minutes','geometry']]
    joined=gpd.sjoin(points,own,how='left',predicate='intersects')
    matches={int(k):{'GEOID':g.GEOID.iloc[0],'minutes':float(g.minutes.iloc[0])} for k,g in joined.groupby('code') if len(g)==1 and pd.notna(g.GEOID.iloc[0]) and np.isfinite(g.minutes.iloc[0])}
    for i,r in enumerate(rows):r.update(matches.get(i,{'GEOID':None,'minutes':None}))
    print('Matched CBGs:',m['name'],len(matches),'/',len(rows),file=sys.stderr,flush=True)
del access,points,joined
# Stream the repaired/deduplicated floor tables once for all requested metros.
parts={city:[] for city in cities};read_rows=0;retained_rows=0
floor_root=Path('/data/xiucheng/voxcity/data/final_383_repaired_2020_dedup/primary_383_by_state')
columns=['GEOID','building_id','voxel_level','vegetation','openness','area','Total_per_floor','face_count']
for path in sorted(floor_root.glob('visual_population_primary_*.parquet')):
    state_parts=[]
    for batch in pq.ParquetFile(path).iter_batches(batch_size=500_000,columns=columns):
        frame=batch.to_pandas();read_rows+=len(frame)
        frame.GEOID=frame.GEOID.astype(str).str.zfill(12)
        frame=frame[frame.GEOID.isin(cbg.index)].copy()
        if frame.empty:continue
        valid=np.isfinite(frame[['vegetation','openness','area','Total_per_floor','face_count']]).all(axis=1)&(frame.area>0)&(frame.Total_per_floor>0)&(frame.face_count>0)&frame.vegetation.between(params['vegetation_lower'],params['vegetation_upper'])&frame.openness.between(params['openness_lower'],params['openness_upper'])
        frame=frame[valid].copy();retained_rows+=len(frame)
        if frame.empty:continue
        assert not frame.duplicated(['GEOID','building_id','voxel_level']).any()
        frame['city']=frame.GEOID.map(cbg.cbsa_code)
        frame['natureSum']=frame.vegetation*frame.face_count;frame['openSum']=frame.openness*frame.face_count
        state_parts.append(frame.groupby(['city','GEOID','building_id'],observed=True)[['face_count','natureSum','openSum']].sum())
    if state_parts:
        aggregated=pd.concat(state_parts).groupby(level=[0,1,2]).sum().reset_index()
        for city,group in aggregated.groupby('city'):parts[city].append(group.drop(columns='city'))
        print('Aggregated:',path.name,len(aggregated),'buildings',file=sys.stderr,flush=True)
    del state_parts

def rank(sorted_values,value,reverse=False):
    if value is None or not np.isfinite(value) or len(sorted_values)==0:return None
    p=100*(np.searchsorted(sorted_values,value,'left')+np.searchsorted(sorted_values,value,'right'))/(2*len(sorted_values))
    return float(100-p if reverse else p)

def eei(nature,openness):
    return .5*((nature-params['vegetation_weighted_mean'])/params['vegetation_weighted_sd']+(openness-params['openness_weighted_mean'])/params['openness_weighted_sd'])

def sorted_finite(values):return np.sort(np.asarray([v for v in values if v is not None and np.isfinite(v)],dtype=float))

result={};summary=[]
for m in models:
    city=m['city'];b=pd.concat(parts[city]).groupby(['GEOID','building_id']).sum().reset_index()
    assert not b.building_id.duplicated().any(), 'A reference building has multiple CBG assignments'
    b['nature']=b.natureSum/b.face_count;b['openness']=b.openSum/b.face_count;b['minutes']=b.GEOID.map(cbg.access_minutes);b['eei']=eei(b.nature,b.openness)
    assert np.isfinite(b[['nature','openness','minutes','eei']]).all().all() and len(b)>1000
    x=np.log1p(b.minutes.to_numpy());y=b.eei.to_numpy();slope,intercept=np.polyfit(x,y,1)
    residual=y-(slope*x+intercept);assert abs(residual.mean())<1e-8 and abs(np.mean(residual*(x-x.mean())))<1e-8;sorted_residual=np.sort(residual);threshold=np.quantile(residual,.9)
    local=[]
    for r in m['buildings']:
        minutes=r['minutes'];nature=r['pairedNature'];openness=r['pairedOpenness']
        value=float(eei(nature,openness)) if nature is not None and openness is not None else None
        item={'status':'matched' if value is not None and minutes is not None else 'No paired exposure or matched CBG','GEOID':r['GEOID'],'minutes':minutes,'eei':value}
        if item['status']=='matched':
            expected=float(slope*np.log1p(minutes)+intercept);res=value-expected
            item.update(expected=expected,percentile=rank(sorted_residual,res),top10=bool(res>0 and res>=threshold))
        local.append(item)
    city_values={'access':b.minutes.to_numpy(),'nature':b.nature.to_numpy(),'openness':b.openness.to_numpy(),'eei':y}
    local_values={'access':[r['minutes'] for r in local],'nature':[r['nature'] for r in m['buildings']],'openness':[r['openness'] for r in m['buildings']],'eei':[r['eei'] for r in local]}
    city_sorted={k:sorted_finite(v) for k,v in city_values.items()};chip_sorted={k:sorted_finite(v) for k,v in local_values.items()}
    for i,item in enumerate(local):item['ranks']={key:{'city':rank(city_sorted[key],values[i],key=='access'),'chip':rank(chip_sorted[key],values[i],key=='access')} for key,values in local_values.items()}
    logs=np.log1p(np.r_[b.minutes.to_numpy(),sorted_finite(local_values['access'])]);lo=float(logs.min());hi=float(logs.max())
    local_eei=sorted_finite(local_values['eei']);all_y=np.r_[y,local_eei,slope*np.array([lo,hi])+intercept];pad=np.ptp(all_y)*.05;ymin=float(np.floor((all_y.min()-pad)*10)/10);ymax=float(np.ceil((all_y.max()+pad)*10)/10)
    sample=b.sample(n=min(2000,len(b)),random_state=42)
    result[m['id']]={'city':m['name'],'cbsa':city,'metricName':'EEI','metricScale':'z-score','baselineBuildings':len(b),'slope':float(slope),'intercept':float(intercept),'accessLogMin':lo,'accessLogMax':hi,'eeiMin':ymin,'eeiMax':ymax,'samplePoints':sample[['minutes','eei']].round(6).values.tolist(),'buildings':local,'eeiParameters':params,'referenceVersion':'publication383_fig1245_preview_20261001; final_383_repaired_2020_dedup','localMethod':'Original paired finite model surfaces; equal-area 5 m triangles; latest EEI z-score parameters; no imputation or clamping','method':'Repaired/deduplicated primary floors; publication two-sided exposure, positive area/population filters; face-count-weighted building means; OLS against log1p(nine-category mean travel time). City ranks use all eligible reference buildings, chip ranks use all finite model means; midpoint ties, lower time ranks higher. CBGs matched with original unsimplified repaired 2020 boundaries.'}
    summary.append({'city':city,'name':m['name'],'chip':m['id'],'baselineBuildings':len(b),'modelBuildings':len(local),'matched':sum(r['status']=='matched' for r in local),'top10':sum(r.get('top10',False) for r in local)})
    print('Calculated:',m['name'],len(b),'reference buildings',file=sys.stderr,flush=True)
output={'models':result,'summary':summary,'readFloorRows':read_rows,'retainedSelectedFloorRows':retained_rows}
sys.stdout.buffer.write(gzip.compress(json.dumps(output,separators=(',',':'),allow_nan=False).encode(),compresslevel=6,mtime=0))
