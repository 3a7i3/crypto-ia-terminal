import { useLayoutEffect } from "react";
import { applyDisplayLayout, readDisplayLayout, type DisplayLayout } from "./displayLayout";
export function useDisplayLayout() {
 useLayoutEffect(()=>{
  let mode=readDisplayLayout();
  const apply=()=>applyDisplayLayout(mode);
  const change=(e:Event)=>{const value=(e as CustomEvent<DisplayLayout>).detail;if(value==="auto"||value==="mobile"||value==="desktop")mode=value;apply();};
  const storage=()=>{mode=readDisplayLayout();apply();};
  apply();window.addEventListener("resize",apply);window.addEventListener("orientationchange",apply);window.addEventListener("cat-display-layout",change);window.addEventListener("storage",storage);
  return()=>{window.removeEventListener("resize",apply);window.removeEventListener("orientationchange",apply);window.removeEventListener("cat-display-layout",change);window.removeEventListener("storage",storage);delete document.documentElement.dataset.layout;document.documentElement.style.zoom="";document.documentElement.style.removeProperty("--cat-display-zoom");};
 },[]);
}
