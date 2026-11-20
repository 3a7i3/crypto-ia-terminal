# Provenance — définitions protobuf MEXC Spot WebSocket

Copie verbatim, non modifiée, des définitions publiques officielles.

- Dépôt : https://github.com/mexcdevelop/websocket-proto
- Révision : `0c9c4f35dd0fadc3a46a350e909a93379d81e811`
  (2026-09-09, « Update PublicIncreaseDepthsV3Api.proto (#6) »)
- Licence : Apache-2.0 (fichier `LICENSE` copié tel quel)

| Fichier | sha256 |
|---|---|
| PushDataV3ApiWrapper.proto | `1869bbb700319ea4a0844ec11860dade0868c6a3a444dd3db6455db3c578c4fd` |
| PublicAggreDepthsV3Api.proto | `77e5d4a690dab83901691c906abf910e904ebbbbcb3d3e345333785992f66994` |
| PublicAggreBookTickerV3Api.proto | `2fb244c34e3fd9d4760795166bd1e43f0c9939bb3982f96d71c66da5388d0108` |
| LICENSE | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |

Usage : `bbo_wire.py` décode à la main (stdlib, sans `protoc`) les numéros de
champ ci-dessous. Le test `test_bbo_wire.py` relit ces fichiers, vérifie leurs
empreintes et que chaque numéro de champ utilisé par le décodeur y figure.

- `PushDataV3ApiWrapper` : channel=1, publicAggreDepths=313,
  symbol=3, symbolId=4, createTime=5 (« 消息生成时间 », heure de génération),
  sendTime=6 (« 消息推送时间 », heure de push).
- `PublicAggreDepthsV3Api` : asks=1, bids=2, eventType=3, fromVersion=4,
  toVersion=5 (chaînes décimales d'entiers), lastOrderCreateTime=6 (int64,
  conservé comme métadonnée, jamais utilisé comme âge du BBO).
- `PublicAggreDepthV3ApiItem` : price=1, quantity=2 (chaînes décimales).

Le sens exact de `createTime`/`sendTime` (horloge, unité) reste
« à qualifier au runtime ».
