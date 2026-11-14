"use strict";
/* landing.js — úvodní stránka.
   1) Spis: osobní údaje v obří větě se při scrollu skartují a dopadne na ně štítek (OSOBA1…).
      Po 4 s nečinnosti se ukázka přehraje sama. Najetí myší = krátké „cuknutí" skartovačky.
   2) „Kam putuje váš text": dveře se rozjedou, zablokovaný paket, čísla, přepnutí na přesný režim.
   3) Živá ukázka: skutečný engine (anonymize-engine.js) v lokálním režimu.
   Žádný innerHTML — jen DOM metody. */
(function(){
const root=document.documentElement, reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v)), smooth=(e0,e1,x)=>{const t=clamp((x-e0)/(e1-e0));return t*t*(3-2*t);};
const ease=t=>1-Math.pow(1-t,4), $=id=>document.getElementById(id);

/* ── 1. spis ── */
const dtext=$("dtext");
// rozdělit na slova (vjezd zdola); interpunkci za údajem přilepit k němu, ať řádek nezačíná čárkou
let lastPii=null;
const mk=()=>{const w=document.createElement("span");w.className="w";const i=document.createElement("span");i.className="wi";w.appendChild(i);return [w,i];};
[...dtext.childNodes].forEach(n=>{
  if(n.nodeType===3){ const frag=document.createDocumentFragment(); let txt=n.textContent;
    const lead=txt.match(/^[^ ]+/); if(lead&&lastPii){ lastPii.appendChild(document.createTextNode(lead[0])); txt=txt.slice(lead[0].length); }
    txt.split(/( +)/).forEach(part=>{ if(!part) return; if(/^ +$/.test(part)){frag.appendChild(document.createTextNode(part));return;}
      const [w,i]=mk(); i.textContent=part; frag.appendChild(w); });
    lastPii=null; n.replaceWith(frag); }
  else { const [w,i]=mk(); n.replaceWith(w); i.appendChild(n); i.style.whiteSpace="nowrap"; lastPii=i; }
});

