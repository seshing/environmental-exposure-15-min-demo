"""Rebuild verified legacy open-air geometry and attach saved CSV values by face ID."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from legacy_surface import extract
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--chip',default='chip_64482_pid_103_36');args=parser.parse_args();p=ROOT/'source'/args.chip;tri,normals,meta,cells=extract(p);g=np.load(p/'building_id_grid.npy');nature=pd.read_csv(p/'bd_vegetation.csv');openness=pd.read_csv(p/'bd_openness.csv');ids=g[::-1,:][tuple(cells[:,:2].T)].astype(np.int64)
 serial=[];local=[];face_ids=[];seen={};counts={}
 for bid,ijk in zip(ids,meta):
  cells_for_building=seen.setdefault(int(bid),{});key=tuple(ijk)
  if key not in cells_for_building:cells_for_building[key]=len(cells_for_building)+1
  s=cells_for_building[key];counter_key=(int(bid),s);l=counts.get(counter_key,0)+1;counts[counter_key]=l
  serial.append(s);local.append(l);face_ids.append(f'{bid}_{s}_{l}')
 assert len(tri)==len(nature)==len(openness)
 assert len(set(face_ids))==len(face_ids)
 assert np.array_equal(np.asarray(face_ids),nature.face_id.to_numpy()),'Reconstructed legacy face IDs differ from recorded result rows'
 assert nature.face_id.equals(openness.face_id)
 assert np.array_equal(ids,nature.building_id.to_numpy())
 np.save(p/'building_gvi_vertices.npy',tri.reshape(-1,3));np.save(p/'building_gvi_faces.npy',np.arange(len(tri)*3).reshape(-1,3))
 metadata={'provided_face_normals':normals,'building_id':ids,'view_factor_values':nature.vegetation.to_numpy(),'voxel_level_in_building':nature.voxel_level.to_numpy(),'voxel_serial_per_building':np.asarray(serial),'face_voxel_local_index':np.asarray(local),'face_id':np.asarray(face_ids)}
 np.save(p/'building_gvi_metadata.npy',metadata);np.save(p/'openness_values.npy',openness.openness.to_numpy())
 print('PASS:',len(tri),'legacy triangles; every reconstructed face ID and building ID exactly matches both original CSV files. No simulation rerun.')
if __name__=='__main__':main()
