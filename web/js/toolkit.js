"use strict";
/* toolkit.js — multi-nástrojový toolkit (NER, morfologie, korektor, překlad).
   Vše volá ÚFAL LINDAT API přímo z prohlížeče.
   Závisí na extract-text.js (extractText) a ner-common.js (apiPost, parseConll, NER_API_BASE). */
const API=NER_API_BASE;

// napoj všechny upload inputy na cílový textarea
function wireUploads(){
  document.querySelectorAll('input[type="file"][data-target]').forEach(function(inp){
    inp.addEventListener("change",async function(){
      const f=inp.files&&inp.files[0]; if(!f) return;
      const ta=document.getElementById(inp.dataset.target);
      const st=inp.dataset.status?document.getElementById(inp.dataset.status):null;
      if(st){st.className="status";st.textContent="Načítám "+f.name+"…";}
      try{
        if(f.size>10*1024*1024) throw new Error("soubor je moc velký (max 10 MB)");
        const txt=await extractText(f);
        ta.value=txt.slice(0,20000);
        ta.dispatchEvent(new Event("input"));
        if(st){st.className="status ok";st.textContent=f.name+" načten ("+ta.value.length.toLocaleString("cs-CZ")+" znaků)";}
      }catch(e){ if(st){st.className="status err";st.textContent="Soubor se nepodařilo načíst: "+e.message;} }
      inp.value="";
    });
  });
}
function $(id){return document.getElementById(id);}
function clr(el){while(el.firstChild)el.removeChild(el.firstChild);}
function setStatus(el,msg,cls){el.className="status"+(cls?" "+cls:"");el.textContent=msg;}

// ── taby ──
document.querySelectorAll(".tab:not(.dis)").forEach(t=>t.onclick=function(){
  document.querySelectorAll(".tab").forEach(x=>{x.classList.remove("active");x.setAttribute("aria-selected","false");});
  document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));
  t.classList.add("active");t.setAttribute("aria-selected","true");
  document.querySelector('.panel[data-p="'+t.dataset.t+'"]').classList.add("active");
});

const MAX_CHARS=20000;
// POST helper (timeout/abort) je sdílený v ner-common.js (apiPost)
// guard: prázdný / příliš dlouhý vstup (vyčistí i starý výstup)
function guard(text,st,out){
  if(out)clr(out);
  if(!text.trim()){ setStatus(st,"Vložte nějaký text",""); return false; }
  if(text.length>MAX_CHARS){ setStatus(st,"Text je příliš dlouhý (max "+MAX_CHARS.toLocaleString("cs-CZ")+" znaků)","err"); return false; }
  return true;
}

// ── NER (NameTag) ──
const NER_LABEL={P:"osoba",pf:"křestní",ps:"příjmení",gu:"město",gs:"stát",gc:"region",
  "if":"firma",io:"instituce",ic:"značka",o:"objekt",t:"datum/čas",T:"datum",ty:"rok",td:"den",tm:"měsíc",at:"telefon",az:"PSČ",n:"číslo"};
// pozn. (review #19): NER_LABEL = jemné CNEC podtypy pro ZOBRAZENÍ; nerCategory()
// v anonymize-engine.js = hrubé anonymizační kategorie. Záměrně dvě různé mapy.
$("ner-go").onclick=async function(){const b=this,st=$("ner-st"),out=$("ner-out");if(!guard($("ner-in").value,st,out))return;b.disabled=true;setStatus(st,"Zpracovává NameTag…");
  try{const r=await apiPost(API+"/nametag/api/recognize",{data:$("ner-in").value,output:"conll"});
    const ents=parseConll((await r.json()).result);clr(out);
    if(!ents.length){out.appendChild(document.createTextNode("V textu nejsou žádné entity."));}
    else ents.forEach(e=>{const s=document.createElement("span");s.className="ent ent-"+e.type;
      s.textContent=e.text+" · "+(NER_LABEL[e.type]||e.type);s.title=NER_LABEL[e.type]||e.type;out.appendChild(s);});
    setStatus(st,ents.length+(ents.length===1?" entita":ents.length>=2&&ents.length<=4?" entity":" entit"),"ok");
  }catch(e){setStatus(st,"Server neodpověděl: "+e.message,"err");}finally{b.disabled=false;}};

// ── Morfologie (UDPipe) ──
const UPOS={NOUN:"podst. jméno",PROPN:"vlastní jméno",VERB:"sloveso",AUX:"pom. sloveso",ADJ:"příd. jméno",
  ADV:"příslovce",PRON:"zájmeno",DET:"determinant",NUM:"číslovka",ADP:"předložka",CCONJ:"spojka",SCONJ:"spojka",
  PART:"částice",INTJ:"citoslovce",PUNCT:"interpunkce",SYM:"symbol",X:"jiné"};
