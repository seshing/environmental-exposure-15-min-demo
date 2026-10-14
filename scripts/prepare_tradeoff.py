"""Join the local sample to CBG accessibility and a whole-metro building baseline."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--research',type=Path,default=Path('/Users/seshing/NUS/Projects/EnvirExpose_final'))
    parser.add_argument('--model-dir',type=Path,default=ROOT/'dist/data')
    parser.add_argument('--metric',choices=['nature','openness'],default='nature')
    args=parser.parse_args();data=args.research/'data';out=args.model_dir;value_column='vegetation' if args.metric=='nature' else 'openness'
    model=json.loads((out/'model.json').read_text())
    access=gpd.read_parquet(data/'data-383-final/accessibility_k3_383_msa/accessibility_k3_383_msa.parquet',filters=[('CBSAFP','==','47900')])
    times=['t_outdoor','t_exercise','t_eating','t_moving','t_cultural','t_services','t_learning','t_healthcare','t_supplies']
    # Same nine-category travel-time average and 300-minute cap as Figure 2.
    capped=access[times+['PT_score']].clip(upper=300)
    access=access[~capped.eq(300).all(axis=1)].copy()
    access['minutes']=capped.loc[access.index,times].mean(axis=1)
    access=access[np.isfinite(access.minutes)&(access.minutes>=0)].copy()
    access.GEOID=access.GEOID.astype(str).str.zfill(12)
    assert not access.GEOID.duplicated().any()
    rows=[]
    for state in ['DC','MD','VA','WV']:
        frame=pd.read_parquet(data/f'visual_exposure/upstream/floor_level/visual_population_primary_{state}.parquet',columns=['GEOID','building_id','voxel_level','face_count',value_column])
        frame=frame.rename(columns={value_column:'vegetation'})
        frame.GEOID=frame.GEOID.astype(str).str.zfill(12)
        rows.append(frame[frame.GEOID.isin(access.GEOID)])
    frame=pd.concat(rows,ignore_index=True)
    frame=frame[np.isfinite(frame.vegetation)&np.isfinite(frame.face_count)&(frame.face_count>0)].copy()
    assert not frame.duplicated(['building_id','voxel_level']).any(),'Duplicate building layers would bias the baseline'
    assert frame.groupby('building_id').GEOID.nunique().max()==1
    frame['weighted']=frame.vegetation*frame.face_count
    buildings=frame.groupby('building_id').agg(GEOID=('GEOID','first'),weighted=('weighted','sum'),faces=('face_count','sum'))
    buildings['vegetation']=buildings.weighted/buildings.faces
    # Normalize over valid metro CBGs, including CBGs without paper exposure records.
    log_time=np.log1p(access.minutes);lo,hi=float(log_time.min()),float(log_time.max());assert hi>lo
    access['score']=1-(log_time-lo)/(hi-lo)
    buildings=buildings.join(access.set_index('GEOID')[['score']],on='GEOID').dropna(subset=['score','vegetation'])
    x=buildings.score.to_numpy();y=buildings.vegetation.to_numpy()
    slope,intercept=np.polyfit(x,y,1);residuals=y-(slope*x+intercept);sorted_residuals=np.sort(residuals)
    threshold=float(np.quantile(residuals,.9))
    assert len(buildings)>10000 and len(access)>100
    # Use each footprint's representative point to assign one CBG.
    footprints=gpd.read_file(out/'buildings.geojson').to_crs(access.crs)
    shapes=footprints.groupby('building_id').geometry.apply(lambda group:group.union_all().representative_point()).to_dict()
    matrix=np.asarray(model['modelMatrix']).reshape(4,4,order='F')
    points=[];methods=[]
    for bid,box in zip(model['buildingIds'],model['buildingBounds']):
        if bid in shapes:point=shapes[bid];method='Footprint representative point'
        else:
            center=(np.asarray(box['min'])+np.asarray(box['max']))/2
            mercator=matrix@np.array([center[0],center[1],0,1])
            point=Point((mercator[0]-.5)*360,np.degrees(np.arctan(np.sinh((.5-mercator[1])*2*np.pi))))
            point=gpd.GeoSeries([point],crs=4326).to_crs(access.crs).iloc[0];method='Model building centre'
        points.append(point);methods.append(method)
    local=gpd.GeoDataFrame({'code':range(len(points))},geometry=points,crs=access.crs)
    joined=gpd.sjoin(local,access[['GEOID','score','minutes','geometry']],how='left',predicate='intersects')
    matches={int(code):group.iloc[0] for code,group in joined.groupby('code') if len(group)==1 and pd.notna(group.iloc[0].GEOID)}
    local_data=[]
    for code,info in enumerate(model['buildingInfo']):
        match=matches.get(code);value=info['meanExposure' if args.metric=='nature' else 'meanOpenness']
        if match is None:local_data.append({'status':'No matching CBG in baseline'});continue
        record={'status':'No recorded vegetation view' if value is None else 'matched','cbg':str(match.GEOID),'accessibility':float(match.score),'minutes':float(match.minutes),'assignment':methods[code]}
        if value is not None:
            expected=float(slope*match.score+intercept);residual=value-expected
            below=np.searchsorted(sorted_residuals,residual,side='left');through=np.searchsorted(sorted_residuals,residual,side='right')
            percentile=float((below+through)/2/len(residuals)*100)
            record.update(vegetation=value,expected=expected,residual=residual,percentile=percentile,top10=bool(residual>0 and residual>=threshold))
        local_data.append(record)
    # Display a deterministic sample; fitting and percentiles use all records.
    sample=buildings.sample(n=min(2000,len(buildings)),random_state=42)
    result={'city':'Washington metro','cbsa':'47900','baselineBuildings':len(buildings),'baselineCBGs':int(buildings.GEOID.nunique()),'accessibilityCBGs':len(access),'slope':float(slope),'intercept':float(intercept),'rSquared':float(np.corrcoef(x,y)[0,1]**2),'top10ResidualThreshold':threshold,'sampleMeshMeters':model['meshSize'],'baselineMeshMeters':5,'provisional':bool(model['meshSize']!=5),'metricName':'Nature view' if args.metric=='nature' else 'Openness','accessibilityMethod':'1 - city min-max(log1p(mean nine-category k=3 travel time, capped at 300 minutes))','buildingMeanMethod':'Source building-layer vegetation weighted by face_count; equal source voxel-face areas','rankMethod':'Building residual against whole-metro ordinary least squares; midpoint percentile for ties; top 10% also requires a positive residual','sampleSeed':42,'samplePoints':sample[['score','vegetation']].round(6).to_numpy().tolist(),'buildings':local_data}
    (out/('tradeoff.json' if args.metric=='nature' else 'tradeoff-openness.json')).write_text(json.dumps(result,separators=(',',':'),allow_nan=False))
    print('PASS:',len(buildings),'whole-metro buildings;',buildings.GEOID.nunique(),'baseline CBGs;' ,sum(d['status']=='matched' for d in local_data),'local buildings matched; slope',round(float(slope),5),'R²',round(result['rSquared'],5))
    print('Matched top-10% sample buildings:',sum(d.get('top10',False) for d in local_data))

if __name__=='__main__':main()
