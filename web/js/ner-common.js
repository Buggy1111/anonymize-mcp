"use strict";
/* ner-common.js — sdílené ÚFAL LINDAT utility: POST helper s timeoutem/abortem
   + CoNLL parser NameTagu. Používají ho anonymize-engine.js i toolkit.js
   (dřív měl každý vlastní kopii — review #13/#14). */

const NER_API_BASE="https://lindat.mff.cuni.cz/services";

// POST na LINDAT API — 30s timeout, ať se UI nezasekne na viselci
async function apiPost(url,params){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),30000);
  try{
    const body=Object.entries(params).map(([k,v])=>k+"="+encodeURIComponent(v)).join("&");
    const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body,signal:ctrl.signal});
    if(!r.ok) throw new Error("API "+r.status);
    return r;
  }catch(e){
    if(e.name==="AbortError") throw new Error("vypršel časový limit (30 s)");
    throw e;
  }finally{ clearTimeout(timer); }
}

// CoNLL výstup NameTagu → entity {type, text}; bere jen nejvnější label
// (čisté maximální entity), lepí interpunkci a zkratky/domény (".cz").
function parseConll(conll){
  const ents=[]; let cur=null;
  for(const raw of (conll||"").split("\n")){
    const l=raw.replace(/\r$/,"");
    if(!l.trim()){ if(cur){ents.push(cur);cur=null;} continue; }
    const p=l.split("\t"); if(p.length<2){ continue; }
    const tok=p[0], first=p[1].split("|")[0];
    if(first==="O"){ if(cur){ents.push(cur);cur=null;} continue; }
    if(first.startsWith("B-")){ if(cur)ents.push(cur); cur={type:first.slice(2),tokens:[tok]}; }
    else if(first.startsWith("I-")){ if(cur)cur.tokens.push(tok); else cur={type:first.slice(2),tokens:[tok]}; }
  }
  if(cur)ents.push(cur);
  for(const e of ents) e.text=e.tokens.join(" ").replace(/\s+([.,;:!?)])/g,"$1").replace(/\s*\.\s*([a-z]{2,4})\b/gi,".$1");
  return ents;
}
