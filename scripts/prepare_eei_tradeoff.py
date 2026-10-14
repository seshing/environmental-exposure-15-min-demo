"""Build an EEI-only building comparison using the saved paper normalization."""
from pathlib import Path
import json,argparse,gzip
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=Path('/Users/seshing/NUS/Projects/EnvirExpose_final')
parser=argparse.ArgumentParser();parser.add_argument('--cbsa',default='47900');parser.add_argument('--model-dir',type=Path,default=ROOT/'dist/data/chips/chip_64482_pid_103_36');parser.add_argument('--name',default='Washington');args=parser.parse_args();OUT=args.model_dir
PREFIX='fig3_fresh_cbg_equal_city_ring_equal_environmental_cost_opportunity_primary'
params=pd.read_csv(RESEARCH/f'output/figure/02_environmental_cost_opportunity/data/fresh_fig3_environmental_cost_opportunity_primary/{PREFIX}_eei_params.csv').iloc[0]
access=gpd.read_parquet(RESEARCH/'data/data-383-final/accessibility_k3_383_msa/accessibility_k3_383_msa.parquet',filters=[('CBSAFP','==',args.cbsa)])
times=['t_outdoor','t_exercise','t_eating','t_moving','t_cultural','t_services','t_learning','t_healthcare','t_supplies']
capped=access[times+['PT_score']].clip(upper=300)
access=access[~capped.eq(300).all(axis=1)].copy()
access['minutes']=capped.loc[access.index,times].mean(axis=1)
access=access[np.isfinite(access.minutes)&(access.minutes>=0)].copy()
access.GEOID=access.GEOID.astype(str).str.zfill(12)
rows=[]
states=gpd.read_file('zip://'+str(RESEARCH/'data/boundary/cb_2021_us_state_20m.zip'));state_names=dict(zip(states.STATEFP,states.STUSPS))
geoids=access.GEOID.tolist()
for statefp in sorted(set(access.GEOID.str[:2])):
    state=state_names[statefp]
    frame=pd.read_parquet(RESEARCH/f'data/visual_exposure/upstream/floor_level/visual_population_primary_{state}.parquet',columns=['GEOID','building_id','voxel_level','face_count','vegetation','openness','area','Total','Total_per_floor'],filters=[('GEOID','in',[g for g in geoids if g.startswith(statefp)])])
    frame.GEOID=frame.GEOID.astype(str).str.zfill(12)
    rows.append(frame[frame.GEOID.isin(access.GEOID)])
f=pd.concat(rows,ignore_index=True)
valid=np.isfinite(f[['vegetation','openness','face_count','area','Total','Total_per_floor']]).all(axis=1)&(f.face_count>0)&(f.area>0)&(f.Total>0)&(f.Total_per_floor>0)&(f.vegetation<=params.vegetation_q999)&(f.openness<=params.openness_q999)
f=f[valid].copy()
assert not f.duplicated(['building_id','voxel_level']).any()
f['eei']=(((f.vegetation-params.vegetation_mean)/params.vegetation_sd+(f.openness-params.openness_mean)/params.openness_sd)/2-params.eei_zmean_min)/(params.eei_zmean_max-params.eei_zmean_min)
assert f.eei.between(-1e-6,1+1e-6).all()
f['weighted']=f.eei*f.face_count
b=f.groupby('building_id').agg(GEOID=('GEOID','first'),weighted=('weighted','sum'),faces=('face_count','sum'))
assert f.groupby('building_id').GEOID.nunique().max()==1
b['eei']=b.weighted/b.faces
b=b.join(access.set_index('GEOID')[['minutes']],on='GEOID').dropna(subset=['minutes'])
x=np.log1p(b.minutes.to_numpy());y=b.eei.to_numpy();slope,intercept=np.polyfit(x,y,1)
residual=y-(slope*x+intercept);sorted_residual=np.sort(residual);threshold=float(np.quantile(residual,.9))
model=json.loads((OUT/'model.json').read_text())
# Local EEI uses the model's paired, finite measured surfaces with the paper parameters.
# Equal 5 m voxel triangles have equal areas; never replace a missing exposure with zero.
attributes=model['attributes'];buffer=OUT/model['assets']['surfaceData']
raw=gzip.decompress(buffer.read_bytes()) if buffer.suffix=='.gz' else buffer.read_bytes()
def attribute(name):
    item=attributes[name];return np.frombuffer(raw,dtype=item['type'],count=item['count'],offset=item['offset'])
