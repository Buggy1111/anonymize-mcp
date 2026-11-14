"use strict";
/* anonymize-app.js — DOM vrstva stránky anonymizéru.
   Závisí na anonymize-engine.js (anonymize/fetchNER/…) a extract-text.js (extractText). */

const MAX_CHARS=20000; // jednotný limit vstupu (textarea má i maxlength, soubor se ořeže)
const input=document.getElementById("input"), output=document.getElementById("output");
const tableEl=document.getElementById("table"), statsEl=document.getElementById("stats");
const repcount=document.getElementById("repcount"), incount=document.getElementById("incount");
const nerinfo=document.getElementById("nerinfo");

function clear(el){while(el.firstChild)el.removeChild(el.firstChild);}
function span(cls,text){const s=document.createElement("span");if(cls)s.className=cls;s.textContent=text;return s;}

let lastAnon="";
function render(anonymized,replacements){
  lastAnon=anonymized;

  // výstup s zvýrazněnými placeholdery — čisté DOM uzly (matchAll, žádný innerHTML)
  clear(output);
  if(!anonymized){output.appendChild(span("placeholder","Výsledek se zobrazí tady."));}
  else{
    let last=0;
    for(const m of anonymized.matchAll(PH_RE)){
      if(m.index>last) output.appendChild(document.createTextNode(anonymized.slice(last,m.index)));
      output.appendChild(span("ph-tok t-"+m[0].replace(/\d+$/,""),m[0]));
      last=m.index+m[0].length;
    }
    if(last<anonymized.length) output.appendChild(document.createTextNode(anonymized.slice(last)));
  }

  // statistiky
  clear(statsEl);
  const byType={}; replacements.forEach(x=>byType[x.type]=(byType[x.type]||0)+1);
  Object.keys(byType).forEach(t=>{
    const s=span("stat","");const b=document.createElement("b");b.textContent=byType[t];
    s.appendChild(b);s.appendChild(document.createTextNode(" "+(TYPE_LABELS[t]||t)));statsEl.appendChild(s);
  });
  if(replacements.length){
    const s=span("stat total","");
    const b=document.createElement("b");b.textContent=replacements.length;
    s.appendChild(b);s.appendChild(document.createTextNode(" celkem"));statsEl.appendChild(s);
  }

  // tabulka
  repcount.textContent=replacements.length;
  clear(tableEl);
  if(!replacements.length){tableEl.appendChild(span("empty","Zatím nic k nahrazení. Vložte text nebo zkuste ukázku."));return;}
  const table=document.createElement("table");
  const thead=document.createElement("thead");const htr=document.createElement("tr");
  ["Originál","Značka","Druh"].forEach(h=>{const th=document.createElement("th");th.textContent=h;htr.appendChild(th);});
  thead.appendChild(htr);table.appendChild(thead);
  const tbody=document.createElement("tbody");
  const seen=new Set();
  replacements.forEach(x=>{
    if(seen.has(x.placeholder))return; seen.add(x.placeholder);
    const tr=document.createElement("tr");
    const td1=document.createElement("td");td1.className="orig";td1.textContent=x.original;
    const td2=document.createElement("td");td2.appendChild(span("ph-tok t-"+x.type,x.placeholder));
    const td3=document.createElement("td");td3.appendChild(span("badge",x.label||x.type));
    tr.appendChild(td1);tr.appendChild(td2);tr.appendChild(td3);tbody.appendChild(tr);
  });
  table.appendChild(tbody);tableEl.appendChild(table);
}