$("morf-go").onclick=async function(){const b=this,st=$("morf-st"),out=$("morf-out");if(!guard($("morf-in").value,st,out))return;b.disabled=true;setStatus(st,"Zpracovává UDPipe…");
  try{const r=await apiPost(API+"/udpipe/api/process",{data:$("morf-in").value,tokenizer:"",tagger:"",model:"czech",output:"conllu"});
    const lines=(await r.json()).result.split("\n").filter(l=>l&&!l.startsWith("#"));
    clr(out);const tbl=document.createElement("table");
    const thead=document.createElement("thead"),htr=document.createElement("tr");
    ["Slovo","Lemma","Slovní druh","Rysy"].forEach(h=>{const th=document.createElement("th");th.textContent=h;htr.appendChild(th);});
    thead.appendChild(htr);tbl.appendChild(thead);const tb=document.createElement("tbody");let n=0;
    lines.forEach(l=>{const c=l.split("\t");if(c.length<6||c[0].includes("-"))return;n++;
      const tr=document.createElement("tr");
      const mk=(cls,txt)=>{const td=document.createElement("td");if(cls)td.className=cls;td.textContent=txt;return td;};
      tr.appendChild(mk("w",c[1]));tr.appendChild(mk("l",c[2]));tr.appendChild(mk("p",UPOS[c[3]]||c[3]));
      tr.appendChild(mk("f",c[5]==="_"?"":c[5]));tb.appendChild(tr);});
    tbl.appendChild(tb);out.appendChild(tbl);setStatus(st,n+" slov a znamének","ok");
  }catch(e){setStatus(st,"Server neodpověděl: "+e.message,"err");}finally{b.disabled=false;}};

// ── Korektor ──
$("korek-go").onclick=async function(){const b=this,st=$("korek-st"),out=$("korek-out");if(!guard($("korek-in").value,st,out))return;b.disabled=true;setStatus(st,"Zpracovává Korektor…");
  try{const r=await apiPost(API+"/korektor/api/correct",{data:$("korek-in").value,model:"czech-spellchecker-130202"});
    const corrected=(await r.json()).result;clr(out);
    const oa=$("korek-in").value.split(/(\s+)/),ca=corrected.split(/(\s+)/);
    if(oa.length===ca.length){
      // zarovnané tokeny → zvýrazni jen změněná slova
      ca.forEach((w,i)=>{if(/^\s+$/.test(w)){out.appendChild(document.createTextNode(w));return;}
        if(oa[i]!==w){const s=document.createElement("span");s.className="ins";s.textContent=w;out.appendChild(s);}
        else out.appendChild(document.createTextNode(w));});
    } else { out.appendChild(document.createTextNode(corrected)); } // jiný počet tokenů → čistý text
    setStatus(st,"Hotovo","ok");
  }catch(e){setStatus(st,"Server neodpověděl: "+e.message,"err");}finally{b.disabled=false;}};

// ── Překlad (Charles Translator) ──
const LANGS={cs:"čeština",en:"angličtina",de:"němčina",fr:"francouzština",pl:"polština",ru:"ruština",uk:"ukrajinština"};
function fillLangs(sel,def){Object.keys(LANGS).forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=LANGS[k];if(k===def)o.selected=true;sel.appendChild(o);});}
fillLangs($("prek-src"),"cs");fillLangs($("prek-tgt"),"en");
$("prek-go").onclick=async function(){const b=this,st=$("prek-st"),out=$("prek-out");
  const src=$("prek-src").value,tgt=$("prek-tgt").value;
  if(!guard($("prek-in").value,st,out))return;
  if(src===tgt){setStatus(st,"Vyberte dva různé jazyky","err");return;}
  b.disabled=true;setStatus(st,"Překládám…");
  try{const r=await apiPost(API+"/translation/api/v2/languages?src="+encodeURIComponent(src)+"&tgt="+encodeURIComponent(tgt),{input_text:$("prek-in").value});
    const txt=await r.text();clr(out);out.appendChild(document.createTextNode(txt.trim()));
    setStatus(st,LANGS[src]+" → "+LANGS[tgt],"ok");
  }catch(e){setStatus(st,"Server neodpověděl: "+e.message,"err");}finally{b.disabled=false;}};

// ── počítadlo znaků + auto-grow u každého textového pole ──
function updateCC(ta){const cc=document.getElementById(ta.dataset.cc);if(!cc)return;
  const n=ta.value.length;cc.textContent=n.toLocaleString("cs-CZ")+" / 20 000 znaků";cc.className="cc"+(n>MAX_CHARS?" over":"");}
function autoGrow(ta){ta.style.height="auto";ta.style.height=Math.max(ta.scrollHeight,130)+"px";}
document.querySelectorAll("textarea[data-cc]").forEach(function(ta){
  ta.style.overflowY="hidden";
  ta.addEventListener("input",function(){updateCC(ta);autoGrow(ta);});
  updateCC(ta);autoGrow(ta);
});
wireUploads();
// odkazy v patičce přepnou na příslušnou záložku
document.querySelectorAll(".foottab").forEach(function(a){a.addEventListener("click",function(){
  const t=document.querySelector('.tab[data-t="'+a.dataset.t+'"]'); if(t){t.click();window.scrollTo({top:0,behavior:"smooth"});}
});});

// deep-link přes hash (#ner, #morf, #korek, #prek) — příchod z přehledu i z patičky
function tabFromHash(){
  const h=(location.hash||"").replace("#","");
  const t=h&&document.querySelector('.tab[data-t="'+h+'"]:not(.dis)');
  if(t){t.click();const el=document.getElementById("tabs");if(el)el.scrollIntoView({behavior:"smooth",block:"start"});}
}
window.addEventListener("hashchange",tabFromHash);
tabFromHash();
