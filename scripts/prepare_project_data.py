"""Export the specified 5090 publication results without recomputing figures."""
from pathlib import Path
import json, shutil, hashlib
from datetime import datetime
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source/publication_latest'
PALETTE={'1_1':'#402e2d','2_1':'#81373e','3_1':'#c63f51','1_2':'#3d6150','2_2':'#837570','3_2':'#ef9b77','1_3':'#359070','2_3':'#9dc886','3_3':'#fee038'}
RINGS={'mid15_30':'15_30','mid30_60':'30_60','outside60':'gt60'}

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,np.integer):return int(value)
    return value

def write(path,data):path.write_text(json.dumps(clean(data),separators=(',',':'),allow_nan=False))
def geo(frame,path):write(path,json.loads(frame.to_json(drop_id=True)))

def main():
    current=ROOT/'dist/data/project'
    out=ROOT/'source/project-next'
    out.mkdir(exist_ok=True);(out/'metros').mkdir(exist_ok=True)
    configured=json.loads((ROOT/'scripts/demo_chips.json').read_text())
    configured_by_city={item['city']:item for item in configured}
    stats=pd.read_csv(SOURCE/'fig2/fig2_visualization_city_summary.csv',dtype={'cbsa_code':str})
    cbg=pd.read_parquet(SOURCE/'fig2/fig2_visualization_data.parquet')
    cbg.GEOID=cbg.GEOID.astype(str).str.zfill(12);cbg.cbsa_code=cbg.cbsa_code.astype(str)
    fig3=pd.read_parquet(SOURCE/'fig3/fig3_visualization_data.parquet').set_index('city_name')
    capacity=pd.read_csv(SOURCE/'fig3/fig3_floor_preservation_capacity.csv').set_index('city_name')
    regression=pd.read_parquet(SOURCE/'fig3/fig3_ring_cbg_regression_data.parquet')
    check=cbg.merge(regression,on='GEOID',suffixes=('_2','_3'),validate='one_to_one')
    for key in ['access_minutes','eei_z','eei_raw']:assert np.array_equal(check[key+'_2'],check[key+'_3'])
    for key in RINGS:assert np.allclose(capacity[f'availability_{key}_to_inside15'],fig3.loc[capacity.index,f'availability_{key}_to_inside15'],equal_nan=True)
    boundaries=gpd.read_parquet(SOURCE/'geometry/msa_383_boundaries.parquet').to_crs(4326)
    boundaries.CBSAFP=boundaries.CBSAFP.astype(str)
    cities=boundaries.merge(stats,left_on='CBSAFP',right_on='cbsa_code',how='inner',validate='one_to_one')
    assert len(cities)==len(stats)==380 and cities.NAME.eq(cities.city_name).all()
    assert set(configured_by_city)<=set(stats.cbsa_code)
    cities['accessBin']=pd.qcut(cities.mean_access_z,3,labels=[1,2,3]).astype(int)
    cities['eeiBin']=pd.qcut(cities.mean_eei_z,3,labels=[1,2,3]).astype(int)
    polygons=gpd.read_parquet(SOURCE/'geometry/cbg_geometry.parquet')
    polygons.GEOID=polygons.GEOID.astype(str).str.zfill(12);polygons.CBSAFP=polygons.CBSAFP.astype(str)
    assert not polygons.GEOID.duplicated().any() and not cbg.GEOID.duplicated().any()
    assert set(cbg.GEOID)<=set(polygons.GEOID), 'Missing latest CBG geometry'
    polygons=polygons.merge(cbg[['GEOID','cbsa_code','access_minutes','eei_z','eei_raw']],on='GEOID',how='left',validate='one_to_one')
    assert polygons.loc[polygons.cbsa_code.notna(),'CBSAFP'].eq(polygons.loc[polygons.cbsa_code.notna(),'cbsa_code']).all(), 'CBG assignment mismatch'
    polygons['minutes']=polygons.access_minutes.fillna(polygons.PT_score)
    polygons['eei']=polygons.eei_z
    polygons['ring']=np.select([polygons.minutes<=15,polygons.minutes<=30,polygons.minutes<=60],['inside15','mid15_30','mid30_60'],default='outside60')
    polygons.loc[~np.isfinite(polygons.minutes),'ring']='missing'
    polygons['hasExposure']=np.isfinite(polygons.eei)
    groups={str(k):v for k,v in polygons.groupby('CBSAFP')}
    index=[];points=[]
    for _,row in cities.iterrows():
        cbsa=row.CBSAFP;name=row.city_name;point=row.geometry.representative_point()
        short=name.split(',')[0].split('-')[0]
        props={'id':cbsa,'name':name,'shortName':short,'access':row.mean_access_z,'eei':row.mean_eei_z,'accessMinutes':row.mean_access_minutes,'eeiRaw':row.mean_eei_raw,'population':row.population,'r':row.local_r,'p':row.local_p,'n':row.local_n_cbg,'nEffective':row.local_n_eff,'significant':bool(pd.notna(row.local_p) and row.local_p<.01),'bivariate':PALETTE[f'{row.accessBin}_{row.eeiBin}']}
        points.append({'type':'Feature','geometry':{'type':'Point','coordinates':[point.x,point.y]},'properties':props})
        detail={'city':props,'bounds':row.geometry.bounds,'fit':{'slope':row.local_slope,'intercept':row.mean_eei_z-row.local_slope*row.mean_access_z},'scatter':[],'loss':None,'preservation':None,'rings':[],'hasChip':cbsa in configured_by_city}
        if detail['hasChip']:
            detail['chipsFile']=f'data/project/metro-chips/{cbsa}.geojson'
        if name in fig3.index:
            record=fig3.loc[name];detail['loss']={key:record[f'cost_{key}_to_inside15'] for key in RINGS}
            detail['preservation']={key:capacity.loc[name,f'availability_{key}_to_inside15'] for key in RINGS}
            detail['insideMean']=record.le15_eei_raw
            detail['ringMeans']={key:record[f'{band}_eei_raw'] for key,band in RINGS.items()}
            detail['ringComponents']={key:{metric:record[f'{band}_{metric}'] for metric in ['vegetation','openness']} for key,band in RINGS.items()}
        own=groups.get(cbsa)
        if own is not None:
            geo(own[['GEOID','minutes','ring','eei','eei_raw','hasExposure','geometry']],out/'metros'/f'{cbsa}-rings.geojson')
            detail['rings']=[{'id':ring,'count':int((own.ring==ring).sum())} for ring in ['inside15','mid15_30','mid30_60','outside60']]
        detail['boundary']={'type':'Feature','properties':{},'geometry':row.geometry.__geo_interface__}
        write(out/'metros'/f'{cbsa}.json',detail);index.append(props)
    # Keep the verified 30-chip geometries and model registry.
    shutil.copytree(current/'metro-chips',out/'metro-chips',dirs_exist_ok=True)
    for name in ['demo-cities.csv','washington-chips.geojson']:
        if (current/name).exists():shutil.copy2(current/name,out/name)
    write(out/'cities.geojson',{'type':'FeatureCollection','features':points})
    versions={'figure2':'publication383_fig1245_preview_20261001/full/outputs/02_fig2','figure3':'publication383_figure3_repaired_20261003/outputs/03_fig3'}
    provenance={'host':'5090','root':'/home/xiucheng/projects/Voxcity','versions':versions,'figure2Cities':len(stats),'figure3Cities':len(fig3),'cbgCount':len(cbg),'geometrySources':['/data/xiucheng/voxcity/data/morphology_383_msa_building_vegetation_2020/msa_383_boundaries.parquet','/data/xiucheng/voxcity/data/accessibility_k3_383_msa_repaired_2020/accessibility_k3_383_msa.parquet'],'geometrySimplificationMeters':60,'standardization':'Figure 2 mean_access_z and mean_eei_z; floor-population-weighted CBG means','preservation':'100 × qualifying ≤15-min floor population / valid ≤15-min floor population; qualify when 0.5 × (Nature/outer Nature + Openness/outer Openness) ≥ 1','files':{str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*') if p.is_file() and p.suffix!='.part'}}
    write(out/'provenance.json',provenance)
    write(out/'index.json',{'cities':index,'bivariatePalette':PALETTE,'eeiCBGBreaks':cbg.eei_z.quantile([.2,.4,.6,.8]).tolist(),'figure2':versions['figure2'],'figure3':versions['figure3'],'globalFit':pd.read_csv(SOURCE/'fig2/fig2_global_city_equal_fit.csv').iloc[0].to_dict(),'metricScale':'z-score','chips':configured})
    assert all((out/'metros'/f'{city["id"]}.json').exists() for city in index)
    backup=ROOT/'source'/('project-before-latest-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    current.rename(backup);shutil.move(str(out),str(current))
    print('PASS:',len(stats),'Figure 2 cities;',len(fig3),'Figure 3 cities;',len(cbg),'CBG metrics;',len(configured),'models retained;',len(check),'Figure 2/3 CBG values exactly matched.')

if __name__=='__main__':main()
