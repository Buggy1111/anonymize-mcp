// engine.test.cjs — testy webového enginu (díry i over-redakce). Spuštění: node web/tests/engine.test.cjs (audit bod 5, review #1–4 + #17).
// Deterministické: lokální mód + simulované NER entity (žádné živé API).
const fs=require('fs'),path=require('path'),os=require('os');
const NERC=path.join(__dirname,'..','js','ner-common.js');
const ENGINE=path.join(__dirname,'..','js','anonymize-engine.js');
const tmp=path.join(os.tmpdir(),'anon-engine-test-'+process.pid+'.cjs');
fs.writeFileSync(tmp, fs.readFileSync(NERC,'utf8')+'\n'+fs.readFileSync(ENGINE,'utf8')+'\nmodule.exports={anonymize,validRC,validICO,luhn,validIBAN};\n');
const {anonymize,validRC,validICO}=require(tmp);

let pass=0,fail=0;
function t(name,cond,detail){ if(cond){pass++;console.log("  ok  "+name);} else {fail++;console.log("  FAIL "+name+(detail?" — "+detail:""));} }
function anon(text,ents){ return anonymize(text,ents||null); }
function redacted(text,key,ents){ const r=anon(text,ents); return r.replacements.some(x=>x.type===key); }
function untouched(text,ents){ const r=anon(text,ents); return r.anonymized===text; }

console.log("#1 IČO — mod-11 validace");
t("reálné IČO 26168685 (Seznam) → ICO", redacted("Dodavatel IČO 26168685 dodá zboží.","ICO"));
t("reálné IČO 45274649 (ČEZ) → ICO", redacted("subjekt 45274649 v rejstříku","ICO"));
t("reálné IČO 00216208 (UK, vedoucí nuly) → ICO", redacted("škola 00216208 sídlí tam","ICO"));
t("cena 12345678 (neplatná kontrolní) zůstává", untouched("celkem 12345678 položek"));
t("kód 10000000 zůstává", untouched("objednávka 10000000 vyřízena"));

console.log("#2 PSČ — kontext/jednotky");
t("'150 96 kusů' zůstává", untouched("dodáno 150 96 kusů zboží"));
t("'250 00 Kč' není PSČ (je to částka)", !redacted("cena 250 00 Kč celkem","PSC")&&redacted("cena 250 00 Kč celkem","CASTKA"));
t("'742 21 Studénka' → PSC", redacted("bytem 742 21 Studénka","PSC"));
t("'110 00 Praha' → PSC", redacted("adresa 110 00 Praha","PSC"));
t("kompaktní 'PSČ 74221' → PSC", redacted("uvedl PSČ 74221 do formuláře","PSC"));
t("kompaktní 74221 BEZ kontextu zůstává", untouched("kód zboží 74221 skladem"));

console.log("#3 telefon — prefixy/částky");
t("'603 123 456' → TELEFON", redacted("volejte 603 123 456 večer","TELEFON"));
t("'+420 60 123 45 67' (nestandardní členění) → TELEFON", redacted("tel. +420 60 123 45 67 přes den","TELEFON"));
t("'123 456 789 Kč' není telefon (je to částka)", !redacted("škoda 123 456 789 Kč byla","TELEFON")&&redacted("škoda 123 456 789 Kč byla","CASTKA"));
t("'100 200 300' zůstává", untouched("řady 100 200 300 vyrobeny"));
t("'777 888 999 Kč' není telefon (je to částka)", !redacted("výhra 777 888 999 Kč padla","TELEFON")&&redacted("výhra 777 888 999 Kč padla","CASTKA"));
t("'234 567 890 123' zůstává (delší číslo)", untouched("kód 234 567 890 123 zadán"));

console.log("#4 SUR_RE — adjektiva a země (lokální mód)");
t("'Německo' zůstává", untouched("Vyvážíme do Německo i jinam"));
t("'Rakousku' zůstává", untouched("Pobočka v Rakousku funguje"));
t("'Řecko' zůstává", untouched("Dovolená v Řecko se vydařila"));
t("'Lipno' zůstává", untouched("Jezero Lipno je hezké"));
t("'Severní Morava' zůstává", untouched("Region Severní Morava prosperuje"));
t("'Mladá Boleslav' zůstává", untouched("Závod Mladá Boleslav vyrábí"));
t("'Národní třída' zůstává", untouched("Stanice Národní třída byla"));
t("'Komerční banka'→'Komerční' zůstává", anon("Účet u Komerční banky veden").anonymized.includes("Komerční"));
t("'Marii Svobodové' → OSOBA (regrese pas B)", redacted("Předáno Marii Svobodové osobně","OSOBA"));
t("'Janu Hradeckou' → OSOBA (ck+ou)", redacted("Zastupuje Janu Hradeckou advokát","OSOBA"));

