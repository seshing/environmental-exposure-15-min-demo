"""Historical VoxCity face order, verified against the saved original mesh."""
from pathlib import Path
import numpy as np

def extract(p):
 a=np.load(p/'voxcity_grid.npy');size=float(np.load(p/'meshsize.npy'));coords=np.argwhere(a==-3);shape=np.array(a.shape)
 dirs=np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]])
 corners=np.array([[[1,0,0],[1,1,0],[1,1,1],[1,0,1]],[[0,0,0],[0,0,1],[0,1,1],[0,1,0]],[[0,1,0],[0,1,1],[1,1,1],[1,1,0]],[[0,0,0],[1,0,0],[1,0,1],[0,0,1]],[[0,0,1],[1,0,1],[1,1,1],[0,1,1]],[[0,0,0],[0,1,0],[1,1,0],[1,0,0]]])
 order=[4,5,0,1,2,3];dirs=dirs[order];corners=corners[order]
 flags=[]
 for d in dirs:
  adj=coords+d;inside=((adj>=0)&(adj<shape)).all(axis=1);v=np.zeros(len(coords),a.dtype);v[inside]=a[tuple(adj[inside].T)];flags.append((v==0)|(v==-2))
 flags=np.stack(flags,axis=1);vi,di=np.where(flags);quad=(coords[vi,None,:]+corners[di])*size;tri=quad[:,[0,1,2,0,2,3],:].reshape(-1,3,3);normals=np.repeat(dirs[di],2,axis=0)
 meta=np.clip(np.floor((tri.mean(axis=1)-1e-6)/size).astype(int),0,shape-1)
 return tri,normals,meta,np.repeat(coords[vi],2,axis=0)
