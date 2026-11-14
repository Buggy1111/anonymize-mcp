"use strict";
/* anonymize-engine.js — čistá logika anonymizace (žádné DOM).
   Lokální mód: slovníky + regex pasy. NER mód: ÚFAL NameTag (browser-direct).
   Závisí na ner-common.js (apiPost s timeoutem, parseConll). */

const FIRST_NAMES = new Set(["jan","jana","petr","petra","josef","marie","martin","jiří","jiri",
  "tomáš","tomas","pavel","pavla","michal","michaela","lukáš","lukas","jakub","david","ondřej","ondrej",
  "marek","filip","adam","vojtěch","vojtech","matěj","matej","daniel","roman","radek","milan","zdeněk","zdenek",
  "karel","václav","vaclav","františek","frantisek","ladislav","miroslav","stanislav","antonín","antonin",
  "eva","hana","anna","lenka","kateřina","katerina","lucie","veronika","tereza","barbora","markéta","marketa",
  "alena","ivana","monika","zuzana","helena","andrea","martina","dana","simona","nikola","kristýna","kristyna",
  "edita","editka","silvie","jaroslav","vladimír","vladimir","oldřich","oldrich"]);

// ⚠️ vědomý kompromis (review #10): "Most"/"Opava"/"Odry" kolidují s apelativy —
// u slovníku bez kontextu nerozlišitelné; chybujeme směrem k redakci (FP ≠ leak),
// reálné dokumenty řeší NER mód.
const CITIES = new Set(["praha","praze","prahy","prahou","prahu","brno","brně","brna","brnu","ostrava","ostravě","ostravy","ostravu","ostravou",
  "plzeň","plzen","plzni","plzně","olomouc","olomouci","olomouce","liberec","liberci","liberce","hradec","hradci","pardubice","pardubic","pardubicích",
  "zlín","zlin","zlíně","zlína","kladno","kladně","kladna","most","mostě","mostu","opava","opavě","opavy","karviná","karvina","karviné","karvinou",
  "jihlava","jihlavě","jihlavy","přerov","prerov","přerově","přerova","studénka","studenka","studénce","studénky","kopřivnice","koprivnice","kopřivnici",
  "odry","oder","odrách","fulnek","fulneku","příbor","pribor","příboře","bílovec","bilovec","bílovce","nový jičín","novém jičíně"]);

