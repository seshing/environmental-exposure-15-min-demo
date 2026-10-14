import * as THREE from './vendor/three.module.js';
const $=id=>document.getElementById(id);
export function createModelViewer(map){
let model,region,tradeoff,modelBase='',activeChip,activeMetric='nature';
let loadVersion=0;let inRegion=false,modelData,loadPromise,layer,selectedLevel=null,selectedBuilding=null;let showBuildings=true,showVegetation=true;
const raycaster=new THREE.Raycaster();
function closeDetails(){selectedLevel=null;selectedBuilding=null;$('inspector').hidden=true;document.body.classList.remove('has-selection');if(layer?.highlight)layer.highlight.visible=false;if(layer?.buildingHighlight)layer.buildingHighlight.visible=false;if(layer?.buildingOutline)layer.buildingOutline.visible=false;map.triggerRepaint();}
$('close').onclick=closeDetails;
function resetView(){const zoom=16.05-Math.log2((model.extentMeters||530)/530)+Math.log2(Math.min(1,innerWidth/900,innerHeight/720));map.flyTo({center:model.center,zoom,pitch:58,bearing:-25,duration:1100});}
$('reset').onclick=()=>{closeDetails();resetView();};
$('retry').onclick=()=>{loadPromise=null;openChip(activeChip);};
window.addEventListener('keydown',event=>{if(event.key==='Escape'){closeMetricMenu();closeDetails();$('help').hidden=true;$('info').setAttribute('aria-expanded','false');}});
function updateVisibility(){
  $('buildings-toggle').setAttribute('aria-pressed',String(showBuildings));$('vegetation-toggle').setAttribute('aria-pressed',String(showVegetation));
  if(!showBuildings)closeDetails();
  if(layer){layer.surfaceMesh.visible=showBuildings;const uniforms=layer.contextMesh.material.uniforms;uniforms.showBuildings.value=showBuildings;uniforms.showVegetation.value=showVegetation;}
  $('legend').hidden=!inRegion||!layer||!showBuildings;map.triggerRepaint();
}
$('buildings-toggle').onclick=()=>{showBuildings=!showBuildings;updateVisibility();};
$('vegetation-toggle').onclick=()=>{showVegetation=!showVegetation;updateVisibility();};
async function loadModel(){
  const version=loadVersion,manifest=model,base=modelBase;
  if(modelData)return modelData;
  if(!loadPromise)loadPromise=Promise.all(Object.entries(manifest.assets).map(async([key,file])=>{const response=await fetch(base+file);if(!response.ok)throw Error('Model data unavailable');const buffer=file.endsWith('.gz')?await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer():await response.arrayBuffer();return[key,buffer];})).then(entries=>{
    const buffers=Object.fromEntries(entries);const constructors={float32:Float32Array,uint16:Uint16Array,uint32:Uint32Array,uint8:Uint8Array};const attributes={};
    for(const [name,info] of Object.entries(manifest.attributes))attributes[name]=new constructors[info.type](buffers.surfaceData,info.offset,info.count);
    const Positions=constructors[manifest.positionType||'float32'];
    const loaded={positions:new Positions(buffers.surfaces),context:new Positions(buffers.context),contextColors:new Uint8Array(buffers.contextColors),contextBuildings:new Uint16Array(buffers.contextBuildings),attributes,rawValues:{nature:attributes.values,openness:attributes.openness}};if(version===loadVersion)modelData=loaded;return loaded;
  });
  return loadPromise;
}
async function openChip(url){
  const version=++loadVersion;activeChip=url;$('retry').onclick=()=>{loadPromise=null;openChip(activeChip);};closeDetails();inRegion=true;$('metric').hidden=false;$('display-layers').hidden=false;$('retry').hidden=true;$('loading-text').textContent='Loading 5 m model';$('loading').hidden=false;
  try{
    if(!model||modelBase!==url.slice(0,url.lastIndexOf('/')+1)){
      if(layer){map.removeLayer('voxcity-model');layer=null;}model=null;region=null;tradeoff=null;modelData=null;loadPromise=null;modelBase=url.slice(0,url.lastIndexOf('/')+1);
      const responses=await Promise.all([fetch(url).then(checkJSON),fetch(modelBase+'region.geojson').then(checkJSON),fetch(modelBase+'tradeoff-eei.json',{cache:'no-store'}).then(checkJSON).catch(()=>null)]);
      if(version!==loadVersion||!inRegion)return;[model,region,tradeoff]=responses;
    }
    model.metric=model.metrics[activeMetric];map.getSource('region').setData(region);resetView();
    const data=await loadModel();if(!inRegion||version!==loadVersion)return;model.metric=model.metrics[activeMetric];
    data.attributes.values=data.rawValues[activeMetric];
    if(!layer){layer=createModelLayer(data);map.addLayer(layer);}else map.setLayoutProperty('voxcity-model','visibility','visible');
    $('loading').hidden=true;updateLegend();updateVisibility();
  }catch(error){if(!inRegion||version!==loadVersion)return;$('loading-text').textContent='Model unavailable';$('retry').hidden=false;console.error(error.message);}
}
function checkJSON(response){if(!response.ok)throw Error('Data unavailable');return response.json();}
function updateLegend(){
  $('legend').classList.toggle('openness',activeMetric==='openness');$('legend-name').textContent=model.metric.name;$('legend-resolution').textContent=model.meshSize+' m';$('legend-middle').textContent=Math.round(model.metric.colorMax*50)+'%';$('legend-high').textContent=Math.round(model.metric.colorMax*100)+'%'+(activeMetric==='nature'?'+':'');
}
function closeMetricMenu(){$('model-menu').hidden=true;$('model-metric').setAttribute('aria-expanded','false');}
$('model-metric').onclick=()=>{const open=$('model-menu').hidden;$('model-menu').hidden=!open;$('model-metric').setAttribute('aria-expanded',String(open));};
for(const button of $('model-menu').children)button.onclick=()=>chooseMetric(button.dataset.metric);
document.addEventListener('click',event=>{if(!event.target.closest('#model-picker'))closeMetricMenu();});
function chooseMetric(next){
  activeMetric=next;$('model-metric-name').textContent=next==='nature'?'Nature view':'Openness';closeMetricMenu();for(const button of $('model-menu').children)button.setAttribute('aria-pressed',String(button.dataset.metric===next));if(model)model.metric=model.metrics[activeMetric];if(!modelData||!layer)return;modelData.attributes.values=modelData.rawValues[activeMetric];
  const values=layer.surfaceMesh.geometry.getAttribute('exposure');for(let i=0;i<model.surfaceCount;i++){const v=modelData.attributes.values[i];values.array.fill(Number.isFinite(v)?v:-1,i*3,i*3+3);}values.needsUpdate=true;layer.surfaceMesh.material.uniforms.colorMax.value=model.metric.colorMax;layer.surfaceMesh.material.uniforms.openness.value=activeMetric==='openness';
  const code=selectedBuilding,levelNumber=selectedLevel;updateLegend();if(code!==null){selectBuilding(code,false);if(levelNumber!==null)inspectLevel(code,levelNumber);}map.triggerRepaint();
}
const vertexShader=`attribute float exposure; attribute float objectKind; varying float kind; varying float value; varying vec3 faceNormal; varying vec3 shadeColor; void main(){kind=objectKind;value=exposure;faceNormal=normal;shadeColor=color;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
const fragmentShader=`precision highp float; uniform bool surface; uniform float colorMax; uniform bool openness; uniform bool showBuildings; uniform bool showVegetation; varying float kind; varying float value; varying vec3 faceNormal; varying vec3 shadeColor;
void main(){
  if((kind==1.0&&!showBuildings)||(kind==2.0&&!showVegetation))discard;
  bool vegetation=!surface&&(kind==2.0||kind==4.0);
  vec3 c=vegetation?mix(shadeColor,vec3(.24,.43,.28),.40):(surface?shadeColor:mix(shadeColor,vec3(.94),.30));
  if(!surface&&kind==3.0)c=vec3(.24,.28,.27);
  bool recorded=surface&&value>=0.0;
  if(recorded){float t=clamp(value/colorMax,0.0,1.0);vec3 a=vec3(237.,244.,238.)/255.,b=vec3(180.,215.,187.)/255.,d=vec3(98.,163.,122.)/255.,e=vec3(31.,99.,65.)/255.;if(openness){a=vec3(239.,246.,255.)/255.;b=vec3(177.,210.,238.)/255.;d=vec3(82.,148.,196.)/255.;e=vec3(25.,76.,125.)/255.;}c=t<.333?mix(a,b,t*3.0):(t<.667?mix(b,d,(t-.333)*3.0):mix(d,e,(t-.667)*3.0));}
  float shade=abs(dot(normalize(faceNormal),normalize(vec3(.4,-.3,1.0))));
  float light=recorded?.88+.12*shade:.64+.36*shade;
  gl_FragColor=vec4(c*light,1.0);
}`;
function createGeometry(positions,colors,values,kinds){
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.computeVertexNormals();
  const count=positions.length/3;geometry.setAttribute('objectKind',new THREE.BufferAttribute(kinds||new Uint8Array(count).fill(1),1));geometry.setAttribute('color',new THREE.BufferAttribute(colors||new Float32Array(count*3).fill(.78),3,Boolean(colors)));
  geometry.setAttribute('exposure',new THREE.BufferAttribute(values||new Float32Array(count).fill(-1),1));geometry.computeBoundingSphere();return geometry;
}
function createModelLayer(data){
  const values=new Float32Array(model.surfaceCount*3);for(let i=0;i<model.surfaceCount;i++){const value=data.attributes.values[i];values.fill(Number.isFinite(value)?value:-1,i*3,i*3+3);}
  const makeMaterial=surface=>new THREE.ShaderMaterial({vertexShader,fragmentShader,uniforms:{surface:{value:surface},openness:{value:activeMetric==='openness'},colorMax:{value:model.metric.colorMax},showBuildings:{value:showBuildings},showVegetation:{value:showVegetation}},vertexColors:true,side:THREE.DoubleSide,polygonOffset:surface,polygonOffsetFactor:-1,polygonOffsetUnits:-1});
  const kinds=new Uint8Array(model.contextVertexCount);
  for(let i=0;i<data.contextBuildings.length;i++){
    const offset=i*9,r=data.contextColors[offset],g=data.contextColors[offset+1],b=data.contextColors[offset+2];
    const kind=data.contextBuildings[i]>0||(r===101&&g===110&&b===121)?1:(r===59&&g===93&&b===61?2:(g>r*1.15&&g>b*1.08?4:(r===52&&g===57&&b===64?3:0)));
    kinds.fill(kind,i*3,i*3+3);
  }
  return {id:'voxcity-model',type:'custom',renderingMode:'3d',
    onAdd(map,gl){
      this.map=map;this.camera=new THREE.Camera();this.scene=new THREE.Scene();this.matrix=new THREE.Matrix4().fromArray(model.modelMatrix);
      this.contextMesh=new THREE.Mesh(createGeometry(data.context,data.contextColors,null,kinds),makeMaterial(false));this.surfaceMesh=new THREE.Mesh(createGeometry(data.positions,null,values),makeMaterial(true));
      this.surfaceMesh.visible=showBuildings;this.contextKinds=kinds;this.scene.add(this.contextMesh,this.surfaceMesh);this.contextMesh.frustumCulled=false;this.surfaceMesh.frustumCulled=false;
      this.buildingHighlight=new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshBasicMaterial({color:0x218461,side:THREE.DoubleSide,transparent:true,opacity:.12,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2}));this.buildingHighlight.visible=false;this.buildingHighlight.renderOrder=2;this.scene.add(this.buildingHighlight);
      this.buildingOutline=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0x258559,transparent:true,opacity:1,depthWrite:false,depthTest:false}));this.buildingOutline.visible=false;this.buildingOutline.renderOrder=3;this.scene.add(this.buildingOutline);
      this.highlight=new THREE.Mesh(new THREE.BufferGeometry(),new THREE.MeshBasicMaterial({color:0x1b8c59,side:THREE.DoubleSide,transparent:true,opacity:.68,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-3,polygonOffsetUnits:-3}));this.highlight.visible=false;this.highlight.renderOrder=10;this.scene.add(this.highlight);
      this.renderer=new THREE.WebGLRenderer({canvas:map.getCanvas(),context:gl,antialias:true});this.renderer.autoClear=false;
    },
    render(gl,input){const matrix=input.defaultProjectionData?.mainMatrix||input;this.camera.projectionMatrix=new THREE.Matrix4().fromArray(matrix).multiply(this.matrix);this.camera.projectionMatrixInverse.copy(this.camera.projectionMatrix).invert();this.renderer.resetState();this.renderer.render(this.scene,this.camera);},
    onRemove(){this.surfaceMesh.geometry.dispose();this.contextMesh.geometry.dispose();this.highlight.geometry.dispose();this.buildingHighlight.geometry.dispose();this.buildingHighlight.material.dispose();this.buildingOutline.geometry.dispose();this.buildingOutline.material.dispose();this.surfaceMesh.material.dispose();this.contextMesh.material.dispose();this.highlight.material.dispose();this.renderer.dispose();}
  };
}
function focusBuilding(code){
  const box=model.buildingBounds[code],bounds=new maplibregl.LngLatBounds();
  for(const [x,y] of [[box.min[0]-12,box.min[1]-12],[box.min[0]-12,box.max[1]+12],[box.max[0]+12,box.min[1]-12],[box.max[0]+12,box.max[1]+12]]){
    const point=new THREE.Vector3(x,y,0).applyMatrix4(layer.matrix);
    bounds.extend(new maplibregl.MercatorCoordinate(point.x,point.y,point.z).toLngLat());
  }
  const portrait=innerWidth<=700&&innerHeight>innerWidth;
  const padding=portrait?{left:25,right:25,top:130,bottom:Math.max(220,$('inspector').offsetHeight+90)}:{left:60,right:$('inspector').offsetWidth+70,top:150,bottom:100};
  const camera=map.cameraForBounds(bounds,{padding,bearing:map.getBearing(),maxZoom:18.2});
  map.easeTo({...camera,pitch:Math.min(70,Math.max(50,map.getPitch())),padding:{left:0,right:0,top:0,bottom:0},duration:850});
}
function showTradeoff(code){
  const item=tradeoff?.buildings[code];$('tradeoff-plot').replaceChildren();$('tradeoff-rank').textContent='';$('tradeoff-rank').classList.remove('top-ten');
  $('accessibility-value').textContent=Number.isFinite(item?.minutes)?item.minutes.toFixed(1)+' min':'Unavailable';
  const rankKey='<div class="rank-comparison-key"><span class="city-rank">City</span><span class="chip-rank">Chip</span></div>';
  const rankRow=(key,name)=>{
    const rank=item?.ranks?.[key],points=[['city','#287466'],['chip','#b18a55']];
    return `<div class="rank-heading"><span>${name}</span><span>${points.map(([scope])=>`<strong class="${scope}-rank">${Number.isFinite(rank?.[scope])?'P'+Math.round(rank[scope]):'—'}</strong>`).join(' ')}</span></div><svg viewBox="0 0 244 40" role="img" aria-label="${name} percentile in city and chip"><path class="percentile-track" d="M10 10H234"/>${points.map(([scope,color])=>Number.isFinite(rank?.[scope])?`<circle cx="${10+rank[scope]*2.24}" cy="10" r="4" fill="${color}" stroke="white" stroke-width=".8"><title>${scope==='city'?'City':'Chip'} · P${rank[scope].toFixed(1)}</title></circle>`:'').join('')}<g class="chart-label"><text x="10" y="34">0</text><text x="122" y="34" text-anchor="middle">50</text><text x="234" y="34" text-anchor="end">100</text></g></svg>`;
  };
  $('building-ranks').innerHTML=rankKey+rankRow('access','Accessibility')+rankRow('nature','Nature view')+rankRow('openness','Openness');
  $('eei-ranks').innerHTML=rankKey+rankRow('eei','EEI rank');
  if(!item||item.status!=='matched'){$('tradeoff-plot').textContent='No eligible EEI record';return;}
  $('tradeoff-rank').textContent=item.top10?'Top 10%':`Percentile ${Math.round(item.percentile)}`;
  $('tradeoff-rank').classList.toggle('top-ten',item.top10);
  $('tradeoff-rank').title='EEI residual percentile relative to the metro reference fit';
  const lo=tradeoff.accessLogMin,hi=tradeoff.accessLogMax;
  const index=minutes=>1-(Math.log1p(minutes)-lo)/(hi-lo);
  const ymin=tradeoff.eeiMin??0,ymax=tradeoff.eeiMax??1;
  const x=value=>32+index(value)*202,y=value=>226-(value-ymin)/(ymax-ymin)*202;
  const dots=tradeoff.samplePoints.map(([a,b])=>`<circle cx="${x(a).toFixed(1)}" cy="${y(b).toFixed(1)}" r="1.4"/>`).join('');
  $('tradeoff-plot').innerHTML=`<svg viewBox="0 0 244 266" role="img" aria-label="Selected building EEI and access index against the city reference">
    <text class="chart-label" x="32" y="12">${tradeoff.metricScale==='z-score'?'EEI · z-score':'EEI'}</text><g class="chart-grid"><path d="M32 24H234 M32 125H234 M32 226H234"/></g>
    <g class="chart-ticks"><text x="25" y="28" text-anchor="end">${ymax.toFixed(1)}</text><text x="25" y="129" text-anchor="end">${((ymin+ymax)/2).toFixed(1)}</text><text x="25" y="230" text-anchor="end">${ymin.toFixed(1)}</text><text x="32" y="241" text-anchor="middle">0</text><text x="133" y="241" text-anchor="middle">0.5</text><text x="234" y="241" text-anchor="middle">1</text></g>
    <svg x="32" y="24" width="202" height="202" viewBox="32 24 202 202" overflow="hidden"><g class="chart-dots">${dots}</g><path class="chart-fit" d="M32 ${y(tradeoff.intercept+tradeoff.slope*hi)}L234 ${y(tradeoff.intercept+tradeoff.slope*lo)}"/></svg>
    <circle class="chart-building-halo" cx="${x(item.minutes)}" cy="${y(item.eei)}" r="10"/><circle class="chart-building" cx="${x(item.minutes)}" cy="${y(item.eei)}" r="5"><title>EEI ${item.eei.toFixed(3)} · Access index ${index(item.minutes).toFixed(3)}</title></circle>
    <text class="chart-label" x="133" y="259" text-anchor="middle">Access index</text></svg>`;
}
function selectBuilding(code,focus=true){
  selectedBuilding=code;selectedLevel=null;layer.highlight.visible=false;$('inspector').scrollTop=0;
  $('building-id').textContent=model.buildingIds[code];$('inspector').dataset.stage='building';
  delete $('inspector').dataset.level;
  $('inspector').hidden=false;$('building-hint').hidden=false;$('exposure-number').hidden=false;$('surface-note').hidden=true;$('rank-section').hidden=false;$('tradeoff').hidden=false;document.body.classList.add('has-selection');
  const info=model.buildingInfo[code];showExposure(info.meanExposure,info.meanOpenness);$('area-label').textContent=info.areaLabel;$('building-area').textContent=new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(info.areaM2)+' m²';
  showTradeoff(code);
  const starts=[];for(let i=0;i<modelData.contextBuildings.length;i++)if(modelData.contextBuildings[i]===code+1)starts.push(i*9);
  const positions=new modelData.positions.constructor(starts.length*9);
  starts.forEach((start,i)=>positions.set(modelData.context.subarray(start,start+9),i*9));
  layer.buildingHighlight.geometry.dispose();layer.buildingHighlight.geometry=new THREE.BufferGeometry();layer.buildingHighlight.geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));layer.buildingHighlight.geometry.computeBoundingSphere();layer.buildingHighlight.visible=true;
  layer.buildingOutline.geometry.dispose();layer.buildingOutline.geometry=new THREE.EdgesGeometry(layer.buildingHighlight.geometry,30);layer.buildingOutline.visible=true;
  map.triggerRepaint();if(focus)focusBuilding(code);
}
function showExposure(nature,openness){
  for(const [key,value] of [['nature',nature],['openness',openness]])$(key+'-value').textContent=Number.isFinite(value)?`${(value*100).toFixed(1)}%`:'No data';
}
function inspectLevel(code,level){
  const attributes=modelData.attributes,starts=[],weighted={nature:0,openness:0},totalArea={nature:0,openness:0};
  for(let i=0;i<model.surfaceCount;i++){
    if(attributes.buildings[i]!==code||attributes.levels[i]!==level)continue;
    const start=i*9,p=modelData.positions;starts.push(start);
    const a=new THREE.Vector3(p[start+3]-p[start],p[start+4]-p[start+1],p[start+5]-p[start+2]);
    const b=new THREE.Vector3(p[start+6]-p[start],p[start+7]-p[start+1],p[start+8]-p[start+2]);
    const area=a.cross(b).length()/2;
    for(const key of ['nature','openness']){const value=modelData.rawValues[key][i];if(Number.isFinite(value)){weighted[key]+=value*area;totalArea[key]+=area;}}
  }
  if(!starts.length)return;
  selectedLevel=level;$('inspector').dataset.stage='level';$('inspector').dataset.level=String(level);
  showExposure(totalArea.nature?weighted.nature/totalArea.nature:null,totalArea.openness?weighted.openness/totalArea.openness:null);
  $('rank-section').hidden=true;$('tradeoff').hidden=true;
  $('building-hint').hidden=true;$('surface-note').hidden=false;$('level-number').textContent=level;$('resolution').textContent=model.meshSize;
  const positions=new modelData.positions.constructor(starts.length*9);
  starts.forEach((start,i)=>positions.set(modelData.positions.subarray(start,start+9),i*9));
  layer.highlight.geometry.dispose();layer.highlight.geometry=new THREE.BufferGeometry();layer.highlight.geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));layer.highlight.geometry.computeBoundingSphere();layer.highlight.visible=true;map.triggerRepaint();
}
map.on('click',event=>{
  if(!inRegion||!showBuildings||!layer?.camera||!modelData||map.isMoving()||event.originalEvent?.target?.closest?.('button'))return;
  const rect=map.getCanvas().getBoundingClientRect();const x=event.point.x/rect.width*2-1,y=1-event.point.y/rect.height*2;
  const inverse=layer.camera.projectionMatrixInverse;const near=new THREE.Vector3(x,y,-1).applyMatrix4(inverse),far=new THREE.Vector3(x,y,1).applyMatrix4(inverse);raycaster.set(near,far.sub(near).normalize());
  const hit=raycaster.intersectObject(layer.surfaceMesh)[0];const blocker=raycaster.intersectObject(layer.contextMesh).find(hit=>showVegetation||layer.contextKinds[hit.faceIndex*3]!==2);
  const surfaceVisible=hit&&(!blocker||hit.distance<=blocker.distance+.02);
  const code=surfaceVisible?modelData.attributes.buildings[hit.faceIndex]:(blocker?modelData.contextBuildings[blocker.faceIndex]-1:-1);
  if(code<0){closeDetails();return;}
  if(code!==selectedBuilding){selectBuilding(code);return;}
  if(surfaceVisible)inspectLevel(code,modelData.attributes.levels[hit.faceIndex]);
  else{
    // A roof click selects the nearest recorded layer of the same building.
    let nearest=-1,distance=Infinity;
    for(let i=0;i<model.surfaceCount;i++)if(modelData.attributes.buildings[i]===code){
      const p=modelData.positions,z=(p[i*9+2]+p[i*9+5]+p[i*9+8])/3,d=Math.abs(z-blocker.point.z);
      if(d<distance){distance=d;nearest=i;}
    }
    if(nearest>=0)inspectLevel(code,modelData.attributes.levels[nearest]);
  }
});

return {open:openChip,hide(){++loadVersion;loadPromise=null;closeMetricMenu();inRegion=false;closeDetails();$('metric').hidden=true;$('display-layers').hidden=true;$('legend').hidden=true;$('loading').hidden=true;if(layer)map.setLayoutProperty('voxcity-model','visibility','none');},close:closeDetails};
}
