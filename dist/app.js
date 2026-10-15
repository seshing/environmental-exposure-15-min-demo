import {createModelViewer} from './model-view.js?v=582a1f0ce3';
const $=id=>document.getElementById(id),empty={type:'FeatureCollection',features:[]};
async function json(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error('Data unavailable');return response.json();}
const [index,cities,usa,states]=await Promise.all([json('data/project/index.json'),json('data/project/cities.geojson'),json('data/usa.geojson'),json('data/states.geojson')]);
const cityById=new Map(index.cities.map(city=>[city.id,city]));
const modelCities=new Set(index.chips.map(chip=>chip.city));
for(const feature of cities.features)feature.properties.hasModel=modelCities.has(feature.properties.id);
function modelPoints(data){return {...data,features:data.features.filter(f=>f.properties.available===true).map(f=>{const coordinates=f.geometry.coordinates.flat(Infinity),xs=coordinates.filter((_,i)=>i%2===0),ys=coordinates.filter((_,i)=>i%2===1);return {...f,geometry:{type:'Point',coordinates:[(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2]}};})};}
const map=new maplibregl.Map({container:'map',style:'map-style.json',center:[-99,38.5],zoom:3.25,minZoom:2,maxZoom:20,maxPitch:80,maxBounds:[[-179,-15],[-40,80]],canvasContextAttributes:{antialias:true},attributionControl:{compact:true}});
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'bottom-right');
const viewer=createModelViewer(map),metroCache=new Map();let stage='us',currentCity=null,currentMetro=null,mode='profile',selectedColor=null,cityMapMode='access',selectedEEI=null,requestId=0;
const ringColors={inside15:'#173b5f',mid15_30:'#2e6f9e',mid30_60:'#91c3e6',outside60:'#9db8a7',missing:'#c4cbc7'};
const citySizes=[[0,3.4],[250000,4.7],[500000,6.6],[1000000,8.1],[2000000,11.4],[5000000,14.7]];
let hovered=null,hoverFrame;
function clearHover(){
  cancelAnimationFrame(hoverFrame);
  if(hovered&&map.getSource(hovered.source))map.setFeatureState({source:hovered.source,id:hovered.id},{hover:false});
  hovered=null;$('map-hover').classList.remove('is-visible');$('map-hover').setAttribute('aria-hidden','true');map.getCanvas().style.cursor='';
}
function positionHover(){if(hovered){const point=map.project(hovered.coordinates);$('map-hover').style.left=point.x+'px';$('map-hover').style.top=point.y+'px';}}
function hoverColor(p){
  if(mode==='profile')return p.bivariate;
  const colors=[[8,48,107],[107,174,214],[247,251,255]],i=Number(p.r)<-.4?0:1,t=Math.max(0,Math.min(1,(Number(p.r)-[-.8,-.4][i])/.4));
  return 'rgb('+colors[i].map((v,k)=>Math.round(v+(colors[i+1][k]-v)*t)).join(',')+')';
}
function showHover(feature,source){
  const p=feature.properties,id=source==='cities'?p.id:p.chipId;
  map.getCanvas().style.cursor='pointer';
  if(hovered?.id===id&&hovered.source===source){positionHover();return;}
  clearHover();hovered={source,id,coordinates:feature.geometry.coordinates};map.setFeatureState({source,id},{hover:true});
  const city=source==='cities'?cityById.get(p.id):null;
  const cityName=city?.name.split(',')[0].trim(),state=city?.name.split(',').slice(1).join(',').trim();
  $('hover-title').textContent=city?cityName:'Zoom in to model';$('hover-state').textContent=city?state:'';
  const radius=city?citySizes.reduce((v,[min,size])=>p.population>=min?size:v,3.4):6;
  $('map-hover').style.setProperty('--dot-radius',radius+'px');$('map-hover').style.setProperty('--dot-color',city?hoverColor(p):'#17806c');
  $('map-hover').style.setProperty('--dot-border',city?(p.hasModel?1.2:.8)+'px':'1.5px');
  positionHover();$('map-hover').setAttribute('aria-hidden','false');void $('map-hover').offsetWidth;
  hoverFrame=requestAnimationFrame(()=>{if(hovered)$('map-hover').classList.add('is-visible');});map.getCanvas().style.cursor='pointer';
}
const format=new Intl.NumberFormat('en-US',{maximumFractionDigits:0});
const label=value=>Number.isFinite(value)?value.toFixed(2):'Unavailable';
function writeRoute(hash){if(location.hash!==hash)history.pushState(null,'',hash||location.pathname);}
function showLayers(ids,visible){for(const id of ids)if(map.getLayer(id))map.setLayoutProperty(id,'visibility',visible?'visible':'none');}
function fitUS(duration=0){map.fitBounds([[-125,24],[-66,50]],{padding:{left:innerWidth<700?20:70,right:innerWidth<700?20:70,top:190,bottom:130},bearing:0,pitch:0,duration});}
function setMode(next){
  mode=next;$('profile-mode').setAttribute('aria-pressed',String(mode==='profile'));$('local-mode').setAttribute('aria-pressed',String(mode==='local'));
  map.setPaintProperty('city-model-glow','circle-color',mode==='profile'?['get','bivariate']:['interpolate',['linear'],['get','r'],-.8,'#08306b',-.4,'#6baed6',0,'#f7fbff']);
  map.setPaintProperty('cities','circle-color',mode==='profile'?['get','bivariate']:['interpolate',['linear'],['get','r'],-.8,'#08306b',-.4,'#6baed6',0,'#f7fbff']);
  applyCityFilter();renderOverviewLegend();
}
function applyCityFilter(){
  const cityFilter=mode==='profile'?(selectedColor?['==',['get','bivariate'],selectedColor]:null):['==',['get','significant'],true];
  map.setFilter('cities',cityFilter);map.setFilter('city-model-glow',cityFilter?['all',['==',['get','hasModel'],true],cityFilter]:['==',['get','hasModel'],true]);
  const query=$('city-filter').value.toLowerCase();
  for(const button of $('city-options').children)button.hidden=!button.textContent.toLowerCase().includes(query)||(mode==='profile'&&selectedColor&&cityById.get(button.dataset.city).bivariate!==selectedColor);
  clearHover();
}
function renderOverviewLegend(){
  $('overview-legend').innerHTML=mode==='profile'?`<div class="legend-title">City profile</div><div class="bivariate-key">${[3,2,1].map(y=>[1,2,3].map(x=>{const color=index.bivariatePalette[x+'_'+y];return `<button data-color="${color}" style="background:${color}" aria-label="Accessibility ${['low','medium','high'][x-1]}, EEI ${['low','medium','high'][y-1]}" aria-pressed="${selectedColor===color}"></button>`;}).join('')).join('')}</div><div class="key-axis">EEI ↑ &nbsp; Accessibility →</div>`:`<div class="legend-title">Local r</div><div class="correlation-ramp"></div><div class="legend-labels"><span>−0.8</span><span>−0.4</span><span>0</span></div><div class="missing">p &lt; 0.01</div>`;
  for(const button of $('overview-legend').querySelectorAll('[data-color]'))button.onclick=()=>{selectedColor=selectedColor===button.dataset.color?null:button.dataset.color;applyCityFilter();renderOverviewLegend();};
  $('population-legend').innerHTML='<div class="legend-title">Population</div><div class="population-key"><span><i style="width:7px;height:7px"></i>&lt;0.25M</span><span><i style="width:16px;height:16px"></i>1–2M</span><span><i style="width:23px;height:23px"></i>2–5M</span><span><i style="width:29px;height:29px"></i>&gt;5M</span></div>';
}
function overview(push=true){
  ++requestId;document.body.classList.remove('has-msa-details');stage='us';currentCity=null;currentMetro=null;viewer.hide();clearHover();$('city-panel').hidden=true;$('ring-legend').hidden=true;$('cbg-note').hidden=true;$('msa-details').hidden=true;$('city-map-switch').hidden=true;$('chip-hint').hidden=true;$('back').hidden=true;$('location').textContent='United States';$('overview-switch').hidden=false;$('city-picker').hidden=false;$('overview-legend').hidden=false;$('population-legend').hidden=false;$('loading').hidden=true;
  showLayers(['cities','city-model-glow','state-outline'],true);showLayers(['msa-fill','msa-line','rings-fill','rings-line','chip-point','chip-glow','region-outline'],false);map.getSource('region').setData(empty);fitUS(800);if(push)writeRoute('');
}
function cityChart(city){
  const limits=key=>{const values=index.cities.map(c=>c[key]),min=Math.min(...values),max=Math.max(...values),pad=(max-min)*.07;return [Math.floor((min-pad)*20)/20,Math.ceil((max+pad)*20)/20];};
  const [xmin,xmax]=limits('access'),[ymin,ymax]=limits('eei');
  const x=v=>36+(v-xmin)/(xmax-xmin)*224,y=v=>250-(v-ymin)/(ymax-ymin)*224;
  const dots=index.cities.map(c=>`<circle cx="${x(c.access)}" cy="${y(c.eei)}" r="2.5" fill="${c.bivariate}" opacity=".55"><title>${c.name}</title></circle>`).join('');
  $('city-chart').innerHTML=`<svg viewBox="0 0 290 290" role="img" aria-label="Figure 2a national city accessibility and EEI; ${city.shortName} highlighted"><g class="chart-grid"><path d="M36 26H260 M36 138H260 M36 250H260 M36 26V250 M148 26V250 M260 26V250"/></g>${dots}<circle class="chart-building-halo" style="fill:${city.bivariate}" cx="${x(city.access)}" cy="${y(city.eei)}" r="12"/><circle class="chart-building" style="fill:${city.bivariate}" cx="${x(city.access)}" cy="${y(city.eei)}" r="5.5"><title>${city.shortName}: accessibility ${label(city.access)}, EEI ${label(city.eei)}</title></circle><g class="chart-label"><text x="36" y="14">EEI · z-score</text><text x="27" y="253" text-anchor="end">${label(ymin)}</text><text x="27" y="141" text-anchor="end">${label((ymin+ymax)/2)}</text><text x="27" y="29" text-anchor="end">${label(ymax)}</text><text x="36" y="265" text-anchor="middle">${label(xmin)}</text><text x="148" y="265" text-anchor="middle">${label((xmin+xmax)/2)}</text><text x="260" y="265" text-anchor="middle">${label(xmax)}</text><text x="148" y="284" text-anchor="middle">Accessibility · z-score →</text></g></svg>`;
  $('city-chart-note').textContent='';
}
function cityPanel(city,metro){
  const percentile=key=>100*index.cities.filter(c=>c[key]<city[key]).length/index.cities.length;
  const scale=(key,name)=>{const value=percentile(key);return `<div class="rank-heading"><span>${name}</span><strong>P${Math.round(value)}</strong></div><svg viewBox="0 0 290 48" role="img" aria-label="${name}: higher than ${value.toFixed(1)} percent of U.S. cities"><path class="percentile-track" d="M10 12H280"/><circle class="rank-point" data-label="${name}" data-value="${city[key]}" cx="${10+value*2.7}" cy="12" r="5" fill="${city.bivariate}"><title>${value.toFixed(1)}th percentile · raw value ${label(city[key])}</title></circle><g class="chart-label"><text x="10" y="39">0</text><text x="145" y="39" text-anchor="middle">50</text><text x="280" y="39" text-anchor="end">100</text></g></svg>`;};
  $('city-title').textContent=city.shortName;$('msa-name').textContent=city.name;
  $('city-ranks').innerHTML=scale('access','Accessibility')+scale('eei','Environmental exposure');
  for(const point of $('city-ranks').querySelectorAll('.rank-point')){
    point.onmouseenter=point.onmousemove=event=>{const tip=$('value-tooltip');tip.textContent=point.dataset.label+' · z-score '+Number(point.dataset.value).toFixed(3);tip.hidden=false;tip.style.left=Math.min(event.clientX+12,innerWidth-195)+'px';tip.style.top=Math.max(8,event.clientY-44)+'px';};
    point.onmouseleave=()=>{$('value-tooltip').hidden=true;};
  }
  cityChart(city);
  const rows=[['mid15_30','15–30 min'],['mid30_60','30–60 min'],['outside60','>60 min']];
  const values=rows.map(([key])=>metro.preservation?.[key]);
  if(values.some(Number.isFinite)){
    $('ring-loss').innerHTML=`<svg viewBox="0 0 290 54" role="img" aria-label="Percentage of the 15-minute population matching or exceeding outer-ring relative exposure"><path class="percentile-track" d="M10 15H280"/>${values.map((v,i)=>Number.isFinite(v)?`<circle cx="${10+Math.min(v,50)*5.4}" cy="15" r="4.5" fill="${ringColors[rows[i][0]]}" stroke="white" stroke-width="1"><title>${rows[i][1]}: ${v.toFixed(1)}% of the 15-minute population has relative exposure ≥ 1 against the outer ring</title></circle>${v>50?`<path d="M281 10L287 15L281 20" fill="none" stroke="${ringColors[rows[i][0]]}"/>`:""}`:'').join('')}<g class="chart-label"><text x="10" y="44">0%</text><text x="145" y="44" text-anchor="middle">25%</text><text x="280" y="44" text-anchor="end">50%</text></g></svg><div class="capacity-key">${rows.map(([key,name],i)=>`<span><i style="background:${ringColors[key]}"></i>${name}<strong>${Number.isFinite(values[i])?values[i].toFixed(1)+'%':'—'}</strong></span>`).join('')}</div>`;
  }else $('ring-loss').textContent='Unavailable';
  $('loss-note').textContent='';
  $('city-panel').hidden=false;document.body.classList.add('has-msa-details');
}
async function openCity(id,push=true){
  const city=cityById.get(id);if(!city)return;const token=++requestId;stage='msa';currentCity=city;viewer.hide();clearHover();$('overview-switch').hidden=true;$('city-picker').hidden=true;$('overview-legend').hidden=true;$('population-legend').hidden=true;$('back').hidden=false;$('back').setAttribute('aria-label','Back to United States');$('location').textContent=city.shortName+' MSA';$('msa-details').hidden=false;$('city-map-switch').hidden=false;$('city-panel').hidden=true;$('ring-legend').hidden=true;$('cbg-note').hidden=true;
  showLayers(['cities','city-model-glow','state-outline','region-outline','chip-point','chip-glow'],false);map.getSource('region').setData(empty);if(push)writeRoute('#msa/'+id);
  $('loading-text').textContent='Loading MSA';$('loading').hidden=false;$('retry').hidden=true;
  try{
    const metro=metroCache.get(id)||await json('data/project/metros/'+id+'.json');metroCache.set(id,metro);if(token!==requestId)return;currentMetro=metro;
    map.getSource('msa').setData(metro.boundary);showLayers(['msa-fill','msa-line'],true);
    const rings=metro.rings.length?await json('data/project/metros/'+id+'-rings.geojson'):empty;if(token!==requestId)return;map.getSource('rings').setData(rings);showLayers(['rings-fill','rings-line'],true);
    const chips=metro.hasChip?await json(metro.chipsFile||'data/project/washington-chips.geojson'):empty;if(token!==requestId)return;map.getSource('chips').setData(modelPoints(chips));showLayers(['chip-point','chip-glow'],metro.hasChip);
    cityPanel(city,metro);selectedEEI=null;renderCityMap();$('ring-legend').hidden=!metro.rings.length;$('loading').hidden=true;
    const side=innerWidth<700?20:60;map.fitBounds([[metro.bounds[0],metro.bounds[1]],[metro.bounds[2],metro.bounds[3]]],{padding:{left:side,right:innerWidth<700?side:360,top:140,bottom:innerWidth<700?Math.min($('city-panel').offsetHeight+82,innerHeight-220):100},bearing:0,pitch:0,duration:1000});
  }catch(error){if(token!==requestId)return;$('loading-text').textContent='MSA data unavailable';$('retry').hidden=false;$('retry').onclick=()=>openCity(id,false);}
}
async function openChip(chipId=null,push=true){
  const chip=chipId?index.chips.find(item=>item.id===chipId):index.chips.find(item=>item.city===currentCity?.id);if(!chip)return;stage='chip';clearHover();map.getCanvas().style.cursor='';document.body.classList.remove('has-msa-details');++requestId;$('msa-details').hidden=true;$('city-map-switch').hidden=true;$('chip-hint').hidden=true;$('city-panel').hidden=true;$('ring-legend').hidden=true;$('cbg-note').hidden=true;$('location').textContent='Model';$('back').setAttribute('aria-label','Back to MSA');showLayers(['msa-fill','msa-line','rings-fill','rings-line','chip-point','chip-glow'],false);showLayers(['region-outline'],true);if(push)writeRoute('#chip/'+chip.id);await viewer.open(chip.manifest);
}
$('profile-mode').onclick=()=>setMode('profile');$('local-mode').onclick=()=>setMode('local');
$('back').onclick=()=>stage==='chip'?openCity(currentCity.id):overview();
$('city-close').onclick=()=>{$('city-panel').hidden=true;document.body.classList.remove('has-msa-details');};
$('msa-details').onclick=()=>{$('city-panel').hidden=!$('city-panel').hidden;document.body.classList.toggle('has-msa-details',!$('city-panel').hidden);};
function closeCityMenu(){$('city-menu').hidden=true;$('city-search').setAttribute('aria-expanded','false');}
$('city-search').onclick=()=>{const open=$('city-menu').hidden;$('city-menu').hidden=!open;$('city-search').setAttribute('aria-expanded',String(open));if(open)$('city-filter').focus();};
for(const city of [...index.cities].sort((a,b)=>a.name.localeCompare(b.name))){const button=document.createElement('button');button.textContent=city.name+(index.chips.some(chip=>chip.city===city.id)?' · 3D':'');button.dataset.city=city.id;button.onclick=()=>{closeCityMenu();openCity(city.id);};$('city-options').append(button);}
$('city-filter').oninput=()=>{applyCityFilter();};
document.addEventListener('click',event=>{if(!event.target.closest('#city-picker'))closeCityMenu();});
function renderCityMap(){
  $('access-map').setAttribute('aria-pressed',String(cityMapMode==='access'));$('eei-map').setAttribute('aria-pressed',String(cityMapMode==='eei'));
  const colors=['#81373e','#ac7777','#aaa49a','#9cba91','#63985e'],breaks=index.eeiCBGBreaks;
  const color=cityMapMode==='access'?['match',['get','ring'],...Object.entries(ringColors).flat(),'#c4cbc7']:['step',['coalesce',['get','eei'],0],colors[0],...breaks.flatMap((value,i)=>[value,colors[i+1]])];
  map.setPaintProperty('rings-fill','fill-color',color);
  const filters=selectedEEI==null||cityMapMode!=='eei'?null:['all',['==',['get','hasExposure'],true],...(selectedEEI===0?[]:[['>=',['get','eei'],breaks[selectedEEI-1]]]),...(selectedEEI===colors.length-1?[]:[['<',['get','eei'],breaks[selectedEEI]]])];
  map.setFilter('rings-fill',filters);
  if(cityMapMode==='access')$('ring-legend').innerHTML='<div class="legend-title">CBG access-time rings</div>'+[['inside15','≤15 min'],['mid15_30','15–30 min'],['mid30_60','30–60 min'],['outside60','>60 min']].map(([key,name])=>`<div class="ring-key"><span style="background:${ringColors[key]}"></span>${name}</div>`).join('')+'<div class="tradeoff-source">Unfilled: no EEI data</div>';
  else{
    $('ring-legend').innerHTML='<div class="legend-title">CBG EEI · z-score</div><div class="eei-key">'+colors.map((color,i)=>`<button data-eei="${i}" aria-pressed="${selectedEEI===i}"><i style="background:${color}"></i>${['Very low','Low','Medium','High','Very high'][i]}</button>`).join('')+'</div><div class="tradeoff-source">National CBG quintiles · no data unfilled</div>';
    for(const button of $('ring-legend').querySelectorAll('[data-eei]'))button.onclick=()=>{const value=Number(button.dataset.eei);selectedEEI=selectedEEI===value?null:value;renderCityMap();};
  }
}
$('access-map').onclick=()=>{cityMapMode='access';renderCityMap();};$('eei-map').onclick=()=>{cityMapMode='eei';renderCityMap();};
function showCBG(feature){const p=feature.properties;$('cbg-note').textContent=`CBG ${p.GEOID} · ${Number(p.minutes).toFixed(1)} min${p.hasExposure===true||p.hasExposure==='true'?' · EEI '+Number(p.eei).toFixed(2):' · no EEI record'}`;$('cbg-note').hidden=false;}
map.on('click',event=>{
  if(event.originalEvent?.target?.closest?.('button,select')||map.isMoving())return;
  if(stage==='us'){const hit=map.queryRenderedFeatures(event.point,{layers:['cities']})[0];if(hit)openCity(hit.properties.id);}
  else if(stage==='msa'){
    const hits=map.queryRenderedFeatures(event.point,{layers:['chip-point','rings-fill']});const chip=hits.find(h=>h.layer.id==='chip-point'&&(h.properties.available===true||h.properties.available==='true'));
    if(chip){openChip(chip.properties.chipId);return;}const cbg=hits.find(h=>h.layer.id==='rings-fill');if(cbg)showCBG(cbg);
  }
});
map.on('mousemove',event=>{
  const layer=stage==='us'?'cities':stage==='msa'?'chip-point':null;
  if(!layer){clearHover();return;}
  const feature=map.queryRenderedFeatures(event.point,{layers:[layer]})[0];
  if(!feature){clearHover();return;}
  showHover(feature,stage==='us'?'cities':'chips');
});
map.on('mouseout',clearHover);map.on('move',positionHover);map.on('zoomstart',clearHover);

