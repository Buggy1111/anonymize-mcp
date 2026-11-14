"use strict";
/* site.js — sdílené chování všech stránek: přepínač den/noc, plynulý scroll (Lenis),
   jemné odhalení bloků při scrollu ([data-reveal]). */
(function(){
  const root=document.documentElement;
  const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ── den / noc / podle systému ──
  const buttons=[...document.querySelectorAll(".theme button")];
  function setTheme(t){
    if(t==="light"||t==="dark") root.setAttribute("data-theme",t); else root.removeAttribute("data-theme");
    buttons.forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.t===t)));
    try{ localStorage.setItem("theme",t); }catch(e){}
    document.dispatchEvent(new CustomEvent("themechange"));
  }
  let saved="system"; try{ saved=localStorage.getItem("theme")||"system"; }catch(e){}
  buttons.forEach(b=>{ b.setAttribute("aria-pressed",String(b.dataset.t===saved)); b.addEventListener("click",()=>setTheme(b.dataset.t)); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change",()=>document.dispatchEvent(new CustomEvent("themechange")));

  // ── plynulý scroll ──
  if(window.Lenis && !reduce){
    try{
      const lenis=new Lenis({lerp:.085});
      window.siteLenis=lenis;
      (function raf(t){ lenis.raf(t); requestAnimationFrame(raf); })(performance.now());
    }catch(e){}
  }

  // ── odhalení při scrollu: obsah je vidět i bez JS, animace jen přidává pohyb ──
  const items=document.querySelectorAll("[data-reveal]");
  if(!reduce && "IntersectionObserver" in window && items.length){
    const io=new IntersectionObserver(es=>es.forEach(en=>{
      if(!en.isIntersecting) return;
      const el=en.target, i=+(el.dataset.reveal||0);
      el.animate([{opacity:0,transform:"translateY(36px)"},{opacity:1,transform:"none"}],
        {duration:1100,delay:i*80,easing:"cubic-bezier(.16,1,.3,1)",fill:"backwards"});
      io.unobserve(el);
    }),{threshold:.15});
    items.forEach(el=>{ const r=el.getBoundingClientRect(); if(r.top>innerHeight) io.observe(el); });
  }
})();
