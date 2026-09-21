"""FIN-01 deterministic PPL -> FinancialEvent adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from financial_institute.models import (
    FIN_SCHEMA_VERSION,
    FinancialContext,
    FinancialEvent,
    financial_context_digest,
)
from financial_institute.semantics import (
    FinancialAccount,
    LedgerPosting,
    PostingSide,
    assert_balanced_postings,
    canonical_decimal,
    derive_financial_event_id,
    linear_price_pnl,
)
from paper_trading.ledger_events import LedgerEvent, LedgerEventType
from paper_trading.paper_portfolio_ledger import project


class FinancialAdapterError(ValueError):
    """PPL facts cannot be mapped to the certified FIN-00 semantics."""


@dataclass(frozen=True)
class AdaptedPPLStream:
    paper_epoch_id: str
    source_stream_digest: str
    source_code_sha: str
    config_hash: str
    financial_events: tuple[FinancialEvent, ...]
    last_source_sequence: int


@dataclass(frozen=True)
class _OpenFact:
    principal: Decimal
    entry_price: Decimal
    entry_fee: Decimal
    side: str


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    raise FinancialAdapterError(
        f"unsupported PPL value in canonical digest: {type(value).__name__}"
    )


def _canonical_ppl_line(event: LedgerEvent) -> bytes:
    record = {
        "event_id": event.event_id,
        "paper_epoch_id": event.paper_epoch_id,
        "sequence": event.sequence,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "trade_id": event.trade_id,
        "decision_id": event.decision_id,
        "payload": _jsonable(event.payload),
        "schema_version": event.schema_version,
    }
    try:
        return (
            json.dumps(
                record,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FinancialAdapterError(
            f"PPL canonical serialization failed: {exc}"
        ) from exc


def ppl_stream_digest(events: Sequence[LedgerEvent]) -> str:
    """Digest the complete validated PPL population in sequence order."""

    digest = hashlib.sha256()
    for event in events:
        digest.update(_canonical_ppl_line(event))
    return digest.hexdigest()


def _posting(
    *,
    financial_event_id: str,
    ordinal: int,
    account: FinancialAccount,
    side: PostingSide,
    asset: str,
    amount: Decimal,
    paper_epoch_id: str,
) -> LedgerPosting:
    return LedgerPosting(
        posting_id=f"{financial_event_id}:{ordinal:02d}",
        financial_event_id=financial_event_id,
        account=account,
        side=side,
        asset=asset,
        amount=amount,
        paper_epoch_id=paper_epoch_id,
    )


def _financial_event(
    *,
    source: LedgerEvent,
    context: FinancialContext,
    config_hash: str,
    semantic_context_digest: str,
    postings: Sequence[LedgerPosting],
) -> FinancialEvent:
    financial_event_id = derive_financial_event_id(
        source_domain="PAPER",
        source_authority=context.source_authority,
        source_event_id=source.event_id,
        paper_epoch_id=source.paper_epoch_id,
        source_sequence=source.sequence,
        schema_version=FIN_SCHEMA_VERSION,
        semantic_context_digest=semantic_context_digest,
    )
    materialized = tuple(postings)
    assert_balanced_postings(materialized)
    return FinancialEvent(
        financial_event_id=financial_event_id,
        paper_epoch_id=source.paper_epoch_id,
        source_event_id=source.event_id,
        source_sequence=source.sequence,
        source_event_type=source.event_type.value,
        source_schema_version=source.schema_version,
        timestamp=canonical_decimal("timestamp", source.timestamp),
        trade_id=source.trade_id,
        decision_id=source.decision_id,
        fin_schema_version=FIN_SCHEMA_VERSION,
        semantic_context_digest=semantic_context_digest,
        fin_code_sha=context.fin_code_sha,
        config_hash=config_hash,
        postings=materialized,
    )


def adapt_ppl_stream(
    events: Sequence[LedgerEvent],
    context: FinancialContext,
) -> AdaptedPPLStream:
    """Map one valid PPL epoch to deterministic financially-material events.

    RECOVERY_COMPLETED remains part of the source-stream digest/sequence but has
    no FinancialEvent because FIN-00 assigns it no financial posting.
    """

    if not events:
        raise FinancialAdapterError("PPL stream must not be empty")

    # Canonical PPL replay validates epoch partition, ordering and lifecycle.
    project(events)

    birth = events[0]
    if birth.event_type is not LedgerEventType.EPOCH_CREATED:
        raise FinancialAdapterError("first PPL event must be EPOCH_CREATED")

    source_code_sha = str(birth.payload["code_sha"])
    config_hash = str(birth.payload["config_snapshot_hash"])
    semantic_context_digest = financial_context_digest(context)
    if not source_code_sha or not config_hash:
        raise FinancialAdapterError("PPL epoch provenance is incomplete")

    open_facts: dict[str, _OpenFact] = {}
    financial_events: list[FinancialEvent] = []

    for source in events:
        fin_id = derive_financial_event_id(
            source_domain="PAPER",
            source_authority=context.source_authority,
            source_event_id=source.event_id,
            paper_epoch_id=source.paper_epoch_id,
            source_sequence=source.sequence,
            schema_version=FIN_SCHEMA_VERSION,
            semantic_context_digest=semantic_context_digest,
        )
        postings: list[LedgerPosting] = []

        if source.event_type is LedgerEventType.EPOCH_CREATED:
            capital = canonical_decimal(
                "initial_virtual_capital",
                source.payload["initial_virtual_capital"],
            )
            postings.extend(
                [
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=1,
                        account=FinancialAccount.CASH_AVAILABLE,
                        side=PostingSide.DEBIT,
                        asset=context.asset,
                        amount=capital,
                        paper_epoch_id=source.paper_epoch_id,
                    ),
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=2,
                        account=FinancialAccount.EPOCH_CAPITAL,
                        side=PostingSide.CREDIT,
                        asset=context.asset,
                        amount=capital,
                        paper_epoch_id=source.paper_epoch_id,
                    ),
                ]
            )

        elif source.event_type is LedgerEventType.POSITION_OPENED:
            assert source.trade_id is not None
            principal = canonical_decimal("principal", source.payload["principal"])
            entry_price = canonical_decimal(
                "entry_price", source.payload["entry_price"]
            )
            entry_fee = canonical_decimal("entry_fee", source.payload["entry_fee"])
            if principal <= 0 or entry_price <= 0 or entry_fee < 0:
                raise FinancialAdapterError("invalid OPEN financial facts")

            open_facts[source.trade_id] = _OpenFact(
                principal=principal,
                entry_price=entry_price,
                entry_fee=entry_fee,
                side=str(source.payload["side"]),
            )
            ordinal = 1
            postings.append(
                _posting(
                    financial_event_id=fin_id,
                    ordinal=ordinal,
                    account=FinancialAccount.CAPITAL_RESERVED,
                    side=PostingSide.DEBIT,
                    asset=context.asset,
                    amount=principal,
                    paper_epoch_id=source.paper_epoch_id,
                )
            )
            ordinal += 1
            if entry_fee > 0:
                postings.append(
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=ordinal,
                        account=FinancialAccount.FEES_EXPENSE,
                        side=PostingSide.DEBIT,
                        asset=context.asset,
                        amount=entry_fee,
                        paper_epoch_id=source.paper_epoch_id,
                    )
                )
                ordinal += 1
            postings.append(
                _posting(
                    financial_event_id=fin_id,
                    ordinal=ordinal,
                    account=FinancialAccount.CASH_AVAILABLE,
                    side=PostingSide.CREDIT,
                    asset=context.asset,
                    amount=principal + entry_fee,
                    paper_epoch_id=source.paper_epoch_id,
                )
            )

        elif source.event_type is LedgerEventType.POSITION_CLOSED:
            assert source.trade_id is not None
            opened = open_facts.pop(source.trade_id)
            exit_price = canonical_decimal(
                "exit_price", source.payload["exit_price"]
            )
            exit_fee = canonical_decimal("exit_fee", source.payload["exit_fee"])
            if exit_price <= 0 or exit_fee < 0:
                raise FinancialAdapterError("invalid CLOSE financial facts")

            gross = linear_price_pnl(
                principal=opened.principal,
                side=opened.side,
                entry_price=opened.entry_price,
                mark_or_exit_price=exit_price,
            )
            ordinal = 1
            postings.extend(
                [
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=ordinal,
                        account=FinancialAccount.CASH_AVAILABLE,
                        side=PostingSide.DEBIT,
                        asset=context.asset,
                        amount=opened.principal,
                        paper_epoch_id=source.paper_epoch_id,
                    ),
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=ordinal + 1,
                        account=FinancialAccount.CAPITAL_RESERVED,
                        side=PostingSide.CREDIT,
                        asset=context.asset,
                        amount=opened.principal,
                        paper_epoch_id=source.paper_epoch_id,
                    ),
                ]
            )
            ordinal += 2
            if gross > 0:
                postings.extend(
                    [
                        _posting(
                            financial_event_id=fin_id,
                            ordinal=ordinal,
                            account=FinancialAccount.CASH_AVAILABLE,
                            side=PostingSide.DEBIT,
                            asset=context.asset,
                            amount=gross,
                            paper_epoch_id=source.paper_epoch_id,
                        ),
                        _posting(
                            financial_event_id=fin_id,
                            ordinal=ordinal + 1,
                            account=FinancialAccount.REALIZED_TRADING_PNL,
                            side=PostingSide.CREDIT,
                            asset=context.asset,
                            amount=gross,
                            paper_epoch_id=source.paper_epoch_id,
                        ),
                    ]
                )
                ordinal += 2
            elif gross < 0:
                loss = abs(gross)
                postings.extend(
                    [
                        _posting(
                            financial_event_id=fin_id,
                            ordinal=ordinal,
                            account=FinancialAccount.REALIZED_TRADING_PNL,
                            side=PostingSide.DEBIT,
                            asset=context.asset,
                            amount=loss,
                            paper_epoch_id=source.paper_epoch_id,
                        ),
                        _posting(
                            financial_event_id=fin_id,
                            ordinal=ordinal + 1,
                            account=FinancialAccount.CASH_AVAILABLE,
                            side=PostingSide.CREDIT,
                            asset=context.asset,
                            amount=loss,
                            paper_epoch_id=source.paper_epoch_id,
                        ),
                    ]
                )
                ordinal += 2
            if exit_fee > 0:
                postings.extend(
                    [
                        _posting(
                            financial_event_id=fin_id,
                            ordinal=ordinal,
                            account=FinancialAccount.FEES_EXPENSE,
                            side=PostingSide.DEBIT,
                            asset=context.asset,
                            amount=exit_fee,
                            paper_epoch_id=source.paper_epoch_id,
                        ),
                        _posting(
                            financial_event_id=fin_id,
                            ordinal=ordinal + 1,
                            account=FinancialAccount.CASH_AVAILABLE,
                            side=PostingSide.CREDIT,
                            asset=context.asset,
                            amount=exit_fee,
                            paper_epoch_id=source.paper_epoch_id,
                        ),
                    ]
                )

        elif source.event_type is LedgerEventType.POSITION_UNRESOLVED:
            assert source.trade_id is not None
            opened = open_facts.pop(source.trade_id)
            postings.extend(
                [
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=1,
                        account=FinancialAccount.CAPITAL_UNRESOLVED,
                        side=PostingSide.DEBIT,
                        asset=context.asset,
                        amount=opened.principal,
                        paper_epoch_id=source.paper_epoch_id,
                    ),
                    _posting(
                        financial_event_id=fin_id,
                        ordinal=2,
                        account=FinancialAccount.CAPITAL_RESERVED,
                        side=PostingSide.CREDIT,
                        asset=context.asset,
                        amount=opened.principal,
                        paper_epoch_id=source.paper_epoch_id,
                    ),
                ]
            )

        elif source.event_type is LedgerEventType.RECOVERY_COMPLETED:
            continue
        else:
            raise FinancialAdapterError(
                f"unsupported PPL event type {source.event_type.value}"
            )

        financial_events.append(
            _financial_event(
                source=source,
                context=context,
                config_hash=config_hash,
                semantic_context_digest=semantic_context_digest,
                postings=postings,
            )
        )

    return AdaptedPPLStream(
        paper_epoch_id=birth.paper_epoch_id,
        source_stream_digest=ppl_stream_digest(events),
        source_code_sha=source_code_sha,
        config_hash=config_hash,
        financial_events=tuple(financial_events),
        last_source_sequence=events[-1].sequence,
    )