function followRoute(){const hash=location.hash;const match=hash.match(/^#msa\/(\d+)$/);if(match)openCity(match[1],false);else if(hash.startsWith('#chip/')){const chip=index.chips.find(item=>item.id===hash.slice(6));if(chip)openCity(chip.city,false).then(()=>{if(stage==='msa'&&currentCity?.id===chip.city&&currentMetro?.city?.id===chip.city&&location.hash==='#chip/'+chip.id)openChip(chip.id,false);});else overview(false);}else if(hash==='#washington-dc')openCity('47900',false);else overview(false);}
window.addEventListener('popstate',followRoute);window.addEventListener('keydown',event=>{if(event.key==='Escape'){viewer.close();closeCityMenu();$('cbg-note').hidden=true;}});
map.once('load',()=>{
  const rings=usa.geometry.coordinates.map(p=>p[0]);map.addSource('usa-mask',{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]],...rings]}}});map.addLayer({id:'usa-mask',type:'fill',source:'usa-mask',maxzoom:10,paint:{'fill-color':'#f7f8f6','fill-opacity':.7}});
  map.addSource('states',{type:'geojson',data:states});map.addLayer({id:'state-outline',type:'line',source:'states',maxzoom:10,paint:{'line-color':'#aebdb3','line-width':.55,'line-opacity':.5}});
  map.addSource('usa',{type:'geojson',data:usa});map.addLayer({id:'usa-outline',type:'line',source:'usa',maxzoom:10,paint:{'line-color':'#647f70','line-opacity':.25,'line-width':1}});
  for(const source of ['msa','rings','chips','region'])map.addSource(source,{type:'geojson',data:empty,...(source==='chips'?{promoteId:'chipId'}:{})});
  map.addSource('cities',{type:'geojson',data:cities,promoteId:'id'});
  const cityRadius=['step',['get','population'],citySizes[0][1],...citySizes.slice(1).flat()];
  map.addLayer({id:'city-model-glow',type:'circle',source:'cities',filter:['==',['get','hasModel'],true],paint:{'circle-color':['get','bivariate'],'circle-radius':['+',cityRadius,8],'circle-blur':.85,'circle-opacity':.28}});
  map.addLayer({id:'cities',type:'circle',source:'cities',paint:{'circle-color':['get','bivariate'],'circle-radius':cityRadius,'circle-opacity':['case',['boolean',['feature-state','hover'],false],0,.9],'circle-stroke-opacity':['case',['boolean',['feature-state','hover'],false],0,1],'circle-stroke-color':'#ffffff','circle-stroke-width':['case',['==',['get','hasModel'],true],1.2,.8]}});
  map.addLayer({id:'msa-fill',type:'fill',source:'msa',layout:{visibility:'none'},paint:{'fill-color':'#bbc9c0','fill-opacity':0}});map.addLayer({id:'msa-line',type:'line',source:'msa',layout:{visibility:'none'},paint:{'line-color':'#426754','line-width':1.4,'line-opacity':.7}});
  const match=['match',['get','ring'],...Object.entries(ringColors).flat(),'#c4cbc7'];map.addLayer({id:'rings-fill',type:'fill',source:'rings',layout:{visibility:'none'},paint:{'fill-color':match,'fill-opacity':['case',['==',['get','hasExposure'],true],.58,0]}});map.addLayer({id:'rings-line',type:'line',source:'rings',layout:{visibility:'none'},paint:{'line-color':'#ffffff','line-width':.35,'line-opacity':.7}});
  map.addLayer({id:'chip-glow',type:'circle',source:'chips',layout:{visibility:'none'},paint:{'circle-color':'#229c70','circle-radius':17,'circle-blur':.85,'circle-opacity':.28}});
  map.addLayer({id:'chip-point',type:'circle',source:'chips',layout:{visibility:'none'},paint:{'circle-color':'#17806c','circle-radius':6,'circle-opacity':['case',['boolean',['feature-state','hover'],false],0,1],'circle-stroke-opacity':['case',['boolean',['feature-state','hover'],false],0,1],'circle-stroke-color':'#ffffff','circle-stroke-width':1.5}});
  map.addLayer({id:'region-outline',type:'line',source:'region',paint:{'line-color':'#17806c','line-width':1,'line-opacity':.3}});
  renderOverviewLegend();followRoute();
});