console.log("#17 NER náhrady — hranice, idempotence placeholderů");
{
  const ents=[{text:"C",key:"OSOBA",label:"osoba"}];
  const r=anon("Rodné číslo 800101/1234 patří svědkovi C a nikomu jinému.",ents);
  t("placeholder RC1 přežil NER náhradu jednopísmenné entity", /\bRC1\b/.test(r.anonymized), r.anonymized);
  t("samostatné 'C' → OSOBA", /\bOSOBA\d+\b/.test(r.anonymized), r.anonymized);
}
{
  const r=anon("Eva řídila evakuaci. Evakuace s Eva souvisí jen jménem.",[{text:"Eva",key:"OSOBA",label:"osoba"}]);
  t("'Eva' nahrazena, 'evakuace/Evakuace' nedotčeny", !/Eva\b/.test(r.anonymized)&&/[Ee]vakuac/.test(r.anonymized), r.anonymized);
}

console.log("Regrese — dřívější opravy (1.6.)");
t("RČ s lomítkem 800101/1234 → RC", redacted("RČ 800101/1234 uvedeno","RC"));
{ // RČ bez lomítka: najdi platnou variantu validátorem a ověř redakci
  let rc=null; for(let i=0;i<10;i++){const c="800101123"+i; if(validRC(c)){rc=c;break;}}
  t("RČ bez lomítka (validní "+rc+") → RC", rc&&redacted("osoba "+rc+" žádá",rc?"RC":""));
}
t("karta 4111111111111111 (Luhn) → KARTA", redacted("kartou 4111111111111111 placeno","KARTA"));
t("náhodných 16 číslic zůstává", untouched("kód 1234567890123456 zadán"));
t("IBAN CZ6508000000192000145399 → IBAN", redacted("účet CZ6508000000192000145399 veden","IBAN"));
t("email → EMAIL", redacted("piš na jan.novak@example.cz hned","EMAIL"));
t("'+420 603 123 456' → TELEFON", redacted("tel +420 603 123 456 doma","TELEFON"));
t("datum '2. září 1954' → DATUM", redacted("narozen 2. září 1954 v Praze","DATUM"));
t("validICO sanity: 26168685 ✓ / 26168684 ✗", validICO("26168685")&&!validICO("26168684"));

console.log("Tech dluh — #9 trailing grabber");
{
  const r=anon("Klient Petr Veškeré Náležitosti doložil včas.");
  t("'Petr Veškeré Náležitosti' → redigován jen Petr", /OSOBA\d+ Veškeré Náležitosti/.test(r.anonymized), r.anonymized);
}
t("'Petr Svoboda' → OSOBA celé", anon("Přišel Petr Svoboda domů.").replacements.some(x=>x.original==="Petr Svoboda"));
t("'Barbora Vidová Hladká' → OSOBA celé (2. příjmení s koncovkou)", anon("Soudkyně Barbora Vidová Hladká rozhodla.").replacements.some(x=>x.original==="Barbora Vidová Hladká"));
{
  const r=anon("Bydlí tam Pavel Praha rád.");
  t("'Pavel Praha' → OSOBA jen Pavel, Praha → MESTO", r.replacements.some(x=>x.original==="Pavel"&&x.type==="OSOBA")&&r.replacements.some(x=>x.original==="Praha"&&x.type==="MESTO"), r.anonymized);
}

console.log("Tech dluh — #11 SPZ formát");
t("'3T9 4567' → SPZ", redacted("vozidlo 3T9 4567 parkovalo","SPZ"));
t("'1AB 1234' → SPZ", redacted("vůz 1AB 1234 odjel","SPZ"));
t("'3t9 4567' (malá písmena) → SPZ", redacted("spz 3t9 4567 nafocena","SPZ"));
t("'výrobek 3T 9999' zůstává", untouched("výrobek 3T 9999 skladem"));

console.log("Tech dluh — #15 datum ISO + dvouciferný rok");
t("ISO '2020-01-05' → DATUM", redacted("dne 2020-01-05 podáno","DATUM"));
t("'1234-56-78' (nesmyslný měsíc) zůstává", untouched("kód 1234-56-78 zadán"));
t("'1.1.99' → DATUM", redacted("narozen 1.1.99 v lednu","DATUM"));
t("verze '2.16.1' zůstává", untouched("verze 2.16.1 vydána"));
t("verze '1.2.34.5' zůstává", untouched("build 1.2.34.5 nasazen"));

console.log("Tech dluh — #16 MKN kontext, #19 sloučený pas C");
t("'onemocnění ... I10' → MKN", redacted("onemocnění klasifikováno I10 trvale","MKN"));
t("'vitamin B12' zůstává", untouched("užívá vitamin B12 denně"));
t("samostatné 'Tomáš' → OSOBA (pas C)", redacted("Přišel Tomáš domů.","OSOBA"));
t("samostatné 'Ostrava' → MESTO (pas C)", redacted("Město Ostrava požádalo.","MESTO"));

