/* THE ERİNÇ — plain browser client; all gameplay decisions belong to the server. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), canvas=$('arena'), ctx=canvas.getContext('2d');
  const map=$('minimap'), mc=map.getContext('2d');
  const pictures=Array.from({length:6},(_,i)=>{const img=new Image(); img.src=`assets/skins/skin-${i+1}.jpeg`; return img;});
  let skin=0, ws=null, myId=null, state=null, playing=false, retryTimer=null, retries=0, lastNotice=0;
  let width=innerWidth,height=innerHeight,dpr=Math.min(devicePixelRatio||1,2), zoom=1, camera={x:1600,y:1600};
  let serverOffset=0, direction={x:0,y:0}, touchDirection=null, keys=new Set(), keyboard=false, lastFrame=performance.now(), renderPlayers=new Map();
  let ping=0, joinedName='', hadConnection=false, deathAt=0;
  pictures.forEach((img,i)=>{
    const button=document.createElement('button');button.type='button';button.className='skin'+(i===0?' selected':'');
    button.setAttribute('aria-label',`Karakter ${i+1}`);button.setAttribute('aria-pressed',i===0?'true':'false');
    button.append(img.cloneNode());button.addEventListener('click',()=>{skin=i;[...$('skins').children].forEach((b,j)=>{b.classList.toggle('selected',i===j);b.setAttribute('aria-pressed',String(i===j));});});$('skins').append(button);
    const hero=img.cloneNode();hero.className='hero-skin';hero.alt=`Karakter ${i+1}`;$('character-stage').append(hero);
  });
  function status(text,error=false){$('message').textContent=text;$('message').classList.toggle('error',error);}
  function toast(text){$('toast').textContent=text;$('toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('show'),6000);}
  function endpoint(){
    const configured=window.ERINC_CONFIG?.serverUrl?.trim();
    if(configured){const u=new URL(configured);if(!['ws:','wss:'].includes(u.protocol)) throw Error('Sunucu adresi ws:// veya wss:// ile başlamalı.');if(location.protocol==='https:' && u.protocol!=='wss:')throw Error('HTTPS sayfası için wss:// sunucu adresi gerekli.');return u.href;}
    if(location.protocol==='file:') throw Error('Oyunu dosyaya çift tıklayarak açamazsın. Sunucuyu başlatıp http://localhost:3000 adresine git.');
    return `${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`;
  }
  function send(data){if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify(data));}
  function connect(){
    let url;try{url=endpoint();}catch(e){status(e.message,true);$('play').disabled=false;return;}
    const connection=new WebSocket(url);ws=connection;
    const timeout=setTimeout(()=>{if(connection.readyState!==WebSocket.OPEN)connection.close();},20000);
    connection.onopen=()=>{clearTimeout(timeout);send({type:'join',name:joinedName,skin});};
    connection.onmessage=event=>{
      if(ws!==connection)return;
      let msg;try{msg=JSON.parse(event.data);}catch{return;}
      if(msg.type==='welcome'){
        myId=msg.id;playing=true;hadConnection=true;retries=0;lastNotice=0;renderPlayers.clear();state=null;deathAt=0;
        $('lobby').hidden=true;$('hud').hidden=false;$('death').hidden=true;$('play').disabled=false;
        status('10 kişilik ortak harita. Hesap açmak yok.');direction={x:0,y:0};
      }else if(msg.type==='state'){
        const first=!state;
        if(!msg.food){msg.food=state?.food||[];for(const f of msg.foodChanges||[])msg.food[f.id]=f;}
        state=msg;serverOffset=msg.now-Date.now();
        const me=state.players.find(p=>p.id===myId);
        if(first&&me){camera.x=me.x;camera.y=me.y;zoom=targetZoom(me.mass);}
        updateHud(me);
      }else if(msg.type==='error'){
        status(msg.message,true);$('play').disabled=false;
        if(playing)toast(msg.message);hadConnection=false;connection.onclose=null;connection.close();
        if(playing)exit();
      }else if(msg.type==='pong'&&typeof msg.time==='number'){ping=Math.max(0,Date.now()-msg.time);$('ping').textContent=`${ping} ms`;}
    };
    connection.onerror=()=>{status('Sunucuya ulaşılamıyor. Adresi ve sunucunun açık olduğunu kontrol et.',true);};
    connection.onclose=()=>{
      clearTimeout(timeout);if(ws!==connection)return;$('play').disabled=false;
      if(hadConnection&&retries<5){retries++;toast(`Bağlantı koptu. Yeniden bağlanılıyor (${retries}/5)…`);retryTimer=setTimeout(connect,Math.min(1000*2**retries,10000));}
      else {exit();status('Bağlantı kurulamadı. Render sunucusu uyanıyorsa biraz bekleyip tekrar katıl.',true);}
    };
  }
  $('join-form').addEventListener('submit',e=>{e.preventDefault();joinedName=$('name').value.trim();if(!joinedName)return;retries=0;hadConnection=false;$('play').disabled=true;status('Pastaneye bağlanılıyor… Sunucunun uyanması biraz sürebilir.');connect();});
  function exit(){clearTimeout(retryTimer);if(ws){ws.onclose=null;ws.close();ws=null;}playing=false;hadConnection=false;myId=null;state=null;keys.clear();direction={x:0,y:0};touchDirection=null;renderPlayers.clear();$('stick').style.transform='';$('lobby').hidden=false;$('hud').hidden=true;$('death').hidden=true;$('play').disabled=false;}
  $('leave').onclick=exit;$('menu').onclick=exit;
  $('respawn').onclick=()=>{send({type:'respawn'});};
  function updateHud(me){
    $('online').textContent=`${state.count}/${state.capacity}`;
    $('leaders').replaceChildren(...state.leaderboard.map((p,i)=>{const li=document.createElement('li');if(p.id===myId)li.className='me';const rank=document.createElement('i'),name=document.createElement('span'),mass=document.createElement('b');rank.textContent=String(i+1).padStart(2,'0');name.textContent=p.name;mass.textContent=p.mass;li.append(rank,name,mass);return li;}));
    if(me){$('mass').textContent=me.mass;$('wins').textContent=me.wins;
      if(!me.alive&&$('death').hidden){deathAt=Date.now();$('death-message').textContent=`${me.killer || 'Bir rakip'} seni yuttu. Bir masa daha?`;$('death').hidden=false;}
      if(me.alive)$('death').hidden=true;
    }
    for(const notice of state.notices)if(notice.id>lastNotice){lastNotice=notice.id;toast(notice.text);}
  }
  function targetZoom(mass){return Math.min(1.4,Math.max(.36,Math.min(width,height)/770)*Math.pow(70/mass,.15));}
  function resize(){width=innerWidth;height=innerHeight;dpr=Math.min(devicePixelRatio||1,2);canvas.width=width*dpr;canvas.height=height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);}
  addEventListener('resize',resize);resize();
  canvas.addEventListener('pointermove',e=>{if(e.pointerType==='mouse'){keyboard=false;direction={x:(e.clientX-width/2)/100,y:(e.clientY-height/2)/100};}});
  canvas.addEventListener('pointerleave',()=>{direction={x:0,y:0};});
  const keySet=new Set(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright']);
  addEventListener('keydown',e=>{if(playing&&keySet.has(e.key.toLowerCase())){e.preventDefault();keyboard=true;keys.add(e.key.toLowerCase());}});
  addEventListener('keyup',e=>{keys.delete(e.key.toLowerCase());});
  const resetInput=()=>{keys.clear();direction={x:0,y:0};touchDirection=null;$('stick').style.transform='';};
  addEventListener('blur',resetInput);document.addEventListener('visibilitychange',()=>{if(document.hidden){resetInput();send({type:'input',x:0,y:0});}});
  let activePointer=null;const joystick=$('joystick');
  function moveStick(e){const rect=joystick.getBoundingClientRect();const x=e.clientX-rect.left-rect.width/2,y=e.clientY-rect.top-rect.height/2;const factor=Math.max(1,Math.hypot(x,y)/40);touchDirection={x:x/40/factor,y:y/40/factor};$('stick').style.transform=`translate(${touchDirection.x*36}px,${touchDirection.y*36}px)`;}
  joystick.addEventListener('pointerdown',e=>{if(activePointer!==null)return;activePointer=e.pointerId;joystick.setPointerCapture(e.pointerId);moveStick(e);});
  joystick.addEventListener('pointermove',e=>{if(activePointer===e.pointerId)moveStick(e);});
  function release(e){if(activePointer===e.pointerId){activePointer=null;touchDirection=null;direction={x:0,y:0};$('stick').style.transform='';}}
  joystick.addEventListener('pointerup',release);joystick.addEventListener('pointercancel',release);joystick.addEventListener('lostpointercapture',release);
  setInterval(()=>{if(!playing)return;let input=touchDirection||direction;if(keyboard&&!touchDirection)input={x:Number(keys.has('d')||keys.has('arrowright'))-Number(keys.has('a')||keys.has('arrowleft')),y:Number(keys.has('s')||keys.has('arrowdown'))-Number(keys.has('w')||keys.has('arrowup'))};send({type:'input',...input});},50);
  setInterval(()=>{if(playing)send({type:'ping',time:Date.now()});},2500);
  const foodColors=['#db7751','#8caa58','#c9a654','#bc6d78','#70989b'];
  function circle(x,y,r,fill){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();}
  function drawPlayer(p,now){
    let draw=renderPlayers.get(p.id);if(!draw){draw={x:p.x,y:p.y,r:Math.sqrt(p.mass)*4};renderPlayers.set(p.id,draw);}
    const a=1-Math.exp(-frameDt*16);draw.x+=(p.x-draw.x)*a;draw.y+=(p.y-draw.y)*a;draw.r+=(Math.sqrt(p.mass)*4-draw.r)*a;
    const {x,y,r}=draw;ctx.save();ctx.translate(x,y);
    ctx.shadowColor='#25312635';ctx.shadowBlur=18;ctx.shadowOffsetY=5;circle(0,0,r+3,p.id===myId?'#ed4c35':'#fffaf0');ctx.shadowBlur=0;ctx.shadowOffsetY=0;
    ctx.save();ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.clip();
    if(p.rainbow){['#e40303','#ff8c00','#ffed00','#008026','#004dff','#750787'].forEach((c,i)=>{ctx.fillStyle=c;ctx.fillRect(-r,-r+i*(r*2/6),r*2,r*2/6+1);});}
    else {const img=pictures[p.skin];if(img?.complete&&img.naturalWidth)ctx.drawImage(img,-r,-r,r*2,r*2);else circle(0,0,r,'#8caa58');}ctx.restore();
    if(p.shieldUntil>now){ctx.beginPath();ctx.arc(0,0,r+9+Math.sin(now/180)*2,0,Math.PI*2);ctx.strokeStyle='#5f997d';ctx.setLineDash([9,6]);ctx.lineWidth=3;ctx.stroke();ctx.setLineDash([]);}
    // Keep the portrait clear: name and mass sit below the circular skin.
    ctx.font=`bold ${Math.max(13,Math.min(22,r*.23))}px Arial`;ctx.textAlign='center';ctx.fillStyle='#fffaf0';ctx.strokeStyle='#252820';ctx.lineWidth=4;ctx.lineJoin='round';ctx.strokeText(p.name,0,r+23);ctx.fillText(p.name,0,r+23);
    ctx.font='11px Arial';ctx.fillStyle='#626e55';ctx.fillText(String(p.mass),0,r+40);ctx.restore();
  }
  let frameDt=.016;
  function frame(time){
    frameDt=Math.min(.05,(time-lastFrame)/1000);lastFrame=time;requestAnimationFrame(frame);if(!playing||!state)return;
    const now=Date.now()+serverOffset, me=state.players.find(p=>p.id===myId), pink=me?.rainbow;
    ctx.fillStyle=pink?'#f7dbe7':'#edf0e3';ctx.fillRect(0,0,width,height);
    if(me){const a=1-Math.exp(-frameDt*8);camera.x+=(me.x-camera.x)*a;camera.y+=(me.y-camera.y)*a;zoom+=(targetZoom(me.mass)-zoom)*a;}
    ctx.save();ctx.translate(width/2,height/2);ctx.scale(zoom,zoom);ctx.translate(-camera.x,-camera.y);
    ctx.strokeStyle=pink?'#e5bed1':'#d8dfca';ctx.lineWidth=1/zoom;ctx.beginPath();
    for(let n=0;n<=state.world;n+=80){ctx.moveTo(n,0);ctx.lineTo(n,state.world);ctx.moveTo(0,n);ctx.lineTo(state.world,n);}ctx.stroke();
    ctx.strokeStyle='#92a07d';ctx.lineWidth=8;ctx.strokeRect(0,0,state.world,state.world);
    ctx.fillStyle=pink?'#dfb4c9':'#d1d9bf';ctx.font='bold 55px Georgia';ctx.textAlign='center';ctx.fillText('BEYLERBEYİ PASTANESİ',1600,1450);ctx.font='17px Arial';ctx.fillText('SON POĞAÇA BU MASADA',1600,1490);
    const left=camera.x-width/zoom/2-10,right=camera.x+width/zoom/2+10,top=camera.y-height/zoom/2-10,bottom=camera.y+height/zoom/2+10;
    for(const f of state.food)if(f.x>left&&f.x<right&&f.y>top&&f.y<bottom)circle(f.x,f.y,5,foodColors[f.color]);
    if(state.pastry){const p=state.pastry;circle(p.x,p.y,44+Math.sin(time/240)*6,'#e9b84435');circle(p.x,p.y,31,'#e3ac54');circle(p.x,p.y,14,'#c68b3e');for(let i=0;i<5;i++){const angle=i*1.256;circle(p.x+Math.cos(angle)*20,p.y+Math.sin(angle)*20,4,'#56663b');}ctx.fillStyle='#a5742d';ctx.font='bold 16px Arial';ctx.fillText('SON ZEYTİNLİ POĞAÇA',p.x,p.y-60);}
    state.players.filter(p=>p.alive).sort((a,b)=>a.mass-b.mass).forEach(p=>drawPlayer(p,now));ctx.restore();
    const present=new Set(state.players.map(p=>p.id));for(const id of renderPlayers.keys())if(!present.has(id))renderPlayers.delete(id);
    const active=!!state.pastry, remaining=Math.max(0,(active?state.pastry.until:state.nextEvent)-now), seconds=Math.ceil(remaining/1000);
    $('event-time').textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
    $('event-label').textContent=active?'POĞAÇA FIRINDAN ÇIKTI!':'SON ZEYTİNLİ POĞAÇA';$('event-hint').textContent=active?'Merkeze git · +600 kütle':'Fırından çıkmasına';$('event-time').parentElement.classList.toggle('active',active);
    if(active&&me){const angle=Math.atan2(1600-me.y,1600-me.x);ctx.save();ctx.translate(width/2+Math.cos(angle)*Math.min(width*.28,210),height/2+Math.sin(angle)*Math.min(height*.28,160));ctx.rotate(angle);ctx.beginPath();ctx.moveTo(14,0);ctx.lineTo(-8,-7);ctx.lineTo(-8,7);ctx.closePath();ctx.fillStyle='#c2872d';ctx.fill();ctx.restore();}
    $('respawn').disabled=Date.now()-deathAt<1600;
    mc.clearRect(0,0,150,150);mc.strokeStyle='#cbd4bc';mc.strokeRect(4,4,142,142);
    if(active){mc.fillStyle='#d39335';mc.beginPath();mc.arc(75,75,5,0,Math.PI*2);mc.fill();}
    for(const p of state.players)if(p.alive){mc.fillStyle=p.id===myId?'#e94d36':'#758e64';mc.beginPath();mc.arc(4+p.x/state.world*142,4+p.y/state.world*142,p.id===myId?4:2.5,0,Math.PI*2);mc.fill();}
  }
  requestAnimationFrame(frame);
})();
