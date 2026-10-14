import {createModelViewer} from './model-view.js';
const $=id=>document.getElementById(id),empty={type:'FeatureCollection',features:[]};
async function json(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error('Data unavailable');return response.json();}
const [index,cities,usa,states]=await Promise.all([json('data/project/index.json'),json('data/project/cities.geojson'),json('data/usa.geojson'),json('data/states.geojson')]);
const cityById=new Map(index.cities.map(city=>[city.id,city]));
const map=new maplibregl.Map({container:'map',style:'map-style.json',center:[-99,38.5],zoom:3.25,minZoom:2,maxZoom:20,maxPitch:80,maxBounds:[[-179,-15],[-40,80]],canvasContextAttributes:{antialias:true},attributionControl:{compact:true}});
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'bottom-right');
const viewer=createModelViewer(map),metroCache=new Map();let stage='us',currentCity=null,currentMetro=null,mode='profile',selectedColor=null,cityMapMode='access',selectedEEI=null,requestId=0;
const ringColors={inside15:'#173b5f',mid15_30:'#2e6f9e',mid30_60:'#91c3e6',outside60:'#9db8a7',missing:'#c4cbc7'};
const tooltip=new maplibregl.Popup({closeButton:false,closeOnClick:false,className:'map-tooltip',offset:13});
const format=new Intl.NumberFormat('en-US',{maximumFractionDigits:0});
const label=value=>Number.isFinite(value)?value.toFixed(2):'Unavailable';
function writeRoute(hash){if(location.hash!==hash)history.pushState(null,'',hash||location.pathname);}
function showLayers(ids,visible){for(const id of ids)if(map.getLayer(id))map.setLayoutProperty(id,'visibility',visible?'visible':'none');}
function fitUS(duration=0){map.fitBounds([[-125,24],[-66,50]],{padding:{left:innerWidth<700?20:70,right:innerWidth<700?20:70,top:190,bottom:130},bearing:0,pitch:0,duration});}
function setMode(next){
  mode=next;$('profile-mode').setAttribute('aria-pressed',String(mode==='profile'));$('local-mode').setAttribute('aria-pressed',String(mode==='local'));
  map.setPaintProperty('cities','circle-color',mode==='profile'?['get','bivariate']:['interpolate',['linear'],['get','r'],-.8,'#08306b',-.4,'#6baed6',0,'#f7fbff']);
  applyCityFilter();renderOverviewLegend();
}
function applyCityFilter(){
  map.setFilter('cities',mode==='profile'?(selectedColor?['==',['get','bivariate'],selectedColor]:null):['==',['get','significant'],true]);
  const query=$('city-filter').value.toLowerCase();
  for(const button of $('city-options').children)button.hidden=!button.textContent.toLowerCase().includes(query)||(mode==='profile'&&selectedColor&&cityById.get(button.dataset.city).bivariate!==selectedColor);
  tooltip.remove();
}
function renderOverviewLegend(){
  $('overview-legend').innerHTML=mode==='profile'?`<div class="legend-title">City profile</div><div class="bivariate-key">${[3,2,1].map(y=>[1,2,3].map(x=>{const color=index.bivariatePalette[x+'_'+y];return `<button data-color="${color}" style="background:${color}" aria-label="Accessibility ${['low','medium','high'][x-1]}, EEI ${['low','medium','high'][y-1]}" aria-pressed="${selectedColor===color}"></button>`;}).join('')).join('')}</div><div class="key-axis">EEI ↑ &nbsp; Accessibility →</div>`:`<div class="legend-title">Local r</div><div class="correlation-ramp"></div><div class="legend-labels"><span>−0.8</span><span>−0.4</span><span>0</span></div><div class="missing">p &lt; 0.01</div>`;
  for(const button of $('overview-legend').querySelectorAll('[data-color]'))button.onclick=()=>{selectedColor=selectedColor===button.dataset.color?null:button.dataset.color;applyCityFilter();renderOverviewLegend();};
  $('population-legend').innerHTML='<div class="legend-title">Population</div><div class="population-key"><span><i style="width:7px;height:7px"></i>&lt;0.25M</span><span><i style="width:16px;height:16px"></i>1–2M</span><span><i style="width:23px;height:23px"></i>2–5M</span><span><i style="width:29px;height:29px"></i>&gt;5M</span></div>';
}
function overview(push=true){
  ++requestId;document.body.classList.remove('has-msa-details');stage='us';currentCity=null;currentMetro=null;viewer.hide();tooltip.remove();$('city-panel').hidden=true;$('ring-legend').hidden=true;$('cbg-note').hidden=true;$('msa-details').hidden=true;$('city-map-switch').hidden=true;$('chip-hint').hidden=true;$('back').hidden=true;$('location').textContent='United States';$('overview-switch').hidden=false;$('city-picker').hidden=false;$('overview-legend').hidden=false;$('population-legend').hidden=false;$('loading').hidden=true;
  showLayers(['cities','state-outline'],true);showLayers(['msa-fill','msa-line','rings-fill','rings-line','chip-fill','chip-line','chip-label','region-outline'],false);map.getSource('region').setData(empty);fitUS(800);if(push)writeRoute('');
}
function cityChart(city){
  const limits=key=>{const values=index.cities.map(c=>c[key]),min=Math.min(...values),max=Math.max(...values),pad=(max-min)*.07;return [Math.floor((min-pad)*20)/20,Math.ceil((max+pad)*20)/20];};
  const [xmin,xmax]=limits('access'),[ymin,ymax]=limits('eei');
  const x=v=>36+(v-xmin)/(xmax-xmin)*224,y=v=>250-(v-ymin)/(ymax-ymin)*224;
  const dots=index.cities.map(c=>`<circle cx="${x(c.access)}" cy="${y(c.eei)}" r="2.5" fill="${c.bivariate}" opacity=".55"><title>${c.name}</title></circle>`).join('');
  $('city-chart').innerHTML=`<svg viewBox="0 0 290 290" role="img" aria-label="Figure 2a national city accessibility and EEI; ${city.shortName} highlighted"><g class="chart-grid"><path d="M36 26H260 M36 138H260 M36 250H260 M36 26V250 M148 26V250 M260 26V250"/></g>${dots}<circle class="chart-building-halo" style="fill:${city.bivariate}" cx="${x(city.access)}" cy="${y(city.eei)}" r="12"/><circle class="chart-building" style="fill:${city.bivariate}" cx="${x(city.access)}" cy="${y(city.eei)}" r="5.5"><title>${city.shortName}: accessibility ${label(city.access)}, EEI ${label(city.eei)}</title></circle><g class="chart-label"><text x="36" y="14">EEI</text><text x="27" y="253" text-anchor="end">${label(ymin)}</text><text x="27" y="141" text-anchor="end">${label((ymin+ymax)/2)}</text><text x="27" y="29" text-anchor="end">${label(ymax)}</text><text x="36" y="265" text-anchor="middle">${label(xmin)}</text><text x="148" y="265" text-anchor="middle">${label((xmin+xmax)/2)}</text><text x="260" y="265" text-anchor="middle">${label(xmax)}</text><text x="148" y="284" text-anchor="middle">City accessibility →</text></g></svg>`;
  $('city-chart-note').textContent='';
}
function cityPanel(city,metro){
  const percentile=key=>100*index.cities.filter(c=>c[key]<city[key]).length/index.cities.length;
  const scale=(key,name)=>{const value=percentile(key);return `<div class="rank-heading"><span>${name}</span><strong>P${Math.round(value)}</strong></div><svg viewBox="0 0 290 48" role="img" aria-label="${name}: higher than ${value.toFixed(1)} percent of U.S. cities"><path class="percentile-track" d="M10 12H280"/><circle class="rank-point" data-label="${name}" data-value="${city[key]}" cx="${10+value*2.7}" cy="12" r="5" fill="${city.bivariate}"><title>${value.toFixed(1)}th percentile · raw value ${label(city[key])}</title></circle><g class="chart-label"><text x="10" y="39">0</text><text x="145" y="39" text-anchor="middle">50</text><text x="280" y="39" text-anchor="end">100</text></g></svg>`;};
  $('city-title').textContent=city.shortName;$('msa-name').textContent=city.name;
  $('city-ranks').innerHTML=scale('access','Accessibility')+scale('eei','Environmental exposure');
  for(const point of $('city-ranks').querySelectorAll('.rank-point')){
    point.onmouseenter=point.onmousemove=event=>{const tip=$('value-tooltip');tip.textContent=point.dataset.label+' · '+Number(point.dataset.value).toFixed(3);tip.hidden=false;tip.style.left=Math.min(event.clientX+12,innerWidth-195)+'px';tip.style.top=Math.max(8,event.clientY-44)+'px';};
    point.onmouseleave=()=>{$('value-tooltip').hidden=true;};
  }
  cityChart(city);
  const rows=[['mid15_30','15–30 min'],['mid30_60','30–60 min'],['outside60','>60 min']];
  const values=rows.map(([key])=>metro.preservation?.[key]);
  if(values.some(Number.isFinite)){
    $('ring-loss').innerHTML=`<svg viewBox="0 0 290 54" role="img" aria-label="Percentage of the 15-minute population matching or exceeding outer-ring mean exposure"><path class="percentile-track" d="M10 15H280"/>${values.map((v,i)=>Number.isFinite(v)?`<circle cx="${10+Math.min(v,50)*5.4}" cy="15" r="4.5" fill="${ringColors[rows[i][0]]}" stroke="white" stroke-width="1"><title>${rows[i][1]}: ${v.toFixed(1)}% of the 15-minute population has exposure at least as high as the ring mean</title></circle>${v>50?`<path d="M281 10L287 15L281 20" fill="none" stroke="${ringColors[rows[i][0]]}"/>`:""}`:'').join('')}<g class="chart-label"><text x="10" y="44">0%</text><text x="145" y="44" text-anchor="middle">25%</text><text x="280" y="44" text-anchor="end">50%</text></g></svg><div class="capacity-key">${rows.map(([key,name],i)=>`<span><i style="background:${ringColors[key]}"></i>${name}<strong>${Number.isFinite(values[i])?values[i].toFixed(1)+'%':'—'}</strong></span>`).join('')}</div>`;
  }else $('ring-loss').textContent='Unavailable';
  $('loss-note').textContent='';
  $('city-panel').hidden=false;document.body.classList.add('has-msa-details');
}
async function openCity(id,push=true){
  const city=cityById.get(id);if(!city)return;const token=++requestId;stage='msa';currentCity=city;viewer.hide();tooltip.remove();$('overview-switch').hidden=true;$('city-picker').hidden=true;$('overview-legend').hidden=true;$('population-legend').hidden=true;$('back').hidden=false;$('back').setAttribute('aria-label','Back to United States');$('location').textContent=city.shortName+' MSA';$('msa-details').hidden=false;$('city-map-switch').hidden=false;$('city-panel').hidden=true;$('ring-legend').hidden=true;$('cbg-note').hidden=true;
  showLayers(['cities','state-outline','region-outline','chip-fill','chip-line','chip-label'],false);map.getSource('region').setData(empty);if(push)writeRoute('#msa/'+id);
  $('loading-text').textContent='Loading MSA';$('loading').hidden=false;$('retry').hidden=true;
  try{
    const metro=metroCache.get(id)||await json('data/project/metros/'+id+'.json');metroCache.set(id,metro);if(token!==requestId)return;currentMetro=metro;
    map.getSource('msa').setData(metro.boundary);showLayers(['msa-fill','msa-line'],true);
    const rings=metro.rings.length?await json('data/project/metros/'+id+'-rings.geojson'):empty;if(token!==requestId)return;map.getSource('rings').setData(rings);showLayers(['rings-fill','rings-line'],true);
    const chips=metro.hasChip?await json(metro.chipsFile||'data/project/washington-chips.geojson'):empty;if(token!==requestId)return;map.getSource('chips').setData(chips);showLayers(['chip-fill','chip-line','chip-label'],metro.hasChip);
    cityPanel(city,metro);selectedEEI=null;renderCityMap();$('ring-legend').hidden=!metro.rings.length;$('loading').hidden=true;
    const side=innerWidth<700?20:60;map.fitBounds([[metro.bounds[0],metro.bounds[1]],[metro.bounds[2],metro.bounds[3]]],{padding:{left:side,right:innerWidth<700?side:360,top:140,bottom:innerWidth<700?Math.min($('city-panel').offsetHeight+82,innerHeight-220):100},bearing:0,pitch:0,duration:1000});
  }catch(error){if(token!==requestId)return;$('loading-text').textContent='MSA data unavailable';$('retry').hidden=false;$('retry').onclick=()=>openCity(id,false);}
}
async function openChip(chipId=null,push=true){
  const chip=chipId?index.chips.find(item=>item.id===chipId):index.chips.find(item=>item.city===currentCity?.id);if(!chip)return;stage='chip';tooltip.remove();map.getCanvas().style.cursor='';document.body.classList.remove('has-msa-details');++requestId;$('msa-details').hidden=true;$('city-map-switch').hidden=true;$('chip-hint').hidden=true;$('city-panel').hidden=true;$('ring-legend').hidden=true;$('cbg-note').hidden=true;$('location').textContent='Model';$('back').setAttribute('aria-label','Back to MSA');showLayers(['msa-fill','msa-line','rings-fill','rings-line','chip-fill','chip-line','chip-label'],false);showLayers(['region-outline'],true);if(push)writeRoute('#chip/'+chip.id);await viewer.open(chip.manifest);
}
$('profile-mode').onclick=()=>setMode('profile');$('local-mode').onclick=()=>setMode('local');
$('back').onclick=()=>stage==='chip'?openCity(currentCity.id):overview();
$('city-close').onclick=()=>{$('city-panel').hidden=true;document.body.classList.remove('has-msa-details');};
$('msa-details').onclick=()=>{$('city-panel').hidden=!$('city-panel').hidden;document.body.classList.toggle('has-msa-details',!$('city-panel').hidden);};
$('info').onclick=()=>{const hidden=$('help').hidden;$('help').hidden=!hidden;$('info').setAttribute('aria-expanded',String(hidden));};
function closeCityMenu(){$('city-menu').hidden=true;$('city-search').setAttribute('aria-expanded','false');}
$('city-search').onclick=()=>{const open=$('city-menu').hidden;$('city-menu').hidden=!open;$('city-search').setAttribute('aria-expanded',String(open));if(open)$('city-filter').focus();};
for(const city of [...index.cities].sort((a,b)=>a.name.localeCompare(b.name))){const button=document.createElement('button');button.textContent=city.name+(index.chips.some(chip=>chip.city===city.id)?' · 3D':'');button.dataset.city=city.id;button.onclick=()=>{closeCityMenu();openCity(city.id);};$('city-options').append(button);}
$('city-filter').oninput=()=>{applyCityFilter();};
document.addEventListener('click',event=>{if(!event.target.closest('#city-picker'))closeCityMenu();});
function renderCityMap(){
  $('access-map').setAttribute('aria-pressed',String(cityMapMode==='access'));$('eei-map').setAttribute('aria-pressed',String(cityMapMode==='eei'));
  const colors=['#81373e','#ac7777','#aaa49a','#9cba91','#63985e'],breaks=index.eeiCBGBreaks;
  const color=cityMapMode==='access'?['match',['get','ring'],...Object.entries(ringColors).flat(),'#c4cbc7']:['step',['coalesce',['get','eei_cbg_equal'],0],colors[0],...breaks.flatMap((value,i)=>[value,colors[i+1]])];
  map.setPaintProperty('rings-fill','fill-color',color);
  const filters=selectedEEI==null||cityMapMode!=='eei'?null:['all',['==',['get','hasExposure'],true],['>=',['get','eei_cbg_equal'],selectedEEI===0?0:breaks[selectedEEI-1]],[selectedEEI===colors.length-1?'<=':'<',['get','eei_cbg_equal'],selectedEEI===colors.length-1?1:breaks[selectedEEI]]];
  map.setFilter('rings-fill',filters);
  if(cityMapMode==='access')$('ring-legend').innerHTML='<div class="legend-title">CBG access-time rings</div>'+[['inside15','≤15 min'],['mid15_30','15–30 min'],['mid30_60','30–60 min'],['outside60','>60 min']].map(([key,name])=>`<div class="ring-key"><span style="background:${ringColors[key]}"></span>${name}</div>`).join('')+'<div class="tradeoff-source">Unfilled: no EEI data</div>';
  else{
    $('ring-legend').innerHTML='<div class="legend-title">CBG EEI</div><div class="eei-key">'+colors.map((color,i)=>`<button data-eei="${i}" aria-pressed="${selectedEEI===i}"><i style="background:${color}"></i>${['Very low','Low','Medium','High','Very high'][i]}</button>`).join('')+'</div><div class="tradeoff-source">National CBG quintiles · no data unfilled</div>';
    for(const button of $('ring-legend').querySelectorAll('[data-eei]'))button.onclick=()=>{const value=Number(button.dataset.eei);selectedEEI=selectedEEI===value?null:value;renderCityMap();};
  }
}
$('access-map').onclick=()=>{cityMapMode='access';renderCityMap();};$('eei-map').onclick=()=>{cityMapMode='eei';renderCityMap();};
function showCBG(feature){const p=feature.properties;$('cbg-note').textContent=`CBG ${p.GEOID} · ${Number(p.minutes).toFixed(1)} min${p.hasExposure===true||p.hasExposure==='true'?' · EEI '+Number(p.eei_cbg_equal).toFixed(2):' · no EEI record'}`;$('cbg-note').hidden=false;}
map.on('click',event=>{
  if(event.originalEvent?.target?.closest?.('button,select')||map.isMoving())return;
  if(stage==='us'){const hit=map.queryRenderedFeatures(event.point,{layers:['cities']})[0];if(hit)openCity(hit.properties.id);}
  else if(stage==='msa'){
    const hits=map.queryRenderedFeatures(event.point,{layers:['chip-fill','rings-fill']});const chip=hits.find(h=>h.layer.id==='chip-fill'&&(h.properties.available===true||h.properties.available==='true'));
    if(chip){openChip(chip.properties.chipId);return;}const cbg=hits.find(h=>h.layer.id==='rings-fill');if(cbg)showCBG(cbg);
  }
});
map.on('mousemove',event=>{
  const layerName=stage==='us'?'cities':stage==='msa'?'chip-fill':null;if(!layerName){tooltip.remove();$('chip-hint').hidden=true;map.getCanvas().style.cursor='';return;}
  const features=map.queryRenderedFeatures(event.point,{layers:[layerName]});const f=features[0];map.getCanvas().style.cursor=f?'pointer':'';
  if(stage==='msa'){
    const available=f&&(f.properties.available===true||f.properties.available==='true');$('chip-hint').hidden=true;map.getCanvas().style.cursor=available?'pointer':'';
    if(available)tooltip.setLngLat(event.lngLat).setText('zoom in to model').addTo(map);else tooltip.remove();return;
  }
  $('chip-hint').hidden=true;if(!f){tooltip.remove();return;}tooltip.setLngLat(event.lngLat).setText(f.properties.name).addTo(map);
});
map.on('mouseout',()=>{$('chip-hint').hidden=true;tooltip.remove();});
function followRoute(){const hash=location.hash;const match=hash.match(/^#msa\/(\d+)$/);if(match)openCity(match[1],false);else if(hash.startsWith('#chip/')){const chip=index.chips.find(item=>item.id===hash.slice(6));if(chip)openCity(chip.city,false).then(()=>{if(stage==='msa'&&currentCity?.id===chip.city&&currentMetro?.city?.id===chip.city&&location.hash==='#chip/'+chip.id)openChip(chip.id,false);});else overview(false);}else if(hash==='#washington-dc')openCity('47900',false);else overview(false);}
window.addEventListener('popstate',followRoute);window.addEventListener('keydown',event=>{if(event.key==='Escape'){viewer.close();closeCityMenu();$('help').hidden=true;$('cbg-note').hidden=true;}});
map.once('load',()=>{
  const rings=usa.geometry.coordinates.map(p=>p[0]);map.addSource('usa-mask',{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]],...rings]}}});map.addLayer({id:'usa-mask',type:'fill',source:'usa-mask',maxzoom:10,paint:{'fill-color':'#f7f8f6','fill-opacity':.7}});
  map.addSource('states',{type:'geojson',data:states});map.addLayer({id:'state-outline',type:'line',source:'states',maxzoom:10,paint:{'line-color':'#aebdb3','line-width':.55,'line-opacity':.5}});
  map.addSource('usa',{type:'geojson',data:usa});map.addLayer({id:'usa-outline',type:'line',source:'usa',maxzoom:10,paint:{'line-color':'#647f70','line-opacity':.25,'line-width':1}});
  for(const source of ['msa','rings','chips','region'])map.addSource(source,{type:'geojson',data:empty});
  map.addSource('cities',{type:'geojson',data:cities});map.addLayer({id:'cities',type:'circle',source:'cities',paint:{'circle-color':['get','bivariate'],'circle-radius':['step',['get','population'],3.4,250000,4.7,500000,6.6,1000000,8.1,2000000,11.4,5000000,14.7],'circle-opacity':.9,'circle-stroke-color':'#ffffff','circle-stroke-width':.8}});
  map.addLayer({id:'msa-fill',type:'fill',source:'msa',layout:{visibility:'none'},paint:{'fill-color':'#bbc9c0','fill-opacity':0}});map.addLayer({id:'msa-line',type:'line',source:'msa',layout:{visibility:'none'},paint:{'line-color':'#426754','line-width':1.4,'line-opacity':.7}});
  const match=['match',['get','ring'],...Object.entries(ringColors).flat(),'#c4cbc7'];map.addLayer({id:'rings-fill',type:'fill',source:'rings',layout:{visibility:'none'},paint:{'fill-color':match,'fill-opacity':['case',['==',['get','hasExposure'],true],.58,0]}});map.addLayer({id:'rings-line',type:'line',source:'rings',layout:{visibility:'none'},paint:{'line-color':'#ffffff','line-width':.35,'line-opacity':.7}});
  map.addLayer({id:'chip-fill',type:'fill',source:'chips',layout:{visibility:'none'},paint:{'fill-color':['case',['==',['get','available'],true],'#229c70','#52695d'],'fill-opacity':['case',['==',['get','available'],true],.30,.035]}});map.addLayer({id:'chip-line',type:'line',source:'chips',layout:{visibility:'none'},paint:{'line-color':['case',['==',['get','available'],true],'#12754e','#466754'],'line-width':['case',['==',['get','available'],true],2.5,.55],'line-opacity':['case',['==',['get','available'],true],1,.35]}});
  map.addLayer({id:'chip-label',type:'symbol',source:'chips',filter:['==',['get','available'],true],minzoom:7,layout:{visibility:'none','text-field':'','text-font':['Noto Sans Regular'],'text-size':12,'text-allow-overlap':true},paint:{'text-color':'#126640','text-halo-color':'#ffffff','text-halo-width':1.5}});
  map.addLayer({id:'region-outline',type:'line',source:'region',paint:{'line-color':'#17806c','line-width':1,'line-opacity':.3}});
  renderOverviewLegend();followRoute();
});