veg,op,code=attribute('values'),attribute('openness'),attribute('buildings')
valid=np.isfinite(veg)&np.isfinite(op)
counts=np.bincount(code[valid].astype(int),minlength=len(model['buildingIds']))
veg_sum=np.bincount(code[valid].astype(int),weights=veg[valid],minlength=len(counts))
open_sum=np.bincount(code[valid].astype(int),weights=op[valid],minlength=len(counts))
if (OUT/'tradeoff.json').exists():legacy=json.loads((OUT/'tradeoff.json').read_text())['buildings']
else:
    from shapely.geometry import Point
    footprints=gpd.read_file(OUT/'buildings.geojson').to_crs(access.crs)
    points=footprints.groupby('building_id').geometry.apply(lambda g:g.union_all().representative_point()).to_dict()
    matrix=np.array(model['modelMatrix']).reshape(4,4,order='F');locations=[]
    for bid,box in zip(model['buildingIds'],model['buildingBounds']):
        if bid in points:point=points[bid]
        else:
            center=(np.array(box['min'])+np.array(box['max']))/2;mercator=matrix@np.array([center[0],center[1],0,1]);point=Point((mercator[0]-.5)*360,np.degrees(np.arctan(np.sinh((.5-mercator[1])*2*np.pi))));point=gpd.GeoSeries([point],crs=4326).to_crs(access.crs).iloc[0]
        locations.append(point)
    joined=gpd.sjoin(gpd.GeoDataFrame({'code':range(len(locations))},geometry=locations,crs=access.crs),access[['minutes','geometry']],how='left',predicate='intersects')
    matches={int(code):float(g.minutes.iloc[0]) for code,g in joined.groupby('code') if len(g)==1 and np.isfinite(g.minutes.iloc[0])}
    legacy=[{'minutes':matches.get(i)} for i in range(len(locations))]
local=[]
for i,bid in enumerate(model['buildingIds']):
    minutes=legacy[i].get('minutes');record={'status':'No paired exposure result','minutes':minutes}
    if minutes is None or counts[i]==0:local.append(record);continue
    z=((veg_sum[i]/counts[i]-params.vegetation_mean)/params.vegetation_sd+(open_sum[i]/counts[i]-params.openness_mean)/params.openness_sd)/2
    value=float((z-params.eei_zmean_min)/(params.eei_zmean_max-params.eei_zmean_min))
    if not 0<=value<=1:record['status']='Outside paper EEI reference range';local.append(record);continue
    expected=float(slope*np.log1p(minutes)+intercept);res=float(value-expected)
    percentile=100*(np.searchsorted(sorted_residual,res,'left')+np.searchsorted(sorted_residual,res,'right'))/2/len(b)
    local.append({'status':'matched','minutes':minutes,'eei':value,'expected':expected,'percentile':float(percentile),'top10':bool(res>0 and res>=threshold)})
# Raw metric ranks use all eligible reference buildings, never the displayed dot sample.
f['nature_weighted']=f.vegetation*f.face_count;f['open_weighted']=f.openness*f.face_count
components=f.groupby('building_id')[['nature_weighted','open_weighted']].sum().reindex(b.index)
city_values={'access':b.minutes.to_numpy(),'eei':b.eei.to_numpy(),'nature':(components.nature_weighted/b.faces).to_numpy(),'openness':(components.open_weighted/b.faces).to_numpy()}
local_values={'access':[item.get('minutes') for item in local],'eei':[item.get('eei') for item in local],'nature':[item['meanExposure'] for item in model['buildingInfo']],'openness':[item['meanOpenness'] for item in model['buildingInfo']]}
def sorted_valid(values):return np.sort(np.array([v for v in values if v is not None and np.isfinite(v)],dtype=float))
city_sorted={k:sorted_valid(v) for k,v in city_values.items()};chip_sorted={k:sorted_valid(v) for k,v in local_values.items()}
def rank(values,value,reverse=False):
    if value is None or not np.isfinite(value) or not len(values):return None
    p=100*(np.searchsorted(values,value,'left')+np.searchsorted(values,value,'right'))/2/len(values)
    return float(100-p if reverse else p)
for i,item in enumerate(local):
    item['ranks']={k:{'city':rank(city_sorted[k],values[i],k=='access'),'chip':rank(chip_sorted[k],values[i],k=='access')} for k,values in local_values.items()}
sample=b.sample(n=min(2000,len(b)),random_state=42)
out={'city':args.name,'cbsa':args.cbsa,'metricName':'EEI','baselineBuildings':len(b),'slope':float(slope),'intercept':float(intercept),'maxMinutes':float(np.ceil(b.minutes.max()/10)*10),'accessLogMin':float(np.log1p(access.minutes).min()),'accessLogMax':float(np.log1p(access.minutes).max()),'samplePoints':sample[['minutes','eei']].round(6).values.tolist(),'buildings':local,'eeiParameters':params.to_dict(),'localMethod':'Paired finite model surfaces, equal-area 5 m triangles; paper EEI normalization; no imputation or clamping', 'method':'Paper national EEI parameters and paired, valid, positive-capacity layers; face-count-weighted building means; OLS against log1p(mean nine-category CBG travel time); residual midpoint ranks over the whole metro.'}
(OUT/'tradeoff-eei.json').write_text(json.dumps(out,separators=(',',':'),allow_nan=False))
print('PASS:',len(b),'metro buildings;',sum(v['status']=='matched' for v in local),'local EEI matches; max minutes',out['maxMinutes'])
