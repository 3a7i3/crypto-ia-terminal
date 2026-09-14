# SEC-API-01 — Private boundary examples

Legitimate exchange-credential consumers remain outside stripping:

- `infra/mexc_reader.py` for authenticated balance/position reads
- `observability/real_accounts.py`
- `src/telegram/exchange_sync.py`
- `infra/exchange_factory.py` / `ExecutionEngine`
- explicit TESTNET/REAL execution and future Treasury/Reconciliation paths

Their inclusion here is documentary; SEC-API-01 does not modify them.
