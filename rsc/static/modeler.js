(function(){
'use strict';
var CFG=window.RSC_MODEL||{};
var ROOT=document.querySelector('.rsc-modeler');
var $=function(id){return document.getElementById(id);};

/* ---------- finishes ---------- */
var PAL={
  siding:[['White','#F0F0EC'],['Light gray','#C4C9CC'],['Greige','#B7AC9B'],['Sage green','#98A58B'],['Navy','#2F4158'],['Natural cedar','#B98B5E'],['Charcoal','#3E4347'],['Barn red','#8E3B34']],
  paint:[['Warm white','#EFEBE0'],['Light gray','#CFD2D3'],['Greige','#BDB2A1'],['Soft blue','#A9BFCB'],['Sage','#A7B496'],['Navy accent','#35475E']],
  floor:[['Light oak','#CDA974'],['Walnut','#6F4C34'],['Reclaimed barnwood','#8C7459'],['Gray tile','#8E9396'],['Slate','#4D5357'],['Concrete','#A6A7A3']],
  trim:[['White','#F4F4F1'],['Black','#26292B'],['Walnut','#6F4C34'],['Barn red','#8E3B34'],['Forest green','#2F5D46'],['Navy','#2F4158']]
};
var FINL={siding:'Exterior siding',paint:'Interior walls',floor:'Floor',trim:'Doors and trim'};
var FINK=['siding','paint','floor','trim'];
function hexOf(k){var n=(S.fin&&S.fin[k]&&S.fin[k].name)||PAL[k][0][0];for(var i=0;i<PAL[k].length;i++)if(PAL[k][i][0]===n)return PAL[k][i][1];return PAL[k][0][1];}
function defFin(){var f={};FINK.forEach(function(k){f[k]={name:k==='siding'?'Light gray':k==='floor'?'Light oak':PAL[k][0][0],note:''};});return f;}

/* ---------- state ---------- */
function newRoom(id,name,x,y,w,d,h,t){return {id:id,name:name,x:x,y:y,w:w,d:d,h:h,t:t,open:[]};}
function BLANK(){return {v:2,rooms:[newRoom(1,'Room 1',0,0,144,144,96,5)],sel:1,nextRoom:2,nextOpen:1,fin:defFin()};}
function SAMPLE(){
  var s=BLANK();
  s.rooms[0].name='Porch';s.rooms[0].w=168;s.rooms[0].d=144;
  s.rooms[0].open=[
    {id:1,type:'door',wall:'S',off:24,w:36,h:80,sill:0},
    {id:2,type:'window',wall:'S',off:84,w:48,h:48,sill:30},
    {id:3,type:'door',wall:'E',off:54,w:36,h:80,sill:0},
    {id:4,type:'window',wall:'W',off:36,w:48,h:48,sill:30},
    {id:5,type:'window',wall:'N',off:60,w:48,h:36,sill:42}];
  var m=newRoom(2,'Mudroom',168,0,96,144,96,5);
  m.open=[{id:6,type:'door',wall:'W',off:54,w:36,h:80,sill:0},{id:7,type:'door',wall:'S',off:30,w:36,h:80,sill:0},{id:8,type:'window',wall:'E',off:54,w:36,h:36,sill:42}];
  s.rooms.push(m);s.sel=1;s.nextRoom=3;s.nextOpen=9;
  return s;
}
function normalize(raw){
  if(!raw)return BLANK();
  if(raw.rooms&&raw.rooms.length){
    var s=raw;s.v=2;if(!s.fin)s.fin=defFin();FINK.forEach(function(k){if(!s.fin[k])s.fin[k]=defFin()[k];});
    var maxO=0,maxR=0;s.rooms.forEach(function(r){maxR=Math.max(maxR,r.id);r.open=r.open||[];r.open.forEach(function(o){maxO=Math.max(maxO,o.id);});});
    s.nextOpen=Math.max(s.nextOpen||1,maxO+1);s.nextRoom=Math.max(s.nextRoom||1,maxR+1);
    if(!s.rooms.some(function(r){return r.id===s.sel;}))s.sel=s.rooms[0].id;
    return s;
  }
  if(raw.open&&raw.w>0){ /* version 1: a single room */
    var s1=BLANK(),r=s1.rooms[0];r.w=raw.w;r.d=raw.d;r.h=raw.h;r.t=raw.t;r.open=raw.open;
    var mo=0;r.open.forEach(function(o){mo=Math.max(mo,o.id);});s1.nextOpen=Math.max(raw.next||1,mo+1);return s1;
  }
  return BLANK();
}
var S=normalize(CFG.state);
if(CFG.demo&&!CFG.state)S=SAMPLE();
function R(){for(var i=0;i<S.rooms.length;i++)if(S.rooms[i].id===S.sel)return S.rooms[i];return S.rooms[0];}
var saveTimer=null,firstSave=true;
function save(){
  if(firstSave){firstSave=false;return;}
  if(!CFG.saveUrl)return;
  clearTimeout(saveTimer);
  var m=$('savemsg');if(m)m.textContent='Saving...';
  saveTimer=setTimeout(function(){
    var body=new URLSearchParams();body.set('csrf',CFG.csrf||'');body.set('model',JSON.stringify(S));
    fetch(CFG.saveUrl,{method:'POST',body:body}).then(function(r){
      if(!r.ok)throw new Error('bad');if(m)m.textContent='Saved with this job.';
    }).catch(function(){if(m)m.textContent='Not saved. Reload the page and try again.';});
  },600);
}

/* ---------- length parsing and formatting (everything stored in inches) ---------- */
function parseFrac(s){
  s=s.trim(); if(!s) return NaN;
  var m=s.match(/^(\d+(?:\.\d+)?)?\s*(?:(\d+)\/(\d+))?$/);
  if(!m||(!m[1]&&!m[2])) return NaN;
  return (m[1]?parseFloat(m[1]):0)+(m[2]?(+m[2])/(+m[3]):0);
}
function parseLen(str){
  var s=String(str).trim().toLowerCase().replace(/[”″]/g,'"').replace(/[’′]/g,"'");
  s=s.replace(/\s*(?:"|in\.?)\s*$/,'').trim();
  var m=s.match(/^(\d+(?:\.\d+)?)\s*(?:'|ft\.?|-)\s*(.*)$/);
  if(m){var rest=m[2].trim();var i=rest===''?0:parseFrac(rest);if(isNaN(i))return NaN;return parseFloat(m[1])*12+i;}
  return parseFrac(s);
}
function gcd(a,b){return b?gcd(b,a%b):a;}
function fmt(inches){
  var neg=inches<0;inches=Math.abs(inches);
  var total=Math.round(inches*8)/8, ft=Math.floor(total/12+1e-9), rem=total-ft*12;
  var whole=Math.floor(rem+1e-9), frac=Math.round((rem-whole)*8);
  if(frac===8){whole++;frac=0;} if(whole===12){ft++;whole=0;}
  var fs=''; if(frac){var g=gcd(frac,8);fs=' '+(frac/g)+'/'+(8/g);}
  return (neg?'-':'')+(ft?(ft+"'-"+whole+fs+'"'):(whole+fs+'"'));
}
function esc(x){return String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}
function q(x){return x.replace(/"/g,'&quot;');}

/* ---------- walls ---------- */
var WALLS=['N','E','S','W'];
var WNAME={N:'North',E:'East',S:'South',W:'West'};
var LEFTC={N:'NE',E:'SE',S:'SW',W:'NW'};
function wdef(r,k){
  var w=r.w,d=r.d;
  var b={N:{P:[w,d],dir:[-1,0],out:[0,1],L:w,trim:false},E:{P:[w,0],dir:[0,1],out:[1,0],L:d,trim:true},
         S:{P:[0,0],dir:[1,0],out:[0,-1],L:w,trim:false},W:{P:[0,d],dir:[0,-1],out:[-1,0],L:d,trim:true}}[k];
  return {P:[b.P[0]+r.x,b.P[1]+r.y],dir:b.dir,out:b.out,L:b.L,trim:b.trim};
}
function bounds(){
  var a=Infinity,b=Infinity,c=-Infinity,d=-Infinity,h=0;
  S.rooms.forEach(function(r){a=Math.min(a,r.x);b=Math.min(b,r.y);c=Math.max(c,r.x+r.w);d=Math.max(d,r.y+r.d);h=Math.max(h,r.h);});
  return {x0:a,y0:b,x1:c,y1:d,w:c-a,d:d-b,h:h};
}
function tagMap(){
  var c={window:0,door:0},m={};
  S.rooms.forEach(function(r){r.open.forEach(function(o){c[o.type]++;m[o.id]=(o.type==='door'?'D':'W')+c[o.type];});});
  return m;
}
function rname(r){return r.name||('Room '+r.id);}

/* ---------- validation ---------- */
function validate(){
  var ok={},msgs=[],tags=tagMap(),multi=S.rooms.length>1;
  S.rooms.forEach(function(r){
    var pre=multi?rname(r)+': ':'';
    WALLS.forEach(function(k){
      var wd=wdef(r,k),u0=wd.trim?r.t:0,u1=wd.L-u0,last=u0;
      r.open.filter(function(o){return o.wall===k;}).sort(function(a,b){return a.off-b.off;}).forEach(function(o){
        var tg=tags[o.id],bad=null;
        if(!(o.w>0&&o.h>0)) bad=tg+' needs a width and height.';
        else if(o.off<u0-1e-6) bad=tg+' starts before the wall begins'+(wd.trim?' (the corner framing takes the first '+fmt(r.t)+')':'')+'.';
        else if(o.off+o.w>u1+1e-6) bad=tg+' runs past the end of the '+WNAME[k].toLowerCase()+' wall.';
        else if(o.sill+o.h>r.h+1e-6) bad=tg+' is taller than the wall.';
        else if(o.off<last-1e-6) bad=tg+' overlaps another opening on the '+WNAME[k].toLowerCase()+' wall.';
        ok[o.id]=!bad; if(bad) msgs.push(pre+bad); else last=o.off+o.w;
      });
    });
  });
  return {ok:ok,msgs:msgs};
}

/* ---------- forms ---------- */
var EDIT=!!$('f-w');
var rowsEl=$('rows');
function roomFields(){
  var r=R();
  $('f-name').value=r.name;$('f-x').value=fmt(r.x);$('f-y').value=fmt(r.y);
  $('f-w').value=fmt(r.w);$('f-d').value=fmt(r.d);$('f-h').value=fmt(r.h);$('f-t').value=fmt(r.t);
  $('pos-wrap').hidden=(S.rooms.length<2);
  $('rm-room').hidden=(S.rooms.length<2);
  $('rm-room').textContent='Remove '+rname(r);
  $('open-title').textContent='Windows and doors'+(S.rooms.length>1?' in '+rname(r):'');
}
function tabs(){
  $('rtabs').innerHTML=S.rooms.map(function(r){
    return '<button type="button" class="rtab" data-room="'+r.id+'" aria-pressed="'+(r.id===S.sel)+'">'+esc(rname(r))+'</button>';
  }).join('');
}
function buildRows(){
  var tags=tagMap(),h='',r=R();
  r.open.forEach(function(o){
    var isDoor=o.type==='door',tg=tags[o.id];
    h+='<div class="orow" data-id="'+o.id+'"><div class="otag"><div>'+tg+'<span class="k">'+(isDoor?'Door':'Window')+'</span></div>'
      +'<button type="button" class="del" aria-label="Remove '+tg+'">Remove</button></div>'
      +'<label class="wallsel" for="o'+o.id+'-wall">Wall<select id="o'+o.id+'-wall" data-f="wall">'
      +WALLS.map(function(k){return '<option value="'+k+'"'+(o.wall===k?' selected':'')+'>'+WNAME[k]+' wall</option>';}).join('')
      +'</select></label>'
      +'<label for="o'+o.id+'-off" style="grid-column:span 2">From corner<input id="o'+o.id+'-off" data-f="off" value="'+q(fmt(o.off))+'" autocomplete="off"></label>'
      +'<label for="o'+o.id+'-w">Width<input id="o'+o.id+'-w" data-f="w" value="'+q(fmt(o.w))+'" autocomplete="off"></label>'
      +'<label for="o'+o.id+'-h">Height<input id="o'+o.id+'-h" data-f="h" value="'+q(fmt(o.h))+'" autocomplete="off"></label>'
      +'<label for="o'+o.id+'-sill" style="grid-column:span 2">Sill height<input id="o'+o.id+'-sill" data-f="sill" value="'+q(fmt(o.sill))+'" autocomplete="off"'+(isDoor?' disabled':'')+'></label>'
      +'</div>';
  });
  rowsEl.innerHTML=h||'<p class="hint">No windows or doors yet.</p>';
}
function finForm(){
  $('fin').innerHTML=FINK.map(function(k){
    var cur=S.fin[k];
    return '<div class="finrow"><label for="fin-'+k+'">'+FINL[k]+'<span class="finsel"><span class="sw" id="sw-'+k+'" style="background:'+hexOf(k)+'"></span>'
      +'<select id="fin-'+k+'" data-k="'+k+'">'+PAL[k].map(function(p){return '<option'+(p[0]===cur.name?' selected':'')+'>'+p[0]+'</option>';}).join('')+'</select></span></label>'
      +'<label for="fin-'+k+'-note">Product or paint code<input id="fin-'+k+'-note" data-n="'+k+'" value="'+q(cur.note||'')+'" autocomplete="off" placeholder="optional"></label></div>';
  }).join('');
}
function readInput(el,key,target){
  var v=parseLen(el.value);
  if(isNaN(v)||v<0){el.classList.add('bad');return false;}
  el.classList.remove('bad');target[key]=v;return true;
}
var RF={'f-x':'x','f-y':'y','f-w':'w','f-d':'d','f-h':'h','f-t':'t'};
function onInput(e){
  var t=e.target,r=R();
  if(t.id==='f-name'){r.name=t.value.slice(0,40);tabs();refresh();return;}
  if(RF[t.id]){var tmp={};if(readInput(t,RF[t.id],tmp)&&(tmp[RF[t.id]]>0||t.id==='f-x'||t.id==='f-y')){r[RF[t.id]]=tmp[RF[t.id]];refresh();}return;}
  if(t.dataset&&t.dataset.k){S.fin[t.dataset.k].name=t.value;var sw=$('sw-'+t.dataset.k);if(sw)sw.style.background=hexOf(t.dataset.k);refresh();return;}
  if(t.dataset&&t.dataset.n){S.fin[t.dataset.n].note=t.value.slice(0,60);refresh(true);return;}
  var row=t.closest&&t.closest('.orow');if(!row)return;
  var o=r.open.filter(function(x){return x.id==row.dataset.id;})[0];if(!o)return;
  var f=t.dataset.f;
  if(f==='wall'){o.wall=t.value;}else if(!readInput(t,f,o)) return;
  refresh();
}
function onChange(e){
  var t=e.target,r=R();
  if(RF[t.id]){t.value=fmt(r[RF[t.id]]);t.classList.remove('bad');}
  else if(t.dataset&&t.dataset.f&&t.dataset.f!=='wall'){
    var row=t.closest('.orow'),o=r.open.filter(function(x){return x.id==row.dataset.id;})[0];
    if(o){t.value=fmt(o[t.dataset.f]);t.classList.remove('bad');}
  }
}
function newOpen(type){
  var d=type==='door'?{w:36,h:80,sill:0}:{w:36,h:48,sill:30},r=R();
  r.open.push({id:S.nextOpen++,type:type,wall:'S',off:Math.max(r.t,12),w:d.w,h:Math.min(d.h,r.h),sill:d.sill});
  buildRows();refresh();
}
function selectRoom(id){S.sel=id;roomFields();tabs();buildRows();refresh();}
function addRoom(){
  var last=S.rooms[S.rooms.length-1],id=S.nextRoom++;
  var r=newRoom(id,'Room '+(S.rooms.length+1),last.x+last.w,last.y,120,last.d,last.h,last.t);
  S.rooms.push(r);selectRoom(id);
}
var rmArm=null;
function removeRoom(){
  var b=$('rm-room');
  if(!rmArm){rmArm=setTimeout(function(){rmArm=null;b.textContent='Remove '+rname(R());},3500);b.textContent='Click again to remove';return;}
  clearTimeout(rmArm);rmArm=null;
  S.rooms=S.rooms.filter(function(r){return r.id!==S.sel;});S.sel=S.rooms[0].id;selectRoom(S.sel);
}
if(EDIT){
  document.addEventListener('input',onInput);
  document.addEventListener('change',onChange);
  rowsEl.addEventListener('click',function(e){
    var b=e.target.closest('.del');if(!b)return;
    var id=b.closest('.orow').dataset.id,r=R();
    r.open=r.open.filter(function(o){return o.id!=id;});buildRows();refresh();
  });
  $('add-win').addEventListener('click',function(){newOpen('window');});
  $('add-door').addEventListener('click',function(){newOpen('door');});
  $('add-room').addEventListener('click',addRoom);
  $('rm-room').addEventListener('click',removeRoom);
  $('rtabs').addEventListener('click',function(e){var b=e.target.closest('.rtab');if(b)selectRoom(+b.dataset.room);});
  $('reset').addEventListener('click',function(){S=SAMPLE();roomFields();tabs();buildRows();finForm();refresh();});
}

/* ---------- plan view (SVG) ---------- */
function plan(v){
  var B=bounds(),M=105,vw=B.w+2*M,vh=B.d+2*M,fs=Math.max(6.5,vw/50),tk=fs*.55,sel=R();
  var svg=$('plan');svg.setAttribute('viewBox','0 0 '+vw+' '+vh);
  var X=function(x){return x-B.x0+M;},Y=function(y){return B.y1-y+M;};
  var pt=function(wd,u,s){return [X(wd.P[0]+wd.dir[0]*u+wd.out[0]*s),Y(wd.P[1]+wd.dir[1]*u+wd.out[1]*s)];};
  var P=function(a){return a[0].toFixed(1)+','+a[1].toFixed(1);};
  var rect=function(r,x0,y0,x1,y1,c){return '<rect class="'+c+'" x="'+X(r.x+x0)+'" y="'+Y(r.y+y1)+'" width="'+(x1-x0)+'" height="'+(y1-y0)+'"/>';};
  var tags=tagMap(),h='',txt=function(c,size,x,y,s,extra){return '<text class="'+c+'" font-size="'+size+'" x="'+x+'" y="'+y+'" text-anchor="middle" dominant-baseline="central"'+(extra||'')+'>'+s+'</text>';};
  S.rooms.forEach(function(r){
    var t=r.t,w=r.w,d=r.d,tagHtml='';
    h+='<g data-room="'+r.id+'" class="rgrp">';
    h+='<rect class="hit" x="'+X(r.x)+'" y="'+Y(r.y+d)+'" width="'+w+'" height="'+d+'"/>';
    if(S.rooms.length>1&&r.id===sel.id)h+='<rect class="selbox" x="'+(X(r.x)-3)+'" y="'+(Y(r.y+d)-3)+'" width="'+(w+6)+'" height="'+(d+6)+'"/>';
    h+=rect(r,0,d-t,w,d,'wall')+rect(r,0,0,w,t,'wall')+rect(r,w-t,t,w,d-t,'wall')+rect(r,0,t,t,d-t,'wall');
    r.open.forEach(function(o){
      if(!v.ok[o.id])return;
      var wd=wdef(r,o.wall),a=o.off,b=o.off+o.w;
      var A0=pt(wd,a,0),B0=pt(wd,b,0),A1=pt(wd,a,-t),B1=pt(wd,b,-t);
      h+='<polygon class="gap" points="'+P(A0)+' '+P(B0)+' '+P(B1)+' '+P(A1)+'"/>';
      h+='<line class="jamb" x1="'+A0[0]+'" y1="'+A0[1]+'" x2="'+A1[0]+'" y2="'+A1[1]+'"/><line class="jamb" x1="'+B0[0]+'" y1="'+B0[1]+'" x2="'+B1[0]+'" y2="'+B1[1]+'"/>';
      if(o.type==='window'){
        [0,-t/2,-t].forEach(function(s,i){var p=pt(wd,a,s),q2=pt(wd,b,s);
          h+='<line class="'+(i===1?'glassln':'thin')+'" x1="'+p[0]+'" y1="'+p[1]+'" x2="'+q2[0]+'" y2="'+q2[1]+'"/>';});
      }else{
        var H=A1,C=pt(wd,a,-t-o.w),Bq=B1,cr=(Bq[0]-H[0])*(C[1]-H[1])-(Bq[1]-H[1])*(C[0]-H[0]);
        h+='<line class="leaf" x1="'+H[0]+'" y1="'+H[1]+'" x2="'+C[0]+'" y2="'+C[1]+'"/>';
        h+='<path class="swing" d="M'+P(Bq)+' A'+o.w+','+o.w+' 0 0,'+(cr>0?1:0)+' '+P(C)+'"/>';
      }
      var tp=pt(wd,(a+b)/2,-t-fs*1.6);
      tagHtml+='<circle class="tagc" cx="'+tp[0]+'" cy="'+tp[1]+'" r="'+fs*1.15+'"/>'+txt('tagt',fs*.85,tp[0],tp[1],tags[o.id],' font-weight="500"');
    });
    h+=tagHtml;
    var iw=w-2*t,id=d-2*t,cx=X(r.x+w/2),cy=Y(r.y+d/2),f2=Math.min(fs,Math.max(5.5,w/15)),ly=cy-f2*1.5;
    h+=txt('mutedt',f2,cx,ly,esc(rname(r)),' font-weight="500"');
    if(S.rooms.length===1)h+=txt('mutedt',f2*.95,cx,ly+f2*1.5,'Inside '+fmt(iw)+' x '+fmt(id));
    h+=txt('mutedt',f2*.9,cx,ly+f2*(S.rooms.length===1?3:1.5),(iw*id/144).toFixed(1)+' sq ft');
    h+='</g>';
  });
  WALLS.forEach(function(k){
    var wd=wdef(sel,k),list=sel.open.filter(function(o){return o.wall===k&&v.ok[o.id];}).sort(function(a,b){return a.off-b.off;});
    if(!list.length)return;
    var mid=pt(wd,wd.L/2,28),mx=mid[0]-M+B.x0,my=B.y1-(mid[1]-M);
    if(S.rooms.some(function(o2){return o2!==sel&&mx>o2.x&&mx<o2.x+o2.w&&my>o2.y&&my<o2.y+o2.d;}))return;
    var br=[0];list.forEach(function(o){br.push(o.off,o.off+o.w);});br.push(wd.L);
    var dist=28,p0=pt(wd,0,dist),p1=pt(wd,wd.L,dist);
    h+='<line class="dimln" x1="'+p0[0]+'" y1="'+p0[1]+'" x2="'+p1[0]+'" y2="'+p1[1]+'"/>';
    br.forEach(function(u){var a=pt(wd,u,dist-tk),b=pt(wd,u,dist+tk);h+='<line class="dimln" x1="'+a[0]+'" y1="'+a[1]+'" x2="'+b[0]+'" y2="'+b[1]+'"/>';});
    for(var i=0;i<br.length-1;i++){
      var len=br[i+1]-br[i];if(len<1)continue;
      var c=pt(wd,(br[i]+br[i+1])/2,dist+fs*.9),vert=(k==='E'||k==='W');
      h+='<text class="dimtxt" font-size="'+fs*.85+'" x="'+c[0]+'" y="'+c[1]+'" text-anchor="middle" dominant-baseline="central"'+(vert?' transform="rotate(-90 '+c[0]+' '+c[1]+')"':'')+(i%2===1?' font-weight="500"':'')+'>'+fmt(len)+'</text>';
    }
  });
  var a=[X(B.x0),Y(B.y0)+62],b=[X(B.x1),Y(B.y0)+62];
  h+='<line class="dimln" x1="'+a[0]+'" y1="'+a[1]+'" x2="'+b[0]+'" y2="'+b[1]+'"/>';
  [a,b].forEach(function(p){h+='<line class="dimln" x1="'+p[0]+'" y1="'+(p[1]-tk)+'" x2="'+p[0]+'" y2="'+(p[1]+tk)+'"/>';});
  h+=txt('dimtxt',fs,X(B.x0+B.w/2),a[1]+fs*1.1,fmt(B.w),' font-weight="500"');
  var c2=[X(B.x0)-62,Y(B.y1)],e2=[X(B.x0)-62,Y(B.y0)];
  h+='<line class="dimln" x1="'+c2[0]+'" y1="'+c2[1]+'" x2="'+e2[0]+'" y2="'+e2[1]+'"/>';
  [c2,e2].forEach(function(p){h+='<line class="dimln" x1="'+(p[0]-tk)+'" y1="'+p[1]+'" x2="'+(p[0]+tk)+'" y2="'+p[1]+'"/>';});
  var tx=c2[0]-fs*1.1,ty=Y(B.y0+B.d/2);
  h+=txt('dimtxt',fs,tx,ty,fmt(B.d),' font-weight="500" transform="rotate(-90 '+tx+' '+ty+')"');
  var lf=fs*1.15;
  h+=txt('mutedt',lf,X(B.x0+B.w/2),Y(B.y1)-78,'N',' font-weight="500"')+txt('mutedt',lf,X(B.x0+B.w/2),Y(B.y0)+92,'S',' font-weight="500"')
    +txt('mutedt',lf,X(B.x1)+78,Y(B.y0+B.d/2),'E',' font-weight="500"')+txt('mutedt',lf,X(B.x0)-92,Y(B.y0+B.d/2),'W',' font-weight="500"');
  svg.innerHTML=h;
}
if(EDIT)$('plan').addEventListener('click',function(e){
  var g=e.target.closest('[data-room]');if(g&&+g.dataset.room!==S.sel)selectRoom(+g.dataset.room);
});

/* ---------- 3D view ---------- */
var stage=$('stage'),canvas=$('gl');
var renderer=null,scene,camera,root,wallGroups={},dirty=true;
var cam={theta:-Math.PI/4,phi:.5,r:300};
function initGL(){
  if(typeof THREE==='undefined'){noGL();return;}
  try{renderer=new THREE.WebGLRenderer({canvas:canvas,antialias:true,alpha:true});}catch(e){noGL();return;}
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
  scene=new THREE.Scene();root=new THREE.Group();scene.add(root);
  camera=new THREE.PerspectiveCamera(35,1,1,8000);
  scene.add(new THREE.AmbientLight(0xffffff,.78));
  var sun=new THREE.DirectionalLight(0xffffff,.5);sun.position.set(-200,400,300);scene.add(sun);
  new ResizeObserver(resize).observe(stage);resize();
  hookControls();(function tick(){if(dirty){dirty=false;if(renderer)renderer.render(scene,camera);}requestAnimationFrame(tick);})();
  window.addEventListener('beforeprint',function(){
    if(!renderer)return;renderer.render(scene,camera);
    var im=$('glprint');if(im){im.src=canvas.toDataURL('image/png');im.hidden=false;canvas.hidden=true;}});
  window.addEventListener('afterprint',function(){var im=$('glprint');if(im){im.hidden=true;canvas.hidden=false;dirty=true;}});
}
function noGL(){renderer=null;stage.innerHTML='<div class="nogl">The 3D view needs WebGL, which this browser is not offering. The plan view and the text below still work.</div>';}
function resize(){
  var w=stage.clientWidth;if(!w||!renderer)return;
  var h=Math.max(280,Math.min(560,Math.round(w*.72)));
  renderer.setSize(w,h,false);canvas.style.height=h+'px';
  camera.aspect=w/h;camera.updateProjectionMatrix();updateCam();
}
function target(){var B=bounds();return new THREE.Vector3(B.x0+B.w/2,B.h/3,-(B.y0+B.d/2));}
function updateCam(){
  if(!renderer)return;var T=target(),cp=Math.cos(cam.phi);
  camera.position.set(T.x+cam.r*Math.sin(cam.theta)*cp,T.y+cam.r*Math.sin(cam.phi),T.z+cam.r*Math.cos(cam.theta)*cp);
  camera.lookAt(T);
  var cutOn=$('cut').checked&&cam.phi<1.2;
  Object.keys(wallGroups).forEach(function(key){
    var g=wallGroups[key],o=g.userData.out;
    g.visible=!(cutOn&&(Math.sin(cam.theta)*o[0]+Math.cos(cam.theta)*(-o[1]))>.45);
  });
  dirty=true;
}
function label(txt,col){
  var c=document.createElement('canvas');c.width=c.height=128;var x=c.getContext('2d');
  x.fillStyle=col;x.font='600 84px Menlo,Consolas,monospace';x.textAlign='center';x.textBaseline='middle';x.fillText(txt,64,68);
  var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c),transparent:true,depthTest:false}));
  sp.scale.set(26,26,1);return sp;
}
function clearRoot(){
  while(root.children.length){var c=root.children.pop();c.traverse(function(n){
    if(n.geometry)n.geometry.dispose();
    if(n.material){var ms=Array.isArray(n.material)?n.material:[n.material];ms.forEach(function(m){if(m.map)m.map.dispose();m.dispose();});}});}
  wallGroups={};
}
function build3d(v){
  if(!renderer)return;clearRoot();
  var mExt=new THREE.MeshLambertMaterial({color:hexOf('siding')}),mInt=new THREE.MeshLambertMaterial({color:hexOf('paint')}),
      mGlass=new THREE.MeshBasicMaterial({color:'#7FB4CF',transparent:true,opacity:.42,depthWrite:false}),
      mTrim=new THREE.MeshLambertMaterial({color:hexOf('trim')}),
      mLine=new THREE.LineBasicMaterial({color:'#222222',transparent:true,opacity:.4}),
      mFloor=new THREE.MeshBasicMaterial({color:hexOf('floor')});
  function piece(g,wd,u0,u1,v0,v1,mat,thick,sOff,edges){
    var geo=new THREE.BoxGeometry(u1-u0,v1-v0,thick);
    var ex=new THREE.Vector3(wd.dir[0],0,-wd.dir[1]),ey=new THREE.Vector3(0,1,0),bz=new THREE.Vector3().crossVectors(ex,ey);
    var inward=new THREE.Vector3(-wd.out[0],0,wd.out[1]);
    var m=new THREE.Mesh(geo,mat==='wall'?(bz.dot(inward)>0?[mExt,mExt,mExt,mExt,mInt,mExt]:[mExt,mExt,mExt,mExt,mExt,mInt]):mat);
    m.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(ex,ey,bz));
    var P3=new THREE.Vector3(wd.P[0],0,-wd.P[1]),u=(u0+u1)/2;
    m.position.copy(P3).addScaledVector(ex,u).add(new THREE.Vector3(0,(v0+v1)/2,0)).addScaledVector(inward,sOff);
    g.add(m);
    if(edges){var l=new THREE.LineSegments(new THREE.EdgesGeometry(geo),mLine);l.position.copy(m.position);l.quaternion.copy(m.quaternion);g.add(l);}
  }
  S.rooms.forEach(function(r){
    var w=r.w,d=r.d,h=r.h,t=r.t;
    var floor=new THREE.Mesh(new THREE.BoxGeometry(w,4,d),mFloor);floor.position.set(r.x+w/2,-2.2,-(r.y+d/2));root.add(floor);
    WALLS.forEach(function(k){
      var wd=wdef(r,k),g=new THREE.Group(),u0=wd.trim?t:0,u1=wd.L-u0,cur=u0;g.userData.out=wd.out;
      r.open.filter(function(o){return o.wall===k&&v.ok[o.id];}).sort(function(a,b){return a.off-b.off;}).forEach(function(o){
        if(o.off>cur)piece(g,wd,cur,o.off,0,h,'wall',t,t/2,true);
        if(o.sill>0)piece(g,wd,o.off,o.off+o.w,0,o.sill,'wall',t,t/2,true);
        if(o.sill+o.h<h)piece(g,wd,o.off,o.off+o.w,o.sill+o.h,h,'wall',t,t/2,true);
        var a=o.off,b=o.off+o.w,s0=o.sill,s1=o.sill+o.h,fw=2,ft=t+1.2;
        piece(g,wd,a,a+fw,s0,s1,mTrim,ft,t/2,false);piece(g,wd,b-fw,b,s0,s1,mTrim,ft,t/2,false);
        piece(g,wd,a+fw,b-fw,s1-fw,s1,mTrim,ft,t/2,false);
        if(o.type==='window'){
          piece(g,wd,a+fw,b-fw,s0,s0+fw,mTrim,ft,t/2,false);
          piece(g,wd,a+fw,b-fw,s0+fw,s1-fw,mGlass,.6,t/2,false);
        }else piece(g,wd,a+fw+.3,b-fw-.3,0,o.h-fw-.3,mTrim,1.75,t*.7,true);
        cur=o.off+o.w;
      });
      if(u1>cur)piece(g,wd,cur,u1,0,h,'wall',t,t/2,true);
      root.add(g);wallGroups[r.id+k]=g;
    });
  });
  var B=bounds(),lc='#6B6B6B',gap=34;
  [['N',B.x0+B.w/2,-B.y1-gap],['S',B.x0+B.w/2,-B.y0+gap],['E',B.x1+gap,-(B.y0+B.d/2)],['W',B.x0-gap,-(B.y0+B.d/2)]].forEach(function(a){
    var s=label(a[0],lc);s.position.set(a[1],6,a[2]);root.add(s);});
  updateCam();
}
function setView(name){
  var B=bounds(),big=Math.max(B.w,B.d,B.h);
  var th={SW:-Math.PI/4,SE:Math.PI/4,NE:3*Math.PI/4,NW:-3*Math.PI/4}[name];
  if(name==='TOP'){cam.phi=1.52;cam.r=big*3;}else{cam.theta=th;cam.phi=.5;cam.r=big*2.5;}
  updateCam();
}
function hookControls(){
  var ptrs=new Map(),lastD=0;
  canvas.addEventListener('pointerdown',function(e){canvas.setPointerCapture(e.pointerId);ptrs.set(e.pointerId,[e.clientX,e.clientY]);lastD=0;});
  canvas.addEventListener('pointerup',function(e){ptrs.delete(e.pointerId);});
  canvas.addEventListener('pointercancel',function(e){ptrs.delete(e.pointerId);});
  canvas.addEventListener('pointermove',function(e){
    if(!ptrs.has(e.pointerId))return;var old=ptrs.get(e.pointerId);
    if(ptrs.size===1){cam.theta-=(e.clientX-old[0])*.008;cam.phi=Math.max(.05,Math.min(1.52,cam.phi+(e.clientY-old[1])*.006));}
    ptrs.set(e.pointerId,[e.clientX,e.clientY]);
    if(ptrs.size===2){var a=Array.from(ptrs.values()),dd=Math.hypot(a[0][0]-a[1][0],a[0][1]-a[1][1]);
      if(lastD)cam.r=Math.max(60,Math.min(4000,cam.r*lastD/dd));lastD=dd;}
    updateCam();
  });
  canvas.addEventListener('wheel',function(e){e.preventDefault();cam.r=Math.max(60,Math.min(4000,cam.r*Math.exp(e.deltaY*.001)));updateCam();},{passive:false});
  document.querySelectorAll('[data-view]').forEach(function(b){b.addEventListener('click',function(){setView(b.dataset.view);});});
  $('cut').addEventListener('change',updateCam);
}

/* ---------- finish schedule and room list ---------- */
function schedule(){
  var el=$('sched');if(!el)return;
  var h='<table class="stbl"><thead><tr><th>Finish</th><th>Choice</th><th>Notes</th></tr></thead><tbody>';
  FINK.forEach(function(k){h+='<tr><td>'+FINL[k]+'</td><td><span class="sw" style="background:'+hexOf(k)+'"></span> '+esc(S.fin[k].name)+'</td><td>'+esc(S.fin[k].note||'')+'</td></tr>';});
  h+='</tbody></table>';
  var tot=0;
  h+='<table class="stbl"><thead><tr><th>Room</th><th>Outside size</th><th class="num">Inside sq ft</th></tr></thead><tbody>';
  S.rooms.forEach(function(r){var a=(r.w-2*r.t)*(r.d-2*r.t)/144;tot+=a;h+='<tr><td>'+esc(rname(r))+'</td><td>'+fmt(r.w)+' x '+fmt(r.d)+', walls '+fmt(r.h)+'</td><td class="num">'+a.toFixed(1)+'</td></tr>';});
  if(S.rooms.length>1)h+='<tr><td colspan="2"><b>Total</b></td><td class="num"><b>'+tot.toFixed(1)+'</b></td></tr>';
  h+='</tbody></table>';
  el.innerHTML=h;
}

/* ---------- before and after photos ---------- */
var stamp=Date.now(),localUrls={};
function photoSrc(k){
  if(CFG.photoBase)return CFG.photos&&CFG.photos[k]?CFG.photoBase+'/'+k+'?t='+stamp:'';
  return localUrls[k]||'';
}
function renderPhotos(){
  var card=$('ba-card');if(!card)return;
  var b=photoSrc('before'),a=photoSrc('after');
  var view=$('ba-view'),bi=$('ba-before'),ai=$('ba-after'),rg=$('ba-range'),cap=$('ba-cap');
  card.hidden=!b&&!a&&ROOT.classList.contains('present');
  view.hidden=!b&&!a;
  if(bi.getAttribute('src')!==b)bi.src=b;if(ai.getAttribute('src')!==a)ai.src=a;
  bi.hidden=!b;ai.hidden=!a;
  rg.hidden=!(a&&b);$('ba-labels').hidden=!(a&&b);
  cap.textContent=(a&&b)?'':(b?'Photo of the space today.':a?'Picture of the idea.':'');
  bi.style.clipPath=(a&&b)?'inset(0 '+(100-(+rg.value))+'% 0 0)':'none';
  var rb=$('ba-rm-before'),ra=$('ba-rm-after');if(rb)rb.hidden=!b;if(ra)ra.hidden=!a;
}
function shrink(file){
  return new Promise(function(res,rej){
    var im=new Image(),u=URL.createObjectURL(file);
    im.onload=function(){
      var s=Math.min(1,1600/Math.max(im.width,im.height)),c=document.createElement('canvas');
      c.width=Math.round(im.width*s);c.height=Math.round(im.height*s);c.getContext('2d').drawImage(im,0,0,c.width,c.height);
      URL.revokeObjectURL(u);c.toBlob(function(b){b?res(b):rej();},'image/jpeg',.85);
    };
    im.onerror=function(){URL.revokeObjectURL(u);rej();};im.src=u;
  });
}
function setPhoto(kind,file){
  var msg=$('ba-msg');msg.textContent='Working...';
  shrink(file).then(function(blob){
    if(!CFG.photoBase){localUrls[kind]=URL.createObjectURL(blob);msg.textContent='Loaded. This demo does not keep photos.';renderPhotos();return;}
    var fd=new FormData();fd.set('csrf',CFG.csrf||'');fd.set('file',blob,'photo.jpg');
    return fetch(CFG.photoBase+'/'+kind,{method:'POST',body:fd}).then(function(r){
      if(!r.ok)throw new Error('bad');CFG.photos=CFG.photos||{};CFG.photos[kind]=true;stamp=Date.now();msg.textContent='Saved with this job.';renderPhotos();
    });
  }).catch(function(){msg.textContent='That picture could not be saved. Try a JPEG or PNG.';});
}
function removePhoto(kind){
  var msg=$('ba-msg');
  if(!CFG.photoBase){delete localUrls[kind];renderPhotos();return;}
  var fd=new FormData();fd.set('csrf',CFG.csrf||'');
  fetch(CFG.photoBase+'/'+kind+'/delete',{method:'POST',body:fd}).then(function(r){
    if(!r.ok)throw new Error('bad');CFG.photos[kind]=false;msg.textContent='Removed.';renderPhotos();
  }).catch(function(){msg.textContent='Could not remove it. Reload and try again.';});
}
if($('ba-card')){
  $('ba-range').addEventListener('input',renderPhotos);
  ['before','after'].forEach(function(k){
    var f=$('ph-'+k);if(f)f.addEventListener('change',function(){if(f.files[0])setPhoto(k,f.files[0]);f.value='';});
    var b=$('ba-rm-'+k);if(b)b.addEventListener('click',function(){removePhoto(k);});
  });
}

/* ---------- text for ChatGPT ---------- */
function specText(v){
  var tags=tagMap(),L=[],multi=S.rooms.length>1;
  L.push(multi?'This is a building with '+S.rooms.length+' rooms. North is the top of the plan. Sizes are outside framing dimensions.':'This is a single room. North is the top of the plan. Sizes are outside framing dimensions.');
  S.rooms.forEach(function(r){
    L.push('');
    L.push((multi?rname(r)+': ':'Room: ')+fmt(r.w)+' east to west by '+fmt(r.d)+' north to south, walls '+fmt(r.h)+' high and '+fmt(r.t)+' thick.'
      +(multi?' Its southwest corner is '+fmt(r.x)+' east and '+fmt(r.y)+' north of the southwest corner of the first room.':''));
    L.push('Openings, measured along each wall from its left corner as you stand outside facing it:');
    WALLS.forEach(function(k){
      var list=r.open.filter(function(o){return o.wall===k&&v.ok[o.id];}).sort(function(a,b){return a.off-b.off;});
      L.push('- '+WNAME[k]+' wall (left corner is '+LEFTC[k]+'): '+(list.length?list.map(function(o){
        return tags[o.id]+' '+(o.type==='door'?'door':'window')+' '+fmt(o.w)+' wide by '+fmt(o.h)+' tall, starting '+fmt(o.off)+' from the corner'+(o.type==='window'?', sill '+fmt(o.sill)+' above the floor':'');
      }).join('; '):'solid wall, no openings')+'.');
    });
  });
  L.push('');
  L.push('Finishes: '+FINK.map(function(k){return FINL[k].toLowerCase()+' '+S.fin[k].name.toLowerCase()+(S.fin[k].note?' ('+S.fin[k].note+')':'');}).join('; ')+'.');
  L.push('');
  L.push('Keep every wall, window and door in exactly these positions and sizes. Do not add, remove or move any opening or room. Only change the finishes, lighting and style that I ask for.');
  return L.join('\n');
}
if($('copy'))$('copy').addEventListener('click',function(){
  var ta=$('spec'),msg=$('copied');
  function done(t){msg.textContent=t;setTimeout(function(){msg.textContent='';},2500);}
  function fallback(){ta.focus();ta.select();done('Text selected. Press copy on your keyboard.');}
  try{navigator.clipboard.writeText(ta.value).then(function(){done('Copied.');},fallback);}catch(e){fallback();}
});
if($('print'))$('print').addEventListener('click',function(){try{window.print();}catch(e){}});

/* ---------- main refresh ---------- */
function refresh(skipBuild){
  var v=validate();
  if($('warns'))$('warns').innerHTML=v.msgs.map(function(m){return '<li>'+esc(m)+'</li>';}).join('');
  if($('reset'))$('reset').hidden=!(S.rooms.length===1&&S.rooms[0].open.length===0);
  if(skipBuild!==true){plan(v);build3d(v);}
  if($('spec'))$('spec').value=specText(v);
  schedule();save();
  var tags=tagMap();document.querySelectorAll('.orow').forEach(function(r){
    var el=r.querySelector('.otag div');if(el&&tags[r.dataset.id])el.firstChild.nodeValue=tags[r.dataset.id];});
}
if(EDIT){roomFields();tabs();buildRows();finForm();}
initGL();refresh();setView('SW');renderPhotos();
})();
