# SEC-API-01 — Test matrix

| Gate | Expected |
|---|---|
| StreamBus env credentials present | not consumed |
| StreamBus explicit apiKey/secret/password | stripped |
| HistoricalDataFetcher env credentials present | not consumed |
| LMI / market observer / radar / horizons units | no `.env.secrets` |
| Quant unit | dedicated mandatory Quant fragment only |
| Radar Bot unit | dedicated mandatory Radar fragment only |
| Dashboard unit | dedicated mandatory Dashboard fragment only |
| Quant/Radar/Dashboard | no global `.env.secrets` |
| Paper/Watchdog current branch boundary | exchange credential deny-list retained |
| `crypto-advisor.service` | private secret access preserved |
| Runtime public/passive processes | exchange private credentials absent |
| Runtime Quant identity | present only in Quant |
| Runtime Radar identity | present only in Radar |
| Runtime Dashboard password | present only in Dashboard |
| Runtime dashboard auth | authenticated behavior confirmed |