const EXAMPLES={
  "Právní spis":"Žalobce Jan Novák, nar. 15.3.1980, rodné číslo 800315/1234, bytem Sokolovská 12, Praha, podal dne 3.2.2026 ke Krajskému soudu návrh na zaplacení 85 000 Kč proti žalované Marii Svobodové (IČO 12345679, DIČ CZ12345679). Kontakt: jan.novak@email.cz, tel. 777 123 456. Spis sp. zn. 25 C 145/2026. Účet 1234567890/0800.",
  "Faktura":"Odběratel: Petr Dvořák, Husova 5, Ostrava, PSČ 702 00. IČO 87654326, DIČ CZ87654326. Splatnost 30.4.2026. Platba na účet 19-2000145399/0800, IBAN CZ65 0800 0000 1920 0014 5399. Dotazy: petr.dvorak@firma.cz, 605 999 111 nebo https://faktury.firma.cz.",
  "E-mail":"Dobrý den, jmenuji se Eva Černá, bydlím v Brně. Moje číslo je 720 555 333 a email eva.cerna@seznam.cz. Narozena 22.11.1990, rodné číslo 905322/4567.",
  "Lékařská zpráva":"Pacientka Marie Nováková, nar. 14.6.1975, rodné číslo 755614/1234, bytem Tyršova 8, Olomouc, byla přijata 12.5.2026 na interní oddělení s diagnózou arteriální hypertenze. Ošetřující lékař MUDr. Petr Svoboda, kontakt petr.svoboda@nemocnice.cz, tel. 585 111 222. Doporučena kontrola za 14 dní."
};
// ── režim (lokální regex / plný NER) + debounce ──
let nerTimer=null, nerSeq=0;
function currentMode(){const el=document.querySelector('input[name="mode"]:checked');return el?el.value:"local";}
// auto-grow: vstupní pole roste s obsahem (jako výstup), uživatel nemusí scrolovat
function autoGrow(){input.style.overflowY="hidden";input.style.height="auto";input.style.height=Math.max(input.scrollHeight,300)+"px";}
function run(){
  if(input.value.length>MAX_CHARS) input.value=input.value.slice(0,MAX_CHARS); // pojistka k maxlength (review #18)
  const text=input.value;
  autoGrow();
  incount.textContent=text.length.toLocaleString("cs-CZ")+" / "+MAX_CHARS.toLocaleString("cs-CZ")+" znaků";
  if(currentMode()==="local"){
    nerinfo.textContent="";
    const r=anonymize(text); render(r.anonymized,r.replacements);
    return;
  }
  // NER mód — počkej na ÚFAL, debounce ať netřískáme API při psaní
  const seq=++nerSeq;
  nerinfo.textContent="Zpracovává server LINDAT…";
  clearTimeout(nerTimer);
  nerTimer=setTimeout(async function(){
    if(!text.trim()){const r=anonymize(text);render(r.anonymized,r.replacements);nerinfo.textContent="";return;}
    try{
      const ents=await fetchNER(text);
      if(seq!==nerSeq) return;            // zastaralý výsledek, zahoď
      const r=anonymize(text,ents); render(r.anonymized,r.replacements);
      nerinfo.textContent="Přesný režim: jména a firmy rozpoznal NameTag (ÚFAL). Text byl odeslán na server LINDAT.";
    }catch(e){
      if(seq!==nerSeq) return;
      const r=anonymize(text); render(r.anonymized,r.replacements);
      nerinfo.textContent="Server LINDAT teď neodpovídá ("+e.message+"). Použil se lokální režim.";
    }
  },550);
}

const exWrap=document.getElementById("examples");
Object.keys(EXAMPLES).forEach(name=>{
  const b=document.createElement("button");b.type="button";b.className="chip";b.textContent=name;b.setAttribute("aria-pressed",String(name==="Právní spis"));
  b.onclick=function(){input.value=EXAMPLES[name];run();exWrap.querySelectorAll(".chip").forEach(c=>c.setAttribute("aria-pressed",String(c===b)));};exWrap.appendChild(b);
});
document.getElementById("copy").onclick=function(){
  const b=document.getElementById("copy");
  const done=t=>{b.textContent=t;setTimeout(function(){b.textContent="Kopírovat";},1600);};
  if(navigator.clipboard) navigator.clipboard.writeText(lastAnon).then(()=>done("Zkopírováno"),()=>done("Kopírování se nepovedlo"));
  else done("Kopírování se nepovedlo");
};
input.addEventListener("input",run);
document.querySelectorAll('input[name="mode"]').forEach(r=>r.addEventListener("change",run));
input.value=EXAMPLES["Právní spis"];
run();

// ── upload souboru (PDF/Word/TXT) → vyplní vstup ──
(function(){
  const fi=document.getElementById("anon-file"), fst=document.getElementById("anon-fst");
  if(!fi) return;
  fi.addEventListener("change",async function(){
    const f=fi.files&&fi.files[0]; if(!f) return;
    fst.className="fst"; fst.textContent="Načítám "+f.name+"…";
    try{
      if(f.size>10*1024*1024) throw new Error("soubor je moc velký (max 10 MB)");
      const txt=await extractText(f);
      input.value=txt.slice(0,MAX_CHARS); run();
      fst.className="fst ok"; fst.textContent=f.name+" načten ("+input.value.length.toLocaleString("cs-CZ")+" znaků)";
    }catch(e){ fst.className="fst err"; fst.textContent="Soubor se nepodařilo načíst: "+e.message; }
    fi.value="";
  });
})();
