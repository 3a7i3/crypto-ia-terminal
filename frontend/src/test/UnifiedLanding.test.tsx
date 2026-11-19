import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import App from '../App';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
for(const path of ['/','/direction'])it('opens live radar from '+path,async()=>{
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline test')));
 window.history.replaceState({},'',path);
 render(<App/>);
 expect(await screen.findByRole('heading',{name:'Market Radar · MEXC Spot'})).toBeTruthy();
 // M1-C1 (EO-022, D-C1/D-C5): the canonical Market home is now the Radar deep route.
 // Was '/paper-live/market'; preserved property: / and /direction land on live Radar.
 expect(window.location.pathname).toBe('/paper-live/market/radar');
});
