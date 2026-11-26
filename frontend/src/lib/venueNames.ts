// Display names only. A venue absent from this table is still shown, by its identifier:
// admitting a further exchange needs a reviewed binding upstream, not a change here.
const NAMES: Record<string, string> = { mexc: "MEXC", bybit: "Bybit", okx: "OKX", kraken: "Kraken", bitfinex: "Bitfinex", kucoin: "KuCoin", coinbase_exchange: "Coinbase Exchange", hyperliquid: "Hyperliquid" };
export const venueName = (id: string): string => NAMES[id] ?? id;
export const marketKindLabel: Record<string, string> = { SPOT: "Spot", PERPETUAL_LINEAR: "Perpétuel linéaire", PERPETUAL_INVERSE: "Perpétuel inverse", FUTURE_LINEAR: "Échéance linéaire", FUTURE_INVERSE: "Échéance inverse" };
