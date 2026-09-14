# SEC-API-01 — Test matrix

| Gate | Expected |
|---|---|
| StreamBus env credentials present | not consumed |
| StreamBus explicit apiKey/secret | stripped |
| HistoricalDataFetcher env credentials present | not consumed |
| LMI / market observer / radar / horizons units | no `.env.secrets` |
| Quant/Radar/Dashboard/Paper/Watchdog units | secret store allowed + exchange credentials unset |
| crypto-advisor.service | private secret access preserved |
| Runtime passive processes | exchange private vars absent/non-empty = NONE |
| Runtime required bot/dashboard identities | remain available where configured |
