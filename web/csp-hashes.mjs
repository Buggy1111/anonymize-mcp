// csp-hashes.mjs — přepočítá sha256 hashe inline <script> bloků (JSON-LD) v CSP každé stránky.
// Spusť po každé úpravě JSON-LD:  node csp-hashes.mjs
// V CSP stačí mít `script-src 'self' …` — hashe za tím skript nahradí aktuálními.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";

for (const file of ["index.html", "anonymize.html", "nastroje.html"]) {
  let html = readFileSync(file, "utf8");
  const hashes = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    .map(m => `'sha256-${createHash("sha256").update(m[1], "utf8").digest("base64")}'`);
  html = html.replace(/(script-src 'self')[^;]*;/, (_, head) => {
    const keep = file === "index.html" ? "" : " https://cdnjs.cloudflare.com"; // pdf.js + mammoth jen na stránkách s nahráním souboru
    return `${head}${keep} ${hashes.join(" ")};`;
  });
  writeFileSync(file, html);
  console.log(`${file}: ${hashes.length} inline skript(y)`);
}
