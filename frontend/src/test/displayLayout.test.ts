import {describe,it,expect} from "vitest";
import {displayMetrics} from "../lib/displayLayout";
describe("display viewport selection",()=>{
 it("uses normal portrait without shrinking",()=>{expect(displayMetrics("auto",412,915,412,412,true)).toEqual({mobile:true,zoom:1});});
 it("keeps mobile navigation in landscape",()=>{expect(displayMetrics("auto",915,412,915,915,true)).toEqual({mobile:true,zoom:1});});
 it("compensates a wide portrait viewport on a narrow touch screen",()=>{const m=displayMetrics("auto",980,2100,412,412,true);expect(m.mobile).toBe(true);expect(m.zoom).toBeCloseTo(980/412);});
 it("handles portrait touch when browser reports wide screen too",()=>{expect(displayMetrics("auto",980,2100,980,980,true)).toEqual({mobile:true,zoom:980/480});});
 it("honours desktop preference on touch device",()=>{expect(displayMetrics("desktop",980,2100,412,412,true)).toEqual({mobile:false,zoom:1});});
 it("keeps desktop unchanged",()=>{expect(displayMetrics("auto",1440,900,1440,1440,false)).toEqual({mobile:false,zoom:1});});
 it("bounds correction scale",()=>{expect(displayMetrics("mobile",2000,3000,320,320,true).zoom).toBe(3);});
});
