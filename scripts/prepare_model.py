"""Export the real VoxCity sample for the local, static map viewer."""
from pathlib import Path
import argparse,json,math
import numpy as np
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('/Users/seshing/Notebook/voxcity/code/01_sun/output/test_grid'))
    parser.add_argument('--out',type=Path,default=ROOT/'dist/data')
    parser.add_argument('--id',default='washington-dc')
    parser.add_argument('--name',default='Washington, D.C.')
    args=parser.parse_args();source=args.source;out=args.out;out.mkdir(parents=True,exist_ok=True)
    size=float(np.load(source/'meshsize.npy'))
    vertices=np.load(source/'building_gvi_vertices.npy')
    faces=np.load(source/'building_gvi_faces.npy')
    metadata=np.load(source/'building_gvi_metadata.npy',allow_pickle=True).item()
    ids=np.asarray(metadata['building_id'],dtype=str)
    values=np.asarray(metadata['view_factor_values'],dtype=float)
    assert len(faces)==len(ids)==len(values)
    grid=np.load(source/'building_id_grid.npy');voxels=np.load(source/'voxcity_grid.npy')
    original_triangles=vertices[faces];normals=np.asarray(metadata['provided_face_normals'])
    face_cells=np.floor((original_triangles.mean(axis=1)-normals*size/2)/size+1e-6).astype(int)
    i,j,k=face_cells.T
    assert np.all(voxels[i,j,k]==-3),'Surface geometry does not match building voxels'
    direct_match=np.mean(grid[i,j].astype(np.int64).astype(str)==ids)
    flipped_match=np.mean(grid[::-1,:][i,j].astype(np.int64).astype(str)==ids)
    reverse_north=flipped_match>direct_match
    model_grid=grid[::-1,:] if reverse_north else grid
    assert np.all(model_grid[i,j].astype(np.int64).astype(str)==ids),'Building IDs do not align with the surface geometry'
    footprints=gpd.read_file(source/'building_gdf.geojson')
    projected=footprints.to_crs(3857)
    # Register the saved model to its original footprint locations, including its axis direction.
    pairs=[]
    for bid in np.unique(grid[grid>0]):
        ii,jj=np.where(grid==bid);matching=projected[projected.id==int(bid)]
        if matching.empty or len(ii)<15 or ii.min()==0 or jj.min()==0 or ii.max()==grid.shape[0]-1 or jj.max()==grid.shape[1]-1:continue
        point=matching.geometry.union_all().centroid
        pairs.append([ii.mean()*size+size/2,jj.mean()*size+size/2,point.x,point.y])
    pairs=np.asarray(pairs)
    if reverse_north:pairs[:,0]=grid.shape[0]*size-pairs[:,0]
    design=np.column_stack([pairs[:,:2],np.ones(len(pairs))]);keep=np.ones(len(pairs),dtype=bool)
    for _ in range(5):
        fit=np.linalg.lstsq(design[keep],pairs[keep,2:],rcond=None)[0]
        errors=np.linalg.norm(design@fit-pairs[:,2:],axis=1);keep=errors<max(4,np.median(errors)*3)
    assert keep.sum()>50 and np.median(errors[keep])<max(2,size*.7),'Model registration failed'
    # Display the entire existing sample, including its original boundary buildings.
    selected=set(ids);mask=np.ones(len(faces),dtype=bool)
    position_dtype='<u2' if np.all(vertices==np.round(vertices)) and vertices.min()>=0 and vertices.max()<=65535 else '<f4'
    surface_positions=vertices[faces].astype(position_dtype).reshape(-1,3)
    surface_positions.tofile(out/'surfaces.bin')
    selected_ids=sorted(set(ids[mask]));codes={bid:i for i,bid in enumerate(selected_ids)}
    building_codes=np.asarray([codes[bid] for bid in ids[mask]],dtype=np.uint16)
    triangles=vertices[faces[mask]];building_min=np.full((len(selected_ids),3),np.inf);building_max=np.full((len(selected_ids),3),-np.inf)
    np.minimum.at(building_min,building_codes,triangles.min(axis=1));np.maximum.at(building_max,building_codes,triangles.max(axis=1))
    building_bounds=[{'min':a.tolist(),'max':b.tolist()} for a,b in zip(building_min,building_max)]
    packed={};chunks=[];offset=0
    def pack(name,array,dtype):
        nonlocal offset
        a=np.asarray(array,dtype=dtype);padding=(-offset)%4
        if padding:chunks.append(bytes(padding));offset+=padding
        packed[name]={'offset':offset,'count':len(a),'type':np.dtype(dtype).name}
        chunks.append(a.tobytes());offset+=a.nbytes
    pack('values',values[mask],'<f4')
    openness=np.load(source/'openness_values.npy') if (source/'openness_values.npy').exists() else None
    if openness is not None:pack('openness',openness[mask],'<f4')
    pack('buildings',building_codes,'<u2')
    pack('levels',np.asarray(metadata['voxel_level_in_building'])[mask],'<u2')
    pack('voxelSerial',np.asarray(metadata['voxel_serial_per_building'])[mask],'<u4')
    pack('faceLocal',np.asarray(metadata['face_voxel_local_index'])[mask],'<u1')
    (out/'surface-data.bin').write_bytes(b''.join(chunks))
    # Export only the outside faces of the existing voxel model, including trees and terrain.
    voxels=np.load(source/'voxcity_grid.npy');lo=0;extent=np.asarray(voxels.shape[:2])*size
    tile=voxels;occupied=tile!=0
    context_positions=[];context_colors=[];context_buildings=[]
    # VoxCity's normalized voxel classes: positive classes are land cover.
    land_colors={1:[125,106,83],2:[75,110,61],3:[59,88,52],4:[109,122,66],5:[55,90,64],6:[92,112,67],7:[68,101,79],8:[49,86,72],9:[48,71,91],10:[159,173,179],11:[63,67,72],12:[52,57,64],13:[75,79,84]}
    visible_land_counts={}
    face_corners=[[[0,0,0],[0,1,0],[0,1,1],[0,0,1]],[[1,0,0],[1,0,1],[1,1,1],[1,1,0]],[[0,0,0],[0,0,1],[1,0,1],[1,0,0]],[[0,1,0],[1,1,0],[1,1,1],[0,1,1]],[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],[[0,0,1],[0,1,1],[1,1,1],[1,0,1]]]
    for axis in range(3):
        for direction in [-1,1]:
            neighbour=np.zeros_like(occupied);target=[slice(None)]*3;other=[slice(None)]*3
            if direction<0:target[axis]=slice(1,None);other[axis]=slice(None,-1)
            else:target[axis]=slice(None,-1);other[axis]=slice(1,None)
            neighbour[tuple(target)]=occupied[tuple(other)]
            exposed=occupied & ~neighbour
            if axis==2 and direction>0:
                canopy_above=np.zeros_like(occupied)
                canopy_above[tuple(target)]=(tile[tuple(other)]==-2)
                exposed |= (tile>0) & canopy_above
            if axis==2 and direction<0:exposed[:,:,:]=False
            coords=np.argwhere(exposed)
            if not len(coords):continue
            classes=tile[tuple(coords.T)];positions=coords.astype(float);positions[:,:2]+=lo
            corners=np.asarray(face_corners[axis*2+(direction>0)])
            quad=(positions[:,None,:]+corners[None,:,:])*size
            triangles=quad[:,[0,1,2,0,2,3],:].reshape(-1,3).astype(position_dtype);context_positions.append(triangles)
            colors=np.tile(np.array([61,69,78],dtype=np.uint8),(len(coords),1))
            colors[classes==-3]=[101,110,121];colors[classes==-2]=[59,93,61];colors[classes==-1]=[56,49,43]
            for class_id,color in land_colors.items():
                colors[classes==class_id]=color
                visible_land_counts[class_id]=visible_land_counts.get(class_id,0)+int((classes==class_id).sum())
            roof_ids=model_grid[coords[:,0]+lo,coords[:,1]+lo].astype(np.int64)
            building_lookup=np.asarray([codes.get(str(bid),-1)+1 if cls==-3 else 0 for bid,cls in zip(roof_ids,classes)],dtype='<u2')
            context_buildings.append(np.repeat(building_lookup,2))
            context_colors.append(np.repeat(colors,6,axis=0))
    context_positions=np.concatenate(context_positions);context_colors=np.concatenate(context_colors)
    context_positions.tofile(out/'context.bin');context_colors.tofile(out/'context-colors.bin')
    context_buildings=np.concatenate(context_buildings);context_buildings.tofile(out/'context-buildings.bin')
    assert len(context_buildings)*3==len(context_positions)
    earth=40075016.68557849
    origin=[fit[2,0]/earth+.5,.5-fit[2,1]/earth]
    location=[(origin[0]-.5)*360,math.degrees(math.atan(math.sinh((.5-origin[1])*2*math.pi)))]
    scale=1/(earth*math.cos(math.radians(location[1])))
    matrix=[fit[0,0]/earth,-fit[0,1]/earth,0,0,fit[1,0]/earth,-fit[1,1]/earth,0,0,0,0,scale,0,*origin,0,1]
    def lnglat(x,y):
        xy=np.asarray([x,y,1])@fit
        return [xy[0]/earth*360,math.degrees(math.atan(math.sinh(xy[1]/earth*2*math.pi)))]
    corners=[lnglat(0,0),lnglat(0,extent[1]),lnglat(extent[0],extent[1]),lnglat(extent[0],0)]
    region={'type':'Feature','properties':{},'geometry':{'type':'Polygon','coordinates':[corners+[corners[0]]]}}
    (out/'region.geojson').write_text(json.dumps(region))
    area_footprints=footprints.to_crs(footprints.estimate_utm_crs())
    footprint_areas={str(bid):float(group.geometry.union_all().area) for bid,group in area_footprints.groupby('id')}
    face_areas=np.linalg.norm(np.cross(original_triangles[:,1]-original_triangles[:,0],original_triangles[:,2]-original_triangles[:,0]),axis=1)/2
    valid=np.isfinite(values[mask]);weighted=np.bincount(building_codes[valid],weights=values[mask][valid]*face_areas[valid],minlength=len(selected_ids));weights=np.bincount(building_codes[valid],weights=face_areas[valid],minlength=len(selected_ids))
    open_valid=np.isfinite(openness) if openness is not None else np.zeros(len(building_codes),dtype=bool)
    open_weighted=np.bincount(building_codes[open_valid],weights=openness[open_valid]*face_areas[open_valid],minlength=len(selected_ids)) if openness is not None else np.zeros(len(selected_ids))
    open_weights=np.bincount(building_codes[open_valid],weights=face_areas[open_valid],minlength=len(selected_ids))
    building_info=[]
    for index,bid in enumerate(selected_ids):
        area=footprint_areas.get(bid);area_source='Footprint area'
        if area is None:area=float((model_grid==int(bid)).sum()*size**2);area_source='Voxel footprint area'
        building_info.append({'areaM2':area,'areaLabel':area_source,'meanExposure':float(weighted[index]/weights[index]) if weights[index]>0 else None,'meanOpenness':float(open_weighted[index]/open_weights[index]) if open_weights[index]>0 else None})
    wanted=footprints[footprints.id.astype(str).isin(selected_ids)].copy()
    wanted['building_id']=wanted.id.astype(str)
    (out/'buildings.geojson').write_text(wanted[['building_id','geometry']].to_json())
    manifest={'id':args.id,'name':args.name,'meshSize':size,'center':lnglat(extent[0]/2,extent[1]/2),'extentMeters':float(max(extent)),'positionType':np.dtype(position_dtype).name,'bounds':[[min(p[0] for p in corners),min(p[1] for p in corners)],[max(p[0] for p in corners),max(p[1] for p in corners)]],'modelMatrix':matrix,'registration':{'method':'Matched original building footprints','reverseNorthAxis':bool(reverse_north),'medianErrorMercatorMeters':float(np.median(errors[keep])),'matchedBuildings':int(keep.sum())},'metric':{'id':'vegetation','name':'Vegetation view','unit':'ratio','colorMax':.5,'missing':'NaN values from the source are retained as missing'},'surfaceCount':int(mask.sum()),'buildingIds':selected_ids,'buildingBounds':building_bounds,'buildingInfo':building_info,'landCoverColors':land_colors,'visibleLandCoverFaces':visible_land_counts,'contextVertexCount':len(context_positions),'attributes':packed,'assets':{'surfaces':'surfaces.bin','surfaceData':'surface-data.bin','context':'context.bin','contextColors':'context-colors.bin','contextBuildings':'context-buildings.bin'},'source':'Original VoxCity voxel model and precomputed surface view factors'}
    manifest['metrics']={'nature':{'name':'Nature view','attribute':'values','colorMax':.5},'openness':{'name':'Openness','attribute':'openness','colorMax':1}} if openness is not None else {'nature':{'name':'Nature view','attribute':'values','colorMax':.5}}
    manifest['sourceChip']=args.id
    (out/'model.json').write_text(json.dumps(manifest,indent=2))
    # Check the export preserves geometry and each recorded surface result.
    exported=np.fromfile(out/'surfaces.bin',dtype=position_dtype).reshape(-1,3)
    assert np.array_equal(exported,surface_positions)
    exported_values=np.frombuffer((out/'surface-data.bin').read_bytes(),dtype='<f4',count=manifest['surfaceCount'])
    assert np.allclose(exported_values,values[mask],atol=1e-7,equal_nan=True)
    original_face_ids=np.asarray(metadata['face_id'])[mask]
    serial=np.asarray(metadata['voxel_serial_per_building'])[mask];local=np.asarray(metadata['face_voxel_local_index'])[mask]
    assert all(str(face)==f'{bid}_{int(s)}_{int(l)}' for face,bid,s,l in zip(original_face_ids,ids[mask],serial,local))
    if openness is not None:
        info=packed['openness'];exported_openness=np.frombuffer((out/'surface-data.bin').read_bytes(),dtype='<f4',offset=info['offset'],count=info['count']);assert np.allclose(exported_openness,openness,atol=1e-7,equal_nan=True)
    print('PASS:',len(selected_ids),'source buildings,',manifest['surfaceCount'],'original surface triangles,',int(np.isfinite(exported_values).sum()),'recorded values. Export preserves source values and face IDs.')
    print('Local data size:',round(sum(p.stat().st_size for p in out.glob('*'))/1024**2,1),'MB')

if __name__=='__main__':main()
