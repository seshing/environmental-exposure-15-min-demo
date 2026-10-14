"""Export existing Figure 2/3 results without recalculating their methods."""
from pathlib import Path
import json,pickle
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=Path('/Users/seshing/NUS/Projects/EnvirExpose_final')
PALETTE={'1_1':'#402e2d','2_1':'#81373e','3_1':'#c63f51','1_2':'#3d6150','2_2':'#837570','3_2':'#ef9b77','1_3':'#359070','2_3':'#9dc886','3_3':'#fee038'}

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,np.integer):return int(value)
    return value

def write(path,data):path.write_text(json.dumps(clean(data),separators=(',',':'),allow_nan=False))

def geo(frame,path):
    data=json.loads(frame.to_json(drop_id=True));write(path,data)

def main():
    out=ROOT/'dist/data/project';out.mkdir(parents=True,exist_ok=True)
    (out/'metros').mkdir(exist_ok=True)
    config=ROOT/'scripts/demo_chips.json'
    configured=json.loads(config.read_text()) if config.exists() else [{'id':'chip_64482_pid_103_36','city':'47900','manifest':'data/chips/chip_64482_pid_103_36/model.json'}]
    configured_by_city={item['city']:item for item in configured}
    (out/'metro-chips').mkdir(exist_ok=True)
    fig2=RESEARCH/'output/figure/01_global_trend/fig2_city_comparison_data_primary'
    stats=pd.read_parquet(fig2/'city_stats_final_no_geometry_100pct.parquet')
    states=gpd.read_file('zip://'+str(RESEARCH/'data/boundary/cb_2021_us_state_20m.zip')).to_crs(4326)
    states=states[~states.STUSPS.isin(['PR','VI','GU','MP','AS'])]
    geo(states[['STUSPS','geometry']],ROOT/'dist/data/states.geojson')
    _,scatter,fits,*_=pickle.loads((fig2/'local_relationship_data_100pct.pkl').read_bytes())
    boundaries=gpd.read_parquet(RESEARCH/'data/boundary/core_based_statistical_areas_selected.parquet').to_crs(4326)
    stats['accessBin']=pd.qcut(stats.Avg_Access,3,labels=[1,2,3]).astype(int)
    stats['eeiBin']=pd.qcut(stats.Avg_EVCI,3,labels=[1,2,3]).astype(int)
    cities=boundaries.merge(stats,left_on='NAME',right_on='city_name',how='inner',validate='one_to_one')
    assert len(cities)==len(stats),'Figure 2 city geometry mismatch'
    points=[];index=[]
    access=gpd.read_parquet(RESEARCH/'data/data-383-final/accessibility_k3_383_msa/accessibility_k3_383_msa.parquet').to_crs(4326)
    access.GEOID=access.GEOID.astype(str).str.zfill(12)
    # Geometry simplification affects drawing only; original published numbers are retained.
    access.geometry=access.to_crs(5070).geometry.simplify(60,preserve_topology=True).to_crs(4326)
    access_groups={str(k):v for k,v in access.groupby('CBSAFP')}
    fig3=RESEARCH/'output/figure/02_environmental_cost_opportunity/data/fresh_fig3_environmental_cost_opportunity_primary'
    prefix='fig3_fresh_cbg_equal_city_ring_equal_environmental_cost_opportunity_primary'
    cbg=pd.read_parquet(fig3/f'{prefix}_fresh_cbg_eei_metrics.parquet');cbg.GEOID=cbg.GEOID.astype(str).str.zfill(12)
    loss=pd.read_csv(fig3/f'{prefix}_all_cities.csv').set_index('city_name')
    chips=gpd.read_file(RESEARCH/'data/boundary/chip_cityname.geojson');all_chips=chips.copy().to_crs(4326);all_chips['chipId']='chip_'+all_chips.chip_index.astype(str)+'_pid_'+all_chips.parent_id.astype(str);chips=chips[chips.NAME=='Washington-Arlington-Alexandria, DC-VA-MD-WV'].to_crs(4326)
    chips['chipId']='chip_'+chips.chip_index.astype(str)+'_pid_'+chips.parent_id.astype(str)
    projected_chips=chips.to_crs(5070);centres=projected_chips.geometry.centroid
    test_index=chips.index[chips.chipId.eq('chip_64482_pid_103_36')][0];anchor=centres.loc[test_index];selected=[test_index]
    for dx,dy in [(-15000,0),(15000,0),(0,-15000),(0,15000)]:
        distance=(centres.x-anchor.x-dx)**2+(centres.y-anchor.y-dy)**2
        selected.append(distance.drop(selected).idxmin())
    chips=chips.loc[selected].copy()
    chips['available']=chips.chipId.eq('chip_64482_pid_103_36')
    geo(chips[['chipId','available','geometry']],out/'washington-chips.geojson')
    for _,row in cities.iterrows():
        cbsa=str(row.CBSAFP);name=row.city_name;point=row.geometry.representative_point()
        props={'id':cbsa,'name':name,'shortName':row.city_name_clean,'access':row.Avg_Access,'eei':row.Avg_EVCI,'population':row.Pop_Count,'r':row.local_r,'p':row.local_p,'n':row.local_n,'significant':bool(pd.notna(row.local_p) and row.local_p<.01),'bivariate':PALETTE[f'{row.accessBin}_{row.eeiBin}']}
        points.append({'type':'Feature','geometry':{'type':'Point','coordinates':[point.x,point.y]},'properties':props})
        detail={'city':props,'bounds':row.geometry.bounds,'fit':fits.get(name),'scatter':np.asarray(scatter.get(name,[])).round(6).tolist(),'loss':None,'preservation':None,'rings':[],'hasChip':cbsa in configured_by_city}
        if cbsa in configured_by_city:
            own=all_chips[all_chips.chipId.eq(configured_by_city[cbsa]['id'])][['chipId','geometry']].copy();own['available']=True
            geo(own,out/'metro-chips'/f'{cbsa}.geojson');detail['chipsFile']=f'data/project/metro-chips/{cbsa}.geojson'
        if name in loss.index:
            record=loss.loc[name];detail['loss']={key:float(record[f'cost_{key}_to_inside15']) for key in ['mid15_30','mid30_60','outside60']}
            detail['preservation']={key:float(record[f'availability_{key}_to_inside15']) for key in ['mid15_30','mid30_60','outside60']}
            detail['insideMean']=float(record.inside15_mean)
            detail['ringMeans']={key:float(record[f'source_mean_{key}_to_inside15']) for key in ['mid15_30','mid30_60','outside60']}
        polygons=access_groups.get(cbsa)
        if polygons is not None:
            own=cbg[cbg.city_name==name][['GEOID','PT_score','eei_cbg_equal']]
            assert not own.GEOID.duplicated().any()
            polygons=polygons[['GEOID','PT_score','geometry']].rename(columns={'PT_score':'accessMinutes'}).merge(own,on='GEOID',how='left',validate='one_to_one')
            polygons['minutes']=polygons.PT_score.fillna(polygons.accessMinutes)
            polygons['ring']=np.select([polygons.minutes<=15,polygons.minutes<=30,polygons.minutes<=60],['inside15','mid15_30','mid30_60'],default='outside60')
            polygons.loc[~np.isfinite(polygons.minutes),'ring']='missing'
            polygons['hasExposure']=polygons.eei_cbg_equal.notna()
            geo(polygons[['GEOID','minutes','ring','eei_cbg_equal','hasExposure','geometry']],out/'metros'/f'{cbsa}-rings.geojson')
            detail['rings']=[{'id':ring,'count':int((polygons.ring==ring).sum())} for ring in ['inside15','mid15_30','mid30_60','outside60']]
        detail['boundary']={'type':'Feature','properties':{},'geometry':json.loads(gpd.GeoSeries([row.geometry],crs=4326).to_json())['features'][0]['geometry']}
        write(out/'metros'/f'{cbsa}.json',detail);index.append(props)
    write(out/'cities.geojson',{'type':'FeatureCollection','features':points})
    write(out/'index.json',{'cities':index,'bivariatePalette':PALETTE,'eeiCBGBreaks':cbg.eei_cbg_equal.dropna().quantile([.2,.4,.6,.8]).tolist(),'figure2':'Existing 100% Figure 2 cache; population-weighted city means and within-city CBG local r; p < 0.01 filter in local-r map','figure3':'Existing final 155-city Figure 3 table; floor-equal CBG EEI and CBG-equal city-ring means; loss = 100*(source ring mean - <=15-minute mean)/source ring mean','chips':configured})
    print('PASS:',len(cities),'Figure 2 cities;',len(loss),'eligible Figure 3 cities;',len(chips),'Washington reference footprints;',len(configured),'city chips activated.')

if __name__=='__main__':main()
