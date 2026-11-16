export type DisplayLayout = "auto" | "mobile" | "desktop";
export const DISPLAY_KEY = "crypto-terminal.display-layout";
export function readDisplayLayout(): DisplayLayout {
 try { const v=localStorage.getItem(DISPLAY_KEY); if(v==="mobile"||v==="desktop")return v; } catch { /* Session fallback. */ }
 return "auto";
}
export function displayMetrics(mode:DisplayLayout, width:number, height:number, screenWidth:number, outerWidth:number, touch:boolean) {
 const actualWidth=Math.min(...[width,screenWidth,outerWidth].filter(n=>Number.isFinite(n)&&n>0));
 const mobile=mode==="mobile"||(mode==="auto"&&(width<=760||(touch&&(Math.min(actualWidth,height)<=600||(height/width>=1.6&&width<=1100)))));
 // Compensate a wide layout viewport on a small portrait touch device only.
 // Desktop/manual zoom and normal landscape are left unchanged.
 const target=actualWidth<=600?actualWidth:480;
 const zoom=mobile&&height>width&&width>760?Math.min(3,Math.max(1,width/target)):1;
 return {mobile,zoom};
}
export function applyDisplayLayout(mode:DisplayLayout) {
 const m=displayMetrics(mode,window.innerWidth,window.innerHeight,window.screen.width,window.outerWidth,navigator.maxTouchPoints>0);
 document.documentElement.dataset.layout=m.mobile?"mobile":"desktop";
 document.documentElement.style.setProperty("--cat-display-zoom",String(m.zoom));
 document.documentElement.style.zoom=m.zoom===1?"":String(m.zoom);
 return m;
}