console.log("Nové bugy z dema (10.6. večer)");
{
  const r=anon("Spis sp. zn. 25 C 145/2026 byl založen.");
  t("'sp. zn. 25 C 145/2026' → SPZN1 bez DOKID manglingu", /sp\. zn\. SPZN1\b/.test(r.anonymized)&&!/SPZNDOKID/.test(r.anonymized), r.anonymized);
}
t("DOKID stále funguje: 'ev. č. AB-2024-001'", redacted("doklad ev. č. AB-2024-001 přiložen","DOKID"));
t("DOKID: 'variabilní symbol 123456'", redacted("platba variabilní symbol 123456 přijata","DOKID"));
t("'Účet 1234567890/0800' (velké Ú) → UCET", redacted("Účet 1234567890/0800 veden u banky","UCET"));
t("demo IČO 12345679 je checksum-validní", validICO("12345679"));
t("demo IČO 87654326 je checksum-validní", validICO("87654326"));

console.log("Částky (CASTKA) — 14. 11. 2026");
{
  const one=(txt,exp)=>{const r=anon(txt);const c=r.replacements.filter(x=>x.type==="CASTKA").map(x=>x.original);t(`'${exp}' → CASTKA`,c.includes(exp),JSON.stringify(c)+" | "+r.anonymized);};
  one("se domáhá zaplacení 85 000 Kč na účet","85 000 Kč");
  one("dluh 1 250,50 Kč vznikl","1 250,50 Kč");
  one("nájem 15.000,- Kč měsíčně","15.000,- Kč");
  one("odškodné 25 tis. Kč","25 tis. Kč");
  one("pokuta 2 mil. Kč","2 mil. Kč");
  one("faktura na 300 EUR","300 EUR");
  one("cena € 1 200 včetně DPH","€ 1 200");
  one("platba $350 kartou","$350");
  one("mzda 42 000 korun hrubého","42 000 korun");
  one("zaplatit 80 000 kč","80 000 kč");
  one("zaplatit 80 000 KČ","80 000 KČ");
  one("zaplatit 80 000 kc","80 000 kc");
  one("zaplatit Kč 80 000","Kč 80 000");
  one("zaplatit 80 000 korun českých","80 000 korun českých");
  one("dluh ve výši 80 000 vznikl","80 000");
  one("jistina 120 000 a úrok","120 000");
  one("částka 80 000 (slovy osmdesát tisíc korun českých)","osmdesát tisíc korun českých");
  t("'dodáno 150 kusů' zůstává (bez měny)", untouched("dodáno 150 kusů zboží"));
  t("'cena za kus' bez čísla zůstává", untouched("cena za kus se dohodne"));
  t("'náhrada škody' s datem není částka", !redacted("náhrada škody ze dne 3.2.2026 se řeší","CASTKA"));
  t("'ve výši 12. 3. 1978' není částka", !redacted("narozen ve výši 12. 3. 1978","CASTKA"));
  t("'rok 2026' zůstává", untouched("v roce 2026 se nic nestalo"));
  { const r=anon("Částka 85 000 Kč a znovu 85 000 Kč."); t("stejná částka = stejný placeholder", (r.anonymized.match(/CASTKA1/g)||[]).length===2, r.anonymized); }
  { const r=anon("Žalobce Jan Novák, nar. 12. 3. 1978, tel. +420 603 123 456, 85 000 Kč na účet CZ65 0800 0000 1920 0014 5399.");
    t("demo věta: telefon, IBAN i částka zvlášť", ["TELEFON","IBAN","CASTKA","DATUM"].every(k=>r.replacements.some(x=>x.type===k)), r.anonymized); }
}

console.log("Díry z 14. 11. 2026 (sonda 50 formátů)");
{
  const hid=(txt,s)=>{const r=anon(txt);t(`'${txt}' skryje '${s}'`,!r.anonymized.includes(s),r.anonymized);};
  hid("RČ: 8003151234 bez lomítka","8003151234"); hid("r. č. 800315 / 1234","800315"); hid("číslo pojištěnce 8003151234","8003151234");
  hid("tel. 00420 603 123 456","603 123 456"); hid("piste na jan.novak(at)seznam.cz","jan.novak");
  hid("č. ú. 2400123456/2010","2400123456/2010"); hid("datum narození 01/01/1980","01/01/1980");
  hid("číslo pasu 45678912","45678912"); hid("řidičský průkaz EF123456","EF123456"); hid("IČP 12345678 lékaře","12345678");
  hid("sídlem náměstí Míru 5, Brno","Míru 5"); hid("bytem U Lesa 3, Kladno","U Lesa 3"); hid("11000 Praha 1","11000");
  hid("IP adresa 192.168.1.15","192.168.1.15"); hid("č. j. 12 Co 345/2025-67","345/2025"); hid("VS 1234567890","1234567890");
  hid("smlouva č. 2024/0123","2024/0123"); hid("Svoboda Petr, nar. 1980","Svoboda");
  { const r=anon("Pan Novák, bytem"); t("'Pan' před příjmením zůstává", r.anonymized.startsWith("Pan OSOBA"), r.anonymized); }
  t("'verze 2.16.1' zůstává", untouched("verze 2.16.1 vyšla"));
  t("'Smlouva o dílo' zůstává", untouched("Smlouva o dílo byla podepsána"));
  t("'ve 12345 případech' zůstává", untouched("ve 12345 případech"));
}

try{fs.unlinkSync(tmp);}catch(_){}
console.log("\n"+pass+" passed, "+fail+" failed");
process.exit(fail?1:0);