// validátory číselných identifikátorů — pustí redakci jen u reálných RČ/karet/IBAN,
// aby volnější vzory (10/16 číslic) neredigovaly náhodná čísla (over-redakce).
function validRC(s){                          // 10 číslic bez lomítka
  let mm=+s.slice(2,4);
  if(mm>70)mm-=70; else if(mm>50)mm-=50; else if(mm>20)mm-=20;  // ženy +50, 2000+ +20/+70
  const dd=+s.slice(4,6);
  if(mm<1||mm>12||dd<1||dd>31) return false;
  if((+s)%11===0) return true;                // RČ od 1954 dělitelné 11
  return (+s.slice(0,9))%11===10 && s[9]==="0"; // historická výjimka (1954–85)
}
function luhn(s){                             // platební karta — Luhnova kontrola
  let sum=0,alt=false;
  for(let i=s.length-1;i>=0;i--){let d=+s[i]; if(alt){d*=2; if(d>9)d-=9;} sum+=d; alt=!alt;}
  return sum%10===0;
}
function validIBAN(s){                         // mod-97 checksum
  const t=s.replace(/\s/g,"").toUpperCase();
  if(t.length<15||t.length>34||!/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(t)) return false;
  const r=t.slice(4)+t.slice(0,4); let rem=0;
  for(const ch of r){const v=ch>="A"?ch.charCodeAt(0)-55:+ch; rem=(rem*(v>9?100:10)+v)%97;}
  return rem===1;
}
function validICO(s){                          // IČO — mod-11 kontrolní číslice (váhy 8..2)
  let t=0;
  for(let i=0;i<7;i++) t+=(8-i)*+s[i];
  return +s[7]===((((11-t)%11)+11)%11)%10;
}
function validISODate(s){                      // ISO 2020-01-05 — reálný rok/měsíc/den
  const y=+s.slice(0,4),m=+s.slice(5,7),d=+s.slice(8,10);
  return y>=1850&&y<=2099&&m>=1&&m<=12&&d>=1&&d<=31;
}
function validDayMonth(s){                     // 1.1.99 — den 1–31, měsíc 1–12 (verze „2.16.1“ propadnou)
  const p=s.split(".");
  return +p[0]>=1&&+p[0]<=31&&+p[1]>=1&&+p[1]<=12;
}
// pořadí = priorita: specifické PŘED obecným, ať si nepřeberou číslice.
// Položky s `cap:1` redigují jen zachycenou skupinu — kontext (trigger) zůstává čitelný.
const MESIC="(?:led(?:na|en)|únor[ay]?|březn[a]?|březen|dub(?:na|en)|květ(?:na|en)|červ(?:na|en|enec|ence)|srp(?:na|en)|září|říj(?:na|en)|listopad[ua]?|prosin(?:ce|ec))";
const STRUCT = [
  {key:"URL",     label:"URL",            re:/\bhttps?:\/\/[^\s<>"]+/gi},
  {key:"EMAIL",   label:"email",          re:/\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b/g},
  // e-mail maskovaný proti robotům: „jan.novak(at)seznam.cz", „jan [at] seznam.cz", „zavináč"
  {key:"EMAIL",   label:"email",          re:/\b[\w.+-]+\s?(?:\(at\)|\[at\]|\{at\}|\s(?:at|zavináč)\s)\s?[\w-]+(?:\.|\s?\(dot\)\s?|\s?\[dot\]\s?)[\w.-]{2,}\b/giu},
  // IPv4 (oktety 0–255); ne za slovem verze/build („build 1.2.34.5")
  {key:"IP",      label:"IP adresa",      re:/(?<![\d.])(?<!(?:[Vv]erz\p{L}*|[Vv]ersion|[Bb]uild|[Rr]elease|[Vv]er\.|\bv)\s?)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])/gu},
  {key:"TOKEN",   label:"API token",      re:/\b(?:sk-[A-Za-z0-9-]{20,}|github_pat_[A-Za-z0-9_]{60,}|ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b/g},
  // KRYPTO bez Base58Check (review #12, vědomě): checksum = 2× SHA-256, v prohlížeči
  // jen async SubtleCrypto — validátory jsou sync. Náhodný 26+znakový token jako FP ≠ leak.
  {key:"KRYPTO",  label:"krypto adresa",  re:/\b(?:0x[a-fA-F0-9]{40}|bc1[a-z0-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b/g},
  // ulice: a) koncovka+číslo  b) kontext (bytem/sídlem)+víceslovný název+číslo
  {key:"ULICE",   label:"ulice",          re:/\p{Lu}[\p{Ll}]+(?:ská|cká|ova|ého|ního|í)\s+\d{1,4}(?:\/\d{1,4})?/gu},
  {key:"ULICE",   label:"ulice",  cap:1,  re:/(?:bytem|se\s+sídlem|sídlem|trvale\s+bytem|adres\p{L}+|bydliště|ulice|ul\.)[:\s]+((?:nám(?:ěstí|\.)\s+|třída\s+|tř\.\s+|nábřeží\s+)?\p{Lu}[\p{L}]*(?:\s+(?:nám\.|náměstí|[\p{Lu}\p{Ll}.]+)){0,2}\s+\d{1,4}(?:\/\d{1,4})?[a-z]?)(?![\d])/gu},
  // náměstí / třída / nábřeží kdekoli („náměstí Míru 5", „třída Kpt. Jaroše 12")
  {key:"ULICE",   label:"ulice",          re:/(?:[Nn]ám(?:ěstí|\.)|[Tt]řída|[Tt]ř\.|[Nn]ábřeží)\s+\p{Lu}[\p{L}.]*(?:\s+\p{Lu}[\p{L}.]*){0,2}\s+\d{1,4}(?:\/\d{1,4})?[a-z]?(?![\d])/gu},
  // DIČ PŘED IBAN (oba CZ+číslice; \b…\b zabrání kolizi na délce)
  {key:"DIC",     label:"DIČ",            re:/\b(?:CZ|SK|DE|AT|PL)\d{8,11}\b/g},
  {key:"IBAN",    label:"IBAN",           re:/\b[A-Za-z]{2}\d{2}(?:\s?[A-Za-z0-9]{4}){2,7}\b/g, valid:validIBAN},
  {key:"VIN",     label:"VIN",            re:/\b[A-HJ-NPR-Z0-9]{17}\b/g},
  {key:"KARTA",   label:"platební karta", re:/\b(?:\d{4}[ -]){3}\d{4}\b/g},
  {key:"KARTA",   label:"platební karta", re:/\b\d{16}\b/g, valid:luhn},          // bez separátorů (Luhn)
  {key:"RC",      label:"rodné číslo",  cap:1, re:/(?:RČ|rodné\s+číslo|r\.\s*č\.|číslo\s+pojištěnce|č\.\s*pojištěnce)[:\s]{0,3}(\d{6}\s?\/?\s?\d{3,4})(?!\d)/giu},
  {key:"RC",      label:"rodné číslo",    re:/\b\d{6}\/\d{3,4}\b/g},
  {key:"RC",      label:"rodné číslo",    re:/\b\d{10}\b/g, valid:validRC},        // bez lomítka (datum+mod11)
  {key:"SPZN",    label:"spisová značka", re:/\b\d{1,3}\s?[A-Z][A-Za-z]{0,3}\s?\d{1,4}\/\d{4}(?:-\d{1,4})?\b/g},
  // ID datové schránky: kontext „schránk…“ + 7znakový alfanum. token (musí mít číslici)
  {key:"DSCHRANKA",label:"datová schránka",cap:1, re:/[Ss]chránk\p{L}*[\s\S]{0,50}?\b((?=[a-z0-9]*\d)[a-z0-9]{7})\b/gu},
  // kontextová oborová čísla (smlouva/pojistka/škodní/jednací/VS/SS/osobní č./ID/ev.č.)
  // (?<![A-Z\d]) před číslicí: capture nesmí ukrást číslici z dřívějšího placeholderu
  // („sp. zn. SPZN1“ → bral „1“ → SPZNDOKID1) — placeholdery jsou VELKÁ písmena+číslo
  {key:"DOKID",   label:"číslo dokumentu",cap:1, re:/(?:(?<![\p{L}])(?:VS|KS|SS)(?=[:\s])|(?:[Ss]mlouv\p{L}*|[Ff]aktur\p{L}*|[Oo]bjednávk\p{L}*|[Pp]ojistk\p{L}*|[Pp]ojistn\p{L}*\s+smlouv\p{L}*)\s+(?:č\.|čísl\p{L}*)|[Vv]ariabiln\p{L}*\s+symbol|[Ss]pecifick\p{L}*\s+symbol|[Čč]ísl\p{L}*\s+(?:smlouvy|pojistky|pojistné\s+smlouvy|škodní\s+události|jednací|zákaznick\p{L}*|profilu|žáka)|[Čč]\.\s*j\.|[Ss]p\.\s*zn\.|[Ss]pisov\p{L}*\s+značk\p{L}*|[Oo]sobní\s+čísl\p{L}*|ID\s+žáka|[Ee]viden\p{L}*\s+čísl\p{L}*|[Ee]v\.\s*č\.)[^\d\n]{0,25}?((?:[A-Z]{1,5}[ \/-])?(?<![A-Z\d])\d[\dA-Za-z]*(?:[\/-][\dA-Za-z]+){0,3})/gu},
  {key:"PAS",     label:"číslo pasu",     cap:1, re:/(?:číslo\s+pasu|cestovní\p{L}*\s+pas\p{L}*|pas\s+č\.)[^\d\n]{0,15}?([A-Z]{0,2}\d{7,9})(?!\d)/giu},
  {key:"RP",      label:"řidičský průkaz",cap:1, re:/(?:řidičsk\p{L}*\s+průkaz\p{L}*|řidičák\p{L}*|ŘP)[^\dA-Z\n]{0,15}?([A-Z]{2}\s?\d{6})(?!\d)/gu},
  {key:"ICP",     label:"IČP/IČZ",        cap:1, re:/(?<![\p{L}])(?:IČP|IČZ)[:\s]{1,3}(\d{8})(?!\d)/gu},
  // číslo OP (9 číslic) v kontextu — PŘED telefonem
  {key:"COP",     label:"číslo OP",       cap:1, re:/(?:občansk\p{L}*\s+průkaz\p{L}*|čísl\p{L}*\s+OP|OP\s+č\.|č\.\s*OP)[^\d\n]{0,20}?(\d{9})\b/gu},
  // číslo účtu: pomlčková forma NEBO v kontextu „účet/účtu“ (zúženo, ať nebere č.j./roky)
  {key:"UCET",    label:"číslo účtu",     re:/\b\d{1,6}-\d{2,10}\/\d{4}\b/g},
  {key:"UCET",    label:"číslo účtu",     cap:1, re:/(?:[Úú]č\p{L}+|č\.\s*ú\.)[^\d\n]{0,12}?((?:\d{1,6}-)?\d{2,10}\/\d{4})\b/gu},
  {key:"SSN",     label:"US SSN",         re:/\b\d{3}-\d{2}-\d{4}\b/g},
  // částka: číslo + měna („85 000 Kč", „1 200,50 EUR", „25 tis. Kč", „15.000,- Kč") nebo měna před číslem („€ 1 200", „$350").
  // PŘED telefonem/PSČ/IČO, ať si číslice částky nepřeberou. Částka sama osobní údaj být nemusí,
  // ale u dlužníka/pacienta ho prozradí (výše dluhu, mzdy, odškodnění) → redigujeme.
  {key:"CASTKA",  label:"částka",         re:/(?<![\d.,])\d+(?:[  .]\d{3})*(?:,\d{1,2}|,-)?(?:\s?(?:mil\.?|tis\.?|milion\p{L}*|tisíc\p{L}*))?\s?(?:[Kk][čČcC]|CZK|czk|EUR|eur|USD|GBP|€|\$|korun\p{L}*(?:\s+česk\p{L}*)?|eur\p{L}*)(?![\p{L}\d])|(?:€|\$|EUR|CZK|USD|[Kk][čČ])\s?\d+(?:[ ,. ]\d{3})*(?:[.,]\d{1,2}|,-)?(?![\d])/gu},
  // částka slovy („slovy: osmdesát tisíc korun českých") — běžné ve smlouvách
  {key:"CASTKA",  label:"částka",  cap:1, re:/slovy[:\s]+((?:\p{L}+[\s-]){0,8}?\p{L}*\s?(?:korun\p{L}*|Kč|eur\p{L}*)(?:\s+česk\p{L}*)?)/gu},
  // částka bez měny, ale za slovem, které peníze jednoznačně ohlašuje („ve výši 80 000", „jistina 120 000")
  {key:"CASTKA",  label:"částka",  cap:1, re:/(?:ve\s+výši|částk\p{L}*|cen[aěuy]\b|úhrad\p{L}*|dluh\p{L}*|jistin\p{L}*|pokut\p{L}*|odměn\p{L}*|mzd\p{L}*|nájemn\p{L}*|záloh\p{L}*|doplat\p{L}*|odškodn\p{L}*|náhrad\p{L}*\s+škody)(?:\s+(?:činí|ve\s+výši|celkem|ve\s+výši))?[\s:]{1,3}((?:\d{1,3}(?:[  .]\d{3})+|\d{3,})(?:,\d{1,2}|,-)?)(?![\d\/.])/gu},
  // telefon: a) s předvolbou +420/+421 — jistota, bereme libovolné členění 9 číslic
  //          b) bez předvolby — jen reálné CZ prefixy 2–7 (pevné linky+mobily; částky
  //             „123 456 789“ začínají 1 → propadnou) + stopka na měnu/jednotky/delší čísla
  {key:"TELEFON", label:"telefon",        re:/(?:\+|00\s?)42[01](?:[\s.-]?\d){9}\b/g},
  {key:"TELEFON", label:"telefon",        re:/(?<!\d[\s.-])\b[2-7]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}\b(?![\s.-]?\d)(?!\s?(?:Kč|CZK|EUR|USD|€|%|,-|mil|tis))/g},
  // SPZ: přesný moderní formát číslice+písmeno+alfanum + 4 číslice („3T9 4567“) —
  // dřívější volný vzor bral i „výrobek 3T 9999“; malá písmena tolerujeme (leak > FP)
  {key:"SPZ",     label:"SPZ",            re:/\b\d[A-Za-z][A-Za-z0-9]\s?\d{4}\b/g},
  // datum: číselné + slovní měsíc („2. září 1954“) + ISO + dvouciferný rok (validované)
  {key:"DATUM",   label:"datum",          re:new RegExp("\\b\\d{1,2}\\.\\s?\\d{1,2}\\.\\s?\\d{4}\\b|\\b\\d{1,2}\\.\\s?"+MESIC+"\\s+\\d{4}\\b","giu")},
  {key:"DATUM",   label:"datum",          re:/\b\d{4}-\d{2}-\d{2}\b/g, valid:validISODate},
  {key:"DATUM",   label:"datum",          re:/\b(?:0?[1-9]|[12]\d|3[01])\/(?:0?[1-9]|1[0-2])\/(?:19|20)\d{2}\b/g},
  {key:"DATUM",   label:"datum",          re:/\b\d{1,2}\.\s?\d{1,2}\.\s?\d{2}\b(?!\.?\d)/g, valid:validDayMonth},
  // MKN/ICD-10: dekadická forma (E11.9) bez kontextu + nedekadická (I10) v kontextu diagnózy
  {key:"MKN",     label:"diagnóza (MKN)", re:/\b[A-TV-Z]\d{2}\.\d{1,2}\b/g},
  {key:"MKN",     label:"diagnóza (MKN)", cap:1, re:/(?:dg\.|diagnóz\p{L}*|MKN(?:-?10)?|kód\p{L}*\s+diagnóz\p{L}*|onemocněn\p{L}*|chorob\p{L}*|posudk\p{L}*)[\s\S]{0,30}?\b([A-TV-Z]\d{2})\b/gu},
  // PSČ: a) kontext „PSČ“ — bere i kompaktní tvar (74221)  b) holý tvar s mezerou,
  //      ale NE před měnou/jednotkou („250 00 Kč“, „150 96 kusů“) a ne uvnitř delšího čísla
  {key:"PSC",     label:"PSČ",    cap:1,  re:/PSČ[\s:]{0,3}(\d{3}\s?\d{2})\b/g},
  {key:"PSC",     label:"PSČ",            re:/(?<!\d\s)\b\d{3}\s\d{2}\b(?![\s.,-]?\d)(?!\s?(?:Kč|CZK|EUR|USD|€|%|,-|[Kk]s\b|kus|km\b|kg\b|mil\b|tis\b|hod\b|let\b|m[²2]?\b|l\b|g\b))/gu},
  {key:"PSC",     label:"PSČ",            re:/(?<![\d\/.,-])\b[1-7]\d{4}(?=\s+\p{Lu}\p{Ll}+)/gu},
  {key:"ICO",     label:"IČO",            re:/\b\d{8}\b/g, valid:validICO},        // mod-11 (ceny/kódy bez platné kontrolní číslice propadnou)
];

// placeholdery jsou VELKÝMI písmeny + číslo (OSOBA1) → názvové/strukturní
// regexy je znovu nematchnou, takže žádné sentinely nejsou potřeba.
function anonymize(text,nerEnts){
  const reps=[]; const counters={}; const registry=new Map();
  function assign(orig,key,label){
    const k=key+"::"+orig.toLowerCase().replace(/\s+/g," ").trim();
    if(registry.has(k)) return registry.get(k);
    counters[key]=(counters[key]||0)+1;
    const plc=key+counters[key];
    registry.set(k,plc);
    reps.push({original:orig.trim(),placeholder:plc,type:key,label});
    return plc;
  }
  let out=text;
  // STRUCT: u položek s `cap` redigujeme jen zachycenou hodnotu (kontext zůstává).
  for(const item of STRUCT) out=out.replace(item.re,(m,...g)=>{
    const val=item.cap?g[item.cap-1]:m;
    if(val==null||val==="") return m;
    if(item.valid&&!item.valid(val)) return m;
    const plc=assign(val,item.key,item.label);
    return item.cap? m.replace(val,plc): plc;
  });
  // NER entity z NameTagu (reálná jména/firmy/města) — delší texty dřív
  if(nerEnts&&nerEnts.length){
    const uq=[...new Map(nerEnts.map(e=>[e.text,e])).values()].sort((a,b)=>b.text.length-a.text.length);
    // hranice (?<!písmeno/číslice)…(?!…) — krátká entita („C“) jinak přepisovala
    // vnitřek už vložených placeholderů (RC1→ROSOBA21) i podřetězce slov (Eva→Evakuace)
    for(const e of uq){const x=e.text.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");out=out.replace(new RegExp("(?<![\\p{L}\\p{N}])"+x+"(?![\\p{L}\\p{N}])","gu"),m=>assign(m,e.key,e.label));}
  }
  // po NER: číslo popisné/orientační hned za placeholderem místa/ulice — ulici NER
  // nahradil, ale číslo domu zůstalo ("MESTO1 1428/9" → "MESTO1 CP1").
  out=out.replace(/((?:MESTO|ULICE)\d+\s+)(\d{1,4}\/\d{1,3})\b/g,(m,pre,num)=>pre+assign(num,"CP","č. popisné"));
  // jména: křestní ze slovníku (i samostatné) NEBO dvojice Velkých slov, kde
  // druhé končí typickou českou příponou příjmení (chytá i skloňované formy
  // jako "Marii Svobodové", které slovník neobsahuje).
  // Jména přes Unicode property escapes (\p{Lu}/\p{Ll} + /u) — řeší diakritiku,
  // kterou JS \b a [a-z] třídy nezvládají. NOTNAME = přídavná jména se stejnou
  // koncovkou jako příjmení (rodné/krajské…), která NEanonymizujeme.
  const NOTNAME=new Set(["rodné","rodného","krajské","krajský","krajského","krajská","krajskému","krajském",
    "městský","městské","městská","městského","okresní","okresního","obvodní","vrchní","vrchního","nejvyšší",
    "ústavní","ústavního","trestní","trestního","občanské","občanský","občanská","občanského","finanční","finančního",
    "sociální","materiální","dobré","dobrý","dobrého","nové","nový","nového","nová","velké","velký","velká",
    "český","česká","české","českého","slovenské","slovenský","slovenská","právní","právního","soudní","soudního",
    "veřejné","veřejný","malá","malé","malý","celá","celé","dlouhá","krásná","správní","daňové","daňový",
    "evropské","evropský","hlavní","hlavního","bytové","bytový","smluvní","kupní","nájemní","příslušné","příslušný",
    "uvedené","uvedený","oprávněná","oprávněný","povinná","povinný","žalovaná","žalovaný","navrhovaná",
    "severní","jižní","východní","západní","střední","státní","mezinárodní","generální","obchodní",
    "výrobní","provozní","technická","technický","technické","průmyslová","průmyslový","průmyslové",
    "komerční","automobilová","automobilový","automobilové","mladá","mladé","mladý","lidové","lidová",
    "lidový","základní","mateřská","mateřské","vysoká","vysoké","odborná","odborné","pracovní","osobní",
    "rodinná","rodinné","měsíční","roční","denní","týdenní","celková","celkový","celkové","poslední",
    "národní","národního","výroční","aktuální","původní","spisová","spisové","jednací","závěrečná","závěrečné",
    "dovolená","dovolené","nemocenská","mzdová","mzdové","platná","platné","písemná","písemné","ústní",
    "veškerá","veškeré","veškerý"]);
  // A) křestní ze slovníku + až 2 následující Velká slova (chytá příjmení i bez
  //    jasné přípony: "Petr Svoboda", "Barbora Vidová Hladká")
  // velké počáteční písmeno přímo v alternaci ([Tt]omáš) → NEpoužíváme /i flag,
  // protože /i ruší rozlišení case u \p{Lu}/\p{Ll} a trailing grabber by chytal i malá slova.
  const NAMEALT=[...FIRST_NAMES].sort((a,b)=>b.length-a.length)
    .map(n=>"["+n[0].toUpperCase()+n[0]+"]"+n.slice(1)).join("|");
  // typické přípony příjmení vč. skloňovaných pádů — sdílí pas A (ořez) i pas B (anchor).
  // pozn.: třídy sk/ck/n BEZ „o“ a „u“ — jinak braly země a města („Německo“,
  // „Rakousku“, „Řecko“, „Brno“, „Lipno“) jako příjmení; příjmení na -sko/-cko/-no neexistují
  const SUF="(?:ov(?:[áéýaěy]|ou|i)|sk(?:[áéýaě]|ou|ého|ému|ém)|ck(?:[áéýa]|ou)|[čďňřšťž]?n(?:[áéýaěií]|ého|ou)|[áí]k(?:[aeuyů]|em|ovi)?|ek(?:[aeu]|em|ovi)?|ič(?:e|ovi)?|[ktlrds]á)";
  const SUR_END=new RegExp("^\\p{Lu}[\\p{Ll}]*"+SUF+"$","u");
  // koncová hranice (?![\p{L}]) + volitelná česká skloňovací koncovka → chytí
  // i skloňovaná jména ("Tomáše", "Václavu", "Romana") jako CELÉ slovo, ne kmen.
  const DICT_RE=new RegExp("(?<![\\p{L}])(?:"+NAMEALT+")(?:ovi|em|e|a|u|y|i|ě)?(?![\\p{L}])(?:\\s+\\p{Lu}[\\p{Ll}]+){0,2}","gu");
  // trailing grabber ořezává zprava (review #9): slovo za jménem, které je adjektivum/
  // město, nepatří do jména ("Petr Veškeré Náležitosti"); 2. slovo za jménem bereme
  // jen s příjmenní koncovkou ("Barbora Vidová Hladká" ano, ale "Jan Novák Veškeré" ne).
  const ROLE=new Set(["žalobce","žalobkyně","žalovaný","žalovaná","pan","paní","pacient","pacientka","kupující","prodávající","účastník","účastnice","svědek","svědkyně","obviněný","obviněná","dlužník","dlužnice","věřitel","věřitelka","zaměstnanec","zaměstnankyně","nájemce","pronajímatel","jméno","příjmení","dne","podepsal","podepsala","zástupce","advokát","advokátka","soudce","soudkyně","lékař","lékařka","ošetřující","student","studentka","žák","žákyně","klient","klientka"]);
  const REV_RE=new RegExp("(?<![\\p{L}])(\\p{Lu}[\\p{Ll}]+)\\s+((?:"+NAMEALT+"))(?![\\p{L}])(?=\\s*,)","gu");
  out=out.replace(REV_RE,(m,sur,first)=>{const w=sur.toLowerCase();return (ROLE.has(w)||NOTNAME.has(w)||CITIES.has(w)||FIRST_NAMES.has(w))?m:assign(m,"OSOBA","osoba");});
  out=out.replace(DICT_RE,m=>{
    let kept=m,rest="";
    for(;;){
      const t=kept.match(/(\s+)(\p{Lu}[\p{Ll}]+)$/u);
      if(!t) break;
      const w=t[2].toLowerCase();
      const head=kept.slice(0,kept.length-t[1].length-t[2].length);
      const isSecondTrailing=/\s/.test(head.trim());
      if(NOTNAME.has(w)||CITIES.has(w)||(isSecondTrailing&&!SUR_END.test(t[2]))){ rest=t[1]+t[2]+rest; kept=head; }
      else break;
    }
    return assign(kept,"OSOBA","osoba")+rest;
  });
  // B) anchor na PŘÍJMENÍ (přípona vč. skloňovaných pádů) + volitelné předchozí slovo.
  //    ⚠️ JEN LOKÁLNÍ mód. V NER módu NameTag pokryje jména spolehlivěji a tahle
  //    heuristika by jinak brala adjektiva ("Komerční", "Automobilový", "Rakousko")
  //    jako příjmení → falešné poplachy / over-redakce čitelných slov.
  if(!(nerEnts&&nerEnts.length)){
    const SUR_RE=new RegExp("(?:(\\p{Lu}[\\p{Ll}]+)\\s+)?(\\p{Lu}[\\p{Ll}]*"+SUF+")(?![\\p{Ll}])","gu");
    out=out.replace(SUR_RE,function(m,pre,word){const w=word.toLowerCase();if(NOTNAME.has(w)||CITIES.has(w)) return m;
      // oslovení/role před příjmením („Pan Novák", „Žalobce Dvořák") zůstává čitelné
      if(pre&&ROLE.has(pre.toLowerCase())) return m.slice(0,m.length-word.length)+assign(word,"OSOBA","osoba");
      return assign(m,"OSOBA","osoba");});
  }
  // C) jeden průchod pro oba slovníky: samostatná křestní jména → OSOBA, města → MESTO
  out=out.replace(/\p{Lu}[\p{Ll}]+/gu,m=>{
    const w=m.toLowerCase();
    if(FIRST_NAMES.has(w)) return assign(m,"OSOBA","osoba");
    if(CITIES.has(w)) return assign(m,"MESTO","město/obec");
    return m;
  });
  return {anonymized:out,replacements:reps};
}

// ── Plný NER mód: volá ÚFAL NameTag přímo z prohlížeče (CORS:*) ──
// Browser-direct = traffic z prohlížeče uživatele (rozložené, ÚFAL-friendly).
// NEjde o zero-egress: text odchází na ÚFAL (= default cloud chování MCP).
// POST helper (timeout/abort) a parseConll žijí v ner-common.js (sdílené s toolkit.js).
// Klasifikace CNEC typu (NameTag) → naše kategorie. PREFIX-based, ne whitelist:
// NameTag dává jemné podtypy (ps=příjmení, pf=křestní, gu/gs/gr=místa, io/ic=instituce,
// td/ty=datum/rok). Dřívější whitelist {P,if,gu,gc} propadal vše ostatní → unikala
// samostatná příjmení ("Babiš"), data ("2. září 1954") i instituce (KSČ, StB).
// Pozn.: anglický model dává PER/ORG/LOC (velká písmena, neřídí se CNEC prefixem).
function nerCategory(type){
  if(!type) return null;
  if(type==="PER") return ["OSOBA","osoba"];
  if(type==="ORG") return ["INSTITUCE","instituce"];
  if(type==="LOC") return ["MESTO","místo"];
  if(type==="if") return ["FIRMA","firma"];   // if = komerční firma (zvlášť od institucí)
  const c=type[0];                             // CNEC: P/p=osoba, g=místo, i=instituce, T/t=datum
  if(c==="P"||c==="p") return ["OSOBA","osoba"];
  if(c==="g")          return ["MESTO","místo"];
  if(c==="i")          return ["INSTITUCE","instituce"];
  if(c==="T"||c==="t") return ["DATUM","datum"];
  return null;                                 // čísla (n*), média (m*), artefakty (o*) … neřešíme
}
async function fetchNER(text){
  const r=await apiPost(NER_API_BASE+"/nametag/api/recognize",{data:text,output:"conll"});
  const d=await r.json();
  const ents=[];
  for(const e of parseConll(d.result)){
    const cat=nerCategory(e.type);
    // stoplist: obecné zkratky/statusy/tituly, které NameTag chybně bere jako entitu
    if(cat && !NER_STOP.has(e.text.toLowerCase().replace(/\.$/,"").trim())) ents.push({text:e.text,key:cat[0],label:cat[1]});
  }
  return ents;
}
// ne-PII zkratky/statusy/tituly: NEanonymizovat (jinak "OSVČ"→INSTITUCE, "ČR"→MESTO, "por."→OSOBA)
const NER_STOP=new Set(["osvč","čr","sr","eu","osa","čsú","npú","por","npor","kpt","mjr","plk","gen","pprap","prap","mudr","judr","ing","mgr","bc","phdr","rndr","csc"]);

// labely drženy v souladu se STRUCT.label (review #19) — NER typy (OSOBA/FIRMA/…) navíc
const TYPE_LABELS={OSOBA:"osoba",FIRMA:"firma",INSTITUCE:"instituce",MESTO:"místo",ULICE:"ulice",CP:"č. popisné",PSC:"PSČ",TELEFON:"telefon",EMAIL:"email",
  URL:"URL",RC:"rodné číslo",ICO:"IČO",DIC:"DIČ",IBAN:"IBAN",UCET:"číslo účtu",SPZN:"spisová značka",DATUM:"datum",
  DSCHRANKA:"datová schránka",VIN:"VIN",DOKID:"číslo dokumentu",COP:"číslo OP",MKN:"diagnóza (MKN)",
  KRYPTO:"krypto adresa",TOKEN:"API token",KARTA:"platební karta",SSN:"US SSN",SPZ:"SPZ",CASTKA:"částka",IP:"IP adresa",PAS:"číslo pasu",RP:"řidičský průkaz",ICP:"IČP/IČZ"};
const PH_RE=/\b(?:OSOBA|FIRMA|INSTITUCE|MESTO|ULICE|CP|PSC|TELEFON|EMAIL|URL|RC|ICO|DIC|IBAN|UCET|SPZN|DATUM|DSCHRANKA|VIN|DOKID|COP|MKN|KRYPTO|TOKEN|KARTA|SSN|SPZ|CASTKA|IP|PAS|RP|ICP)\d+\b/g;