let INK="#000";
const DPR=Math.min(devicePixelRatio||1,2);
const piis=[...dtext.querySelectorAll(".pii")].map((el,i)=>{
  const text=el.textContent, cv=document.createElement("canvas"), rb=document.createElement("span"), tk=document.createElement("span");
  cv.setAttribute("aria-hidden","true"); rb.className="rb"; tk.className="tk"; tk.textContent=el.dataset.tok; tk.setAttribute("aria-hidden","true");
  el.append(cv,rb,tk);
  const o={el,text,cv,ctx:cv.getContext("2d"),rb,tk,i,off:document.createElement("canvas"),hover:0,hoverT:0,last:-1,w:0,h:0,H:0,base:0,font:"",img:null};
  el.addEventListener("pointerenter",()=>o.hoverT=1); el.addEventListener("pointerleave",()=>o.hoverT=0);
  return o;
});
function readColors(){ INK=getComputedStyle(root).getPropertyValue("--pii").trim()||INK; piis.forEach(p=>{p.last=-1;p.img=null;}); }
document.addEventListener("themechange",()=>requestAnimationFrame(readColors));
function measure(){
  piis.forEach(p=>{ const cs=getComputedStyle(p.el); p.font=`${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    p.w=p.el.offsetWidth+28; p.h=p.el.offsetHeight; p.H=p.h*3.2;
    p.cv.width=Math.round(p.w*DPR); p.cv.height=Math.round(p.H*DPR); p.cv.style.width=p.w+"px"; p.cv.style.height=p.H+"px";
    const m=p.ctx; m.font=p.font; const mt=m.measureText("Hg");
    const asc=mt.fontBoundingBoxAscent||parseFloat(cs.fontSize)*.8, desc=mt.fontBoundingBoxDescent||parseFloat(cs.fontSize)*.2;
    p.base=(p.h-(asc+desc))/2+asc; p.last=-1; p.img=null; });
}
function textImg(p){ const o=p.off; o.width=Math.round(p.w*DPR); o.height=Math.round(p.h*DPR); const x=o.getContext("2d");
  x.setTransform(DPR,0,0,DPR,0,0); x.clearRect(0,0,p.w,p.h); x.font=p.font; x.fillStyle=INK; x.fillText(p.text,14,p.base); p.img=o; }
// skartovačka: údaj rozřezaný na 7 proužků, které se rozjedou, natočí a propadnou z řádku
function drawShred(p,f){
  if(!p.img) textImg(p);
  const c=p.ctx, n=7, sh=p.img.height/n, W=p.img.width;
  c.setTransform(1,0,0,1,0,0); c.clearRect(0,0,p.cv.width,p.cv.height);
  for(let i=0;i<n;i++){ const dir=i%2?1:-1, fall=Math.pow(clamp(f*1.25-i*.035),2);
    c.save(); c.globalAlpha=1-smooth(.6,1,f);
    c.translate(W/2+dir*f*(10+i*2)*DPR, i*sh+sh/2+fall*p.h*(1.7+i*.07)*DPR); c.rotate(dir*f*(.05+i*.008));
    c.drawImage(p.img,0,i*sh,W,sh,-W/2,-sh/2,W,sh+.5); c.restore(); }
}
const dossier=$("dossier"), cap0=$("cap0"), cap1=$("cap1"), cnt=$("cnt"), dprog=$("dprog");
function progress(el){ const r=el.getBoundingClientRect(); return clamp(-r.top/(el.offsetHeight-innerHeight)); }

// nečinnost: po 4 s bez vstupu nahoře se skartování přehraje, podrží, přetočí zpět a opakuje
const IDLE=4000, CYCLE=9200; let lastInput=performance.now(), autoStart=0, autoP=0;
["scroll","wheel","pointermove","pointerdown","keydown","touchstart"].forEach(ev=>addEventListener(ev,()=>{lastInput=performance.now();},{passive:true}));
function autoplay(sP,now){
  if(!reduce && sP<.01 && now-lastInput>IDLE){ if(!autoStart) autoStart=now; const t=(now-autoStart)%CYCLE;
    autoP = t<3400 ? ease(t/3400)*.88 : t<6400 ? .88 : t<7600 ? .88*(1-ease((t-6400)/1200)) : 0; }
  else { autoStart=0; autoP+=(0-autoP)*.12; if(autoP<.002) autoP=0; }
  return autoP;
}

/* ── 2. dveře a cesta dat ── */
const vault=$("vault"), vmask=$("vmask");
const V_={dl:$("dl"),dr:$("dr"),bA:$("bA"),bB:$("bB"),hA1:$("hA1"),hA2:$("hA2"),flowA:$("flowA"),stats:[...$("statsA").children],
  sw:$("swK"),swL:$("swL"),swR:$("swR"),flowB:$("flowB"),wireB:$("wireB"),noteB:$("noteB")};
const show=(el,o,dy=24)=>{ el.style.opacity=o; el.style.transform=`translateY(${(1-o)*dy}px)`; };
function vaultFrame(V){
  const dk=ease(smooth(.05,.2,V)), shd=Math.sin(Math.PI*dk);
  V_.dl.style.transform=`translateX(${-dk*101}%)`; V_.dr.style.transform=`translateX(${dk*101}%)`;
  V_.dl.style.setProperty("--sh",shd); V_.dr.style.setProperty("--sh",shd); vmask.style.transform=`scale(${.94+.06*dk})`;
  const a1=smooth(.16,.26,V); V_.hA1.style.opacity=a1; V_.hA1.style.transform=`scale(${1.18-.18*ease(a1)})`;
  show(V_.hA2,smooth(.24,.34,V),40);
  const fa=smooth(.34,.44,V); show(V_.flowA,fa); V_.flowA.classList.toggle("go",fa>.6);
  V_.stats.forEach((d,i)=>show(d,smooth(.42+i*.03,.5+i*.03,V)));
  const outA=1-smooth(.62,.7,V), inB=smooth(.68,.76,V);
  V_.bA.style.opacity=outA; V_.bA.style.transform=`translateY(${-(1-outA)*40}px)`; V_.bA.style.visibility=outA<.01?"hidden":"visible";
  V_.bB.style.opacity=inB; V_.bB.style.transform=`translateY(${(1-inB)*40}px)`; V_.bB.style.visibility=inB<.01?"hidden":"visible";
  const k=ease(smooth(.78,.84,V)); V_.sw.style.transform=`translateX(${k*22}px)`; V_.swL.style.opacity=1-.6*k; V_.swR.style.opacity=.4+.6*k;
  const w=smooth(.84,.9,V); V_.wireB.style.transform=`scaleX(${w})`; V_.flowB.classList.toggle("go",w>.98);
  show(V_.noteB,smooth(.88,.95,V));
}

let shown=piis.length;
function tick(now){
  const sP=reduce?(progress(dossier)>.02?1:0):progress(dossier);
  const P=Math.max(sP,autoplay(sP,now));
  let left=0;
  piis.forEach(p=>{
    const a=clamp((P-.06-p.i*.11)/.3);
    p.hover+=(p.hoverT*(a<.05?1:0)-p.hover)*.14;
    const f=Math.max(smooth(.02,.55,a),p.hover*.12), on=f>.004&&a<.98;
    if(on){ const q=Math.round(f*200)/200; if(q!==p.last){ drawShred(p,q); p.last=q; } }
    p.cv.style.visibility=on?"visible":"hidden"; p.el.style.color=on||a>.98?"transparent":"";
    const k=smooth(.5,.8,a), drop=(1-ease(k))*-.7;
    p.rb.style.transform=`translateY(${drop}em)`; p.rb.style.opacity=k;
    p.tk.style.transform=`translateY(${drop}em)`; p.tk.style.opacity=smooth(.6,.9,a); p.tk.style.letterSpacing=(.24-.12*smooth(.6,.9,a))+"em";
    if(a<.6) left++;
  });
  if(left!==shown){ shown=left; cnt.textContent=left; }
  const c0=smooth(.55,.66,P), c1=smooth(.66,.78,P);
  cap0.style.opacity=1-c0; cap0.style.transform=`translateY(${-c0*14}px)`;
  cap1.style.opacity=c1; cap1.style.transform=`translateY(${(1-c1)*14}px)`;
  dprog.style.transform=`scaleX(${P})`;
  vaultFrame(reduce?1:progress(vault));
  requestAnimationFrame(tick);
}

let rt=0; addEventListener("resize",()=>{ clearTimeout(rt); rt=setTimeout(measure,150); });
(document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(()=>{
  measure(); readColors();
  const free=()=>document.querySelectorAll("#dtext .w").forEach(w=>w.classList.add("free"));
  if(!reduce){
    const ws=document.querySelectorAll("#dtext .wi"); let last=null;
    ws.forEach((w,i)=>{ last=w.animate([{transform:"translateY(115%)"},{transform:"none"}],{duration:1300,delay:100+i*35,easing:"cubic-bezier(.16,1,.3,1)",fill:"backwards"}); });
    if(last) last.finished.then(free,free); else free();
    document.querySelectorAll(".d-meta,.d-foot").forEach((el,i)=>el.animate([{opacity:0,transform:"translateY(16px)"},{opacity:1,transform:"none"}],{duration:1200,delay:600+i*100,easing:"cubic-bezier(.16,1,.3,1)",fill:"backwards"}));
    // první obrazovka hned ukáže, o co jde: každý údaj krátce „cukne"
    piis.forEach((p,i)=>{ setTimeout(()=>p.hoverT=1,1500+i*260); setTimeout(()=>{ if(!p.el.matches(":hover")) p.hoverT=0; },2020+i*260); });
  } else free();
  requestAnimationFrame(tick);
});

/* ── 3. živá ukázka ── */
const SAMPLES={
  zaloba:"Žalobce Jan Novák, nar. 12. 3. 1978, r. č. 780312/1234, bytem Husova 12, 602 00 Brno, tel. +420 603 123 456, e-mail jan.novak@seznam.cz, se domáhá zaplacení 85 000 Kč na účet CZ65 0800 0000 1920 0014 5399. Žalovaná, IČO 27074358, se nevyjádřila.",
  zprava:"Pacientka Marie Dvořáková, r. č. 855124/0012, přijata 4. 11. 2026 pro bolesti na hrudi, dg. I21.0. Kontakt na dceru: 731 456 789. Bydliště Palackého 8, 779 00 Olomouc, e-mail marie.dvorakova@email.cz.",
  smlouva:"Prodávající: Petr Svoboda, nar. 2. 7. 1965, trvale bytem Nádražní 45, 702 00 Ostrava. Kupující: Eva Horáková, datová schránka ab3cd7e. Vozidlo SPZ 2T5 4321, VIN TMBJJ7NE8L0123456. Kupní cena 240 000 Kč na účet 19-2000145399/0800."
};
const src=$("src"), out=$("out"), nEl=$("n"), G="▓▒░█■#%@&";
function scramble(el,from,to,dur){ if(reduce){ el.textContent=to; return; }
  const st=performance.now(), L=Math.max(from.length,to.length);
  (function f(now){ const q=Math.min(1,(now-st)/dur); let s="";
    for(let i=0;i<L;i++) s+= i/L<q?(to[i]||""):(q<.15?(from[i]||""):G[(Math.random()*G.length)|0]);
    el.textContent=s; if(q<1) requestAnimationFrame(f); else el.textContent=to; })(st);
}
let animate=false, seen=false, tm=0;
function run(){
  let r; try{ r=anonymize(src.value); }catch(e){ r={anonymized:src.value,replacements:[]}; }
  const map=new Map(r.replacements.map(x=>[x.placeholder,x.original])); out.textContent=""; const toks=[]; let last=0;
  for(const m of r.anonymized.matchAll(new RegExp(PH_RE.source,"g"))){
    if(m.index>last) out.appendChild(document.createTextNode(r.anonymized.slice(last,m.index)));
    const s=document.createElement("span"); s.className="tok"; s.textContent=m[0]; s.dataset.ph=m[0]; s.dataset.orig=map.get(m[0])||m[0]; s.title=s.dataset.orig;
    out.appendChild(s); toks.push(s); last=m.index+m[0].length;
  }
  if(last<r.anonymized.length) out.appendChild(document.createTextNode(r.anonymized.slice(last)));
  const n=r.replacements.length; nEl.textContent=n+(n===1?" údaj":n>=2&&n<=4?" údaje":" údajů");
  if(animate&&!reduce) toks.forEach((t,i)=>{ t.classList.add("raw"); t.textContent=t.dataset.orig;
    setTimeout(()=>{ t.classList.remove("raw"); scramble(t,t.dataset.orig,t.dataset.ph,450); },300+i*110); });
  animate=false;
}
function load(k){ src.value=SAMPLES[k]; animate=seen; run();
  document.querySelectorAll(".chip[data-s]").forEach(c=>c.setAttribute("aria-pressed",String(c.dataset.s===k))); }
document.querySelectorAll(".chip[data-s]").forEach(c=>c.addEventListener("click",()=>{ seen=true; load(c.dataset.s); }));
src.addEventListener("input",()=>{ clearTimeout(tm); tm=setTimeout(run,140); });
$("copy").addEventListener("click",async e=>{ const b=e.currentTarget, txt=[...out.childNodes].map(n=>n.dataset&&n.dataset.ph||n.textContent).join("");
  try{ await navigator.clipboard.writeText(txt); b.textContent="Zkopírováno"; }
  catch(err){ const s=getSelection(), g=document.createRange(); g.selectNodeContents(out); s.removeAllRanges(); s.addRange(g); b.textContent="Označeno, Ctrl+C"; }
  setTimeout(()=>b.textContent="Kopírovat",1800); });
load("zaloba");
if("IntersectionObserver" in window){
  new IntersectionObserver((es,o)=>es.forEach(en=>{ if(en.isIntersecting){ seen=true; animate=true; run(); o.disconnect(); } }),{threshold:.4}).observe(out);
  const f=document.querySelector("[data-to]");
  if(f&&!reduce) new IntersectionObserver((es,o)=>es.forEach(en=>{ if(!en.isIntersecting) return; o.disconnect();
    const to=+f.dataset.to, st=performance.now();
    (function step(now){ const q=Math.min(1,(now-st)/1600); f.textContent=Math.round(ease(q)*to)+"+"; if(q<1) requestAnimationFrame(step); })(st);
  }),{threshold:.6}).observe(f);
}
})();
