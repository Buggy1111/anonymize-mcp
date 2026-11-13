"use strict";
/* theme.js — načíst synchronně v <head>: nastaví den/noc dřív, než se stránka vykreslí (bez probliknutí). */
try{ const t=localStorage.getItem("theme"); if(t==="light"||t==="dark") document.documentElement.setAttribute("data-theme",t); }catch(e){}
