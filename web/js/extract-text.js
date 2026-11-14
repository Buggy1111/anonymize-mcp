"use strict";
/* extract-text.js — extrakce textu z nahraného souboru (TXT/PDF/DOCX), vše v prohlížeči.
   Sdíleno anonymizérem i toolkitem. Vyžaduje pdf.js a mammoth.js (načtené z CDN). */
// pdf.js 5.x je ES modul (type="module" = deferred) → workerSrc nastavujeme líně
// až při prvním použití, ne při načtení tohoto (klasického) skriptu.
const PDF_WORKER="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/5.4.149/pdf.worker.min.mjs";

async function extractText(file){
  const name=(file.name||"").toLowerCase();
  if(name.endsWith(".txt")||file.type==="text/plain") return await file.text();
  if(name.endsWith(".pdf")||file.type==="application/pdf"){
    if(!window.pdfjsLib) throw new Error("pdf.js se nenačetlo");
    if(!pdfjsLib.GlobalWorkerOptions.workerSrc) pdfjsLib.GlobalWorkerOptions.workerSrc=PDF_WORKER;
    const pdf=await pdfjsLib.getDocument({data:await file.arrayBuffer()}).promise;
    let out="";
    for(let i=1;i<=pdf.numPages;i++){ const pg=await pdf.getPage(i); const tc=await pg.getTextContent();
      out+=tc.items.map(it=>it.str).join(" ")+"\n"; }
    return out.trim();
  }
  if(name.endsWith(".docx")){
    if(!window.mammoth) throw new Error("mammoth se nenačetlo");
    return (await mammoth.extractRawText({arrayBuffer:await file.arrayBuffer()})).value.trim();
  }
  throw new Error("nepodporovaný formát (jen TXT, PDF, DOCX)");
}
