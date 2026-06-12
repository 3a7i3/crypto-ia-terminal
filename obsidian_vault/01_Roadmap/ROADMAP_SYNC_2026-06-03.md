# Roadmap Sync — 2026-06-03

## Etat systeme

- P9 termine (meta gouvernance complete)
- P10 en execution operationnelle (pas encore phase live capital)

## Livrables confirms de la session

- Gouvernance G0->G8-E certifiee (ATC + EIC v2 + lifecycle + preuves Z3)
- Stack paper trading MEXC disponible:
  - infra/mexc_reader.py (read-only)
  - paper_trading/virtual_portfolio.py
  - paper_trading/mexc_simulator.py
- watchdog_vps.py disponible pour supervision VPS

## Dettes immediates

1. I-14 Layer 3: fail-closed agent exceptions en pipeline
2. I-15 Layer 3: can_trade gate force DecisionPacket REJECTED
3. I-16 Layer 3: trace_id obligatoire avant EXECUTION_PENDING
4. Auto-heal exchange: reconnect runtime reel (pas no-op)

## Priorites roadmap a court terme

1. Fiabilite runtime
2. Validation paper trading VPS
3. Burn-in KPI 7 jours
4. Decision go/no-go capital actif

## Liens internes Obsidian

- [[../00_Hub/Reprise_Demain_2026-06-03]]
- [[../02_Execution/Checklist_Demain_2026-06-04]]
- [[../02_Execution/Session_2026-06-03]]
