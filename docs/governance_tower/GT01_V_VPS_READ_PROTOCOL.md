# GT01-V — Protocole de lecture VPS réelle (NON EXÉCUTÉ)

Statut : `GT01_LIVE_VPS_PROVEN = NOT_PROVEN`. Ce document décrit ce qu'une future preuve
devrait contenir. Il **n'autorise rien** : son exécution exige l'accord explicite de Mathieu,
dans une mission distincte, sous la garde [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286).

## 1. Ce qui est lu, et seulement cela

- `GET /api/operator/v1/runtime-service` et `GET /api/operator/v1/storage` de l'Operator API
  existante, en lecture seule, via `OperatorApiHostProvider`.
- Accès par un tunnel déjà existant et contrôlé par l'opérateur vers `127.0.0.1` ; Sentinel
  n'ouvre ni tunnel, ni port, ni session SSH.
- Aucune lecture de JSONL, de base de données, de journal, de secret, de ledger PPL/FIN.

## 2. Préconditions

1. Accord écrit de Mathieu nommant la date, la durée et le tunnel.
2. Le HEAD source de Sentinel utilisé est noté (SHA exact).
3. `expected_host_id` renseigné avec l'identité publiée attendue.
4. Aucun restart, aucune modification du checkout, de la configuration ou des services.

## 3. Exécution (une seule fois, bornée)

```bash
python -m governance_tower ask "Le VPS exécute-t-il la même version que GitHub ?" \
  --host-operator-api http://127.0.0.1:<port-du-tunnel> --json > gt01v_run.json
```

Deux GET au plus par question. Le serveur Sentinel n'est pas lancé à demeure.

## 4. Preuve attendue

- `gt01v_run.json` : `mode = LIVE_READ`, preuves `snapshot:` avec `observed_at_utc`,
  ETag éventuel, âge, `HOST_MISMATCH`/`NON_MONOTONIC` absents ou expliqués.
- Horodatage UTC, SHA de Sentinel, identité de l'opérateur ayant ouvert le tunnel.
- Constat explicite : ce qui reste NOT_PUBLISHED (hash de configuration, ressources, journaux).

## 5. Critères d'échec

Toute réponse autre que `application/json`, toute redirection, tout horodatage futur ou
rétrograde, toute identité d'hôte inattendue : arrêt, aucune nouvelle tentative automatique.
