# Observabilité Totale — Checklist

## Questions auxquelles le système doit répondre instantanément

| Question | Source | Implémenté |
|----------|--------|------------|
| Pourquoi ce trade existe ? | black_box.jsonl trace_id | ✅ |
| Qui l'a autorisé ? | DecisionPacket.approved_by | ✅ |
| Quel régime était actif ? | RuntimeState.regime | ✅ |
| Quel signal a gagné ? | DecisionPacket.signal_source | ✅ |
| Pourquoi un signal a été rejeté ? | StructuredLogger | ✅ |
| Quel module a timeout ? | StructuredLogger.duration_ms | ✅ |
| Quelle version du modèle ? | DecisionPacket.model_version | ✅ |

## Politique de logs

1. Chaque événement critique = un JSON structuré
2. Chaque décision = un trace_id unique
3. Chaque transition d'état = logguée
4. black_box.jsonl = append-only, jamais modifié
5. Durée cycle enregistrée de CREATED à résolution finale
