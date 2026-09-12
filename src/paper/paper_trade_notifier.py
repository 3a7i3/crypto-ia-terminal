"""
src/paper/paper_trade_notifier.py — Notificateur Telegram PUSH-ONLY des
trades PAPER de la main machine (mission TG-PAPER-01).

Rôle exact et exclusif : lire databases/paper_trades.jsonl (source de
vérité écrite par paper_trading/recorder.py), filtrer les événements
mode="futures_demo" (main machine), et envoyer une notification Telegram
par OPEN et par CLOSE via @PaperArena_bot.

Ce module n'est PAS une autorité financière :
  - il ne génère aucun signal, aucune stratégie, aucun score ;
  - il n'ouvre, ne ferme, ni ne modifie aucune position ;
  - il n'écrit jamais dans paper_trades.jsonl ;
  - une panne d'envoi Telegram n'a strictement aucun effet sur le moteur.

Garantie de livraison : AT-LEAST-ONCE. Un événement peut être notifié deux
fois si le process meurt entre l'envoi Telegram réussi et l'écriture du
checkpoint local (cache/paper_trade_notifier_checkpoint.json) — un doublon
occasionnel est acceptable, un trade silencieusement manqué ne l'est pas.
Il n'y a jamais d'exactly-once ici, et ce module ne le prétend pas.

Bootstrap "live-only" : au tout premier démarrage (aucun checkpoint
présent), le notificateur se positionne à la fin du fichier existant et ne
notifie AUCUN événement historique. Seuls les événements ajoutés après ce
démarrage sont envoyés. Un checkpoint corrompu/illisible est traité comme
une absence de checkpoint (fail safe, jamais un replay complet).

Env vars requis (identité Telegram réutilisée, aucune autre) :
    PAPER_ARENA_BOT_TOKEN
    PAPER_ARENA_CHAT_ID

Aucun fallback vers un autre token/chat. Absence de l'un ou l'autre =
échec de démarrage explicite (fail closed).

Seule méthode Telegram autorisée : sendMessage. Aucune méthode de
réception/polling, aucun dispatcher de commande.

Usage service :
    python3 -m src.paper.paper_trade_notifier
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_HTTP_TIMEOUT_S = 8
_POLL_INTERVAL_S = 2.0

_MAIN_MACHINE_MODE = "futures_demo"
_HANDLED_EVENTS = ("OPEN", "CLOSE")


# ── Configuration ────────────────────────────────────────────────────────────


class NotifierConfigError(RuntimeError):
    """Configuration manquante ou invalide — échec de démarrage explicite."""


@dataclass(frozen=True)
class NotifierConfig:
    bot_token: str
    chat_id: str
    source_path: Path
    checkpoint_path: Path

    @classmethod
    def from_env(cls) -> "NotifierConfig":
        token = os.getenv("PAPER_ARENA_BOT_TOKEN", "")
        chat_id = os.getenv("PAPER_ARENA_CHAT_ID", "")
        if not token:
            raise NotifierConfigError(
                "PAPER_ARENA_BOT_TOKEN manquant — démarrage refusé (fail closed)"
            )
        if not chat_id:
            raise NotifierConfigError(
                "PAPER_ARENA_CHAT_ID manquant — démarrage refusé (fail closed)"
            )
        source = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
        checkpoint = Path(
            os.getenv(
                "PAPER_TRADE_NOTIFIER_CHECKPOINT",
                "cache/paper_trade_notifier_checkpoint.json",
            )
        )
        return cls(
            bot_token=token,
            chat_id=chat_id,
            source_path=source,
            checkpoint_path=checkpoint,
        )


# ── Client Telegram (send-only) ──────────────────────────────────────────────


class TelegramSender:
    """Client minimal, send-only. Seule méthode utilisée : sendMessage.

    Aucune capacité de réception/polling ici — ce client n'a même pas les
    moyens d'en faire.
    """

    def __init__(self, token: str, chat_id: str) -> None:
        self._url = _TELEGRAM_API.format(token=token)
        self._chat_id = chat_id

    def send(self, text: str) -> bool:
        """Retourne True seulement si Telegram a réellement livré le message.

        Contrat d'ACK strict (TG-PAPER-01-R1 §5) : la requête HTTP doit
        réussir, le statut doit être 2xx, le corps de réponse doit être un
        JSON valide de la Bot API, et ce JSON doit contenir `"ok": true`.
        Un statut 2xx avec `{"ok": false}` (ou un corps non-JSON/invalide)
        n'est PAS un succès — Telegram peut renvoyer 200 sur une requête
        malgré tout rejetée. Ne lève jamais — un échec réseau/HTTP/de
        contenu est observable via le retour False + un log, jamais via une
        exception qui remonterait au moteur de trading. Le token n'est
        jamais loggé.
        """
        payload = {
            "chat_id": self._chat_id,
            "text": text,
        }
        data = urllib.parse.urlencode(payload).encode()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(self._url, data=data), timeout=_HTTP_TIMEOUT_S
            ) as resp:
                status = resp.status
                body = resp.read()
        except urllib.error.HTTPError as e:
            logger.warning("Telegram sendMessage failed: HTTP %s %s", e.code, e.reason)
            return False
        except Exception as e:
            logger.warning("Telegram sendMessage failed: %s", e)
            return False

        if not (200 <= status < 300):
            logger.warning("Telegram sendMessage HTTP status=%s", status)
            return False

        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            logger.warning(
                "Telegram sendMessage: réponse non-JSON malgré HTTP %s", status
            )
            return False

        if not isinstance(parsed, dict) or parsed.get("ok") is not True:
            logger.warning(
                "Telegram sendMessage: ok != true (description=%r)",
                parsed.get("description") if isinstance(parsed, dict) else None,
            )
            return False

        return True


# ── Checkpoint de livraison (non financier) ──────────────────────────────────


@dataclass
class Checkpoint:
    source_path: str
    byte_offset: int
    last_fingerprint: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "byte_offset": self.byte_offset,
            "last_fingerprint": self.last_fingerprint,
        }


class CheckpointStore:
    """Persistance atomique du checkpoint de livraison Telegram.

    Ceci n'est PAS un état financier : perdre/corrompre ce fichier ne
    modifie ni ne rejoue jamais paper_trades.jsonl, il ne fait au pire que
    déclencher un nouveau bootstrap "live-only" (voir load()).
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Optional[Checkpoint]:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return Checkpoint(
                source_path=raw["source_path"],
                byte_offset=int(raw["byte_offset"]),
                last_fingerprint=raw.get("last_fingerprint"),
            )
        except Exception as e:
            # Fail safe : un checkpoint illisible/corrompu ne doit jamais
            # provoquer un replay complet de l'historique. On log et on
            # laisse l'appelant re-bootstrap proprement à l'EOF courant.
            logger.error(
                "Checkpoint illisible/corrompu (%s) — re-bootstrap sûr à l'EOF: %s",
                self._path,
                e,
            )
            return None

    def save(self, checkpoint: Checkpoint) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._path)


# ── Filtrage / parsing des événements ────────────────────────────────────────


def is_main_machine_event(record: dict) -> bool:
    """True seulement pour un OPEN/CLOSE explicitement mode=futures_demo.

    Un `mode` absent n'est jamais traité comme PAPER main-machine (filtrage
    conservateur — voir mission §4).
    """
    if record.get("event") not in _HANDLED_EVENTS:
        return False
    return record.get("mode") == _MAIN_MACHINE_MODE


def normalize_side(side: Optional[str]) -> str:
    if not isinstance(side, str):
        return "UNKNOWN"
    s = side.strip().lower()
    if s in ("buy", "long"):
        return "LONG"
    if s in ("sell", "short"):
        return "SHORT"
    return "UNKNOWN"


def fingerprint(record: dict) -> str:
    return f"{record.get('trade_id', '')}:{record.get('event', '')}:{record.get('ts', '')}"


# ── Formatage des messages ───────────────────────────────────────────────────


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "UNKNOWN"
    return f"${value:,.2f}"


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "UNKNOWN"
    total_min = int(seconds // 60)
    hours, minutes = divmod(total_min, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def format_entry_message(record: dict) -> str:
    side = normalize_side(record.get("side"))
    symbol = record.get("symbol", "UNKNOWN")
    price = record.get("price")
    size = record.get("size_usd")
    score = record.get("score")
    regime = record.get("regime") or "UNKNOWN"
    trade_id = record.get("trade_id", "UNKNOWN")

    price_line = _fmt_money(price) if price is not None else "UNKNOWN"
    size_line = _fmt_money(size) if size is not None else "UNKNOWN"
    score_line = f"{score}/100" if score is not None else "UNKNOWN"

    return (
        "🟢 PAPER ENTRY\n\n"
        f"{symbol}\n"
        f"{side}\n\n"
        f"Prix   : {price_line}\n"
        f"Taille : {size_line}\n"
        f"Score  : {score_line}\n"
        f"Régime : {regime}\n\n"
        f"Trade  : {trade_id}\n\n"
        "Mode   : PAPER"
    )


def format_exit_message(record: dict) -> str:
    side = normalize_side(record.get("side"))
    symbol = record.get("symbol", "UNKNOWN")
    exit_price = record.get("exit_price")
    pnl_usd = record.get("pnl_usd")
    reason = record.get("reason") or "UNKNOWN"
    duration_s = record.get("duration_s")
    trade_id = record.get("trade_id", "UNKNOWN")
    fee_incomplete = bool(record.get("pnl_fee_evidence_incomplete"))

    if pnl_usd is None:
        header = "⚠️ PAPER OUTCOME UNRESOLVED"
    else:
        header = "🟢 PAPER EXIT" if pnl_usd >= 0 else "🔴 PAPER EXIT"

    exit_line = _fmt_money(exit_price)
    if pnl_usd is None:
        pnl_line = "UNKNOWN"
    else:
        sign = "+" if pnl_usd >= 0 else ""
        pnl_line = f"{sign}${pnl_usd:,.2f}"

    lines = [
        header,
        "",
        symbol,
        side,
        "",
        f"Sortie : {exit_line}",
        f"PnL    : {pnl_line}",
        f"Raison : {reason}",
        f"Durée  : {_fmt_duration(duration_s)}",
        "",
        f"Trade  : {trade_id}",
        "",
        "Mode   : PAPER",
    ]
    if fee_incomplete:
        lines.append("")
        lines.append("⚠️ PnL fee evidence incomplete")
    return "\n".join(lines)


def format_message(record: dict) -> Optional[str]:
    if record.get("event") == "OPEN":
        return format_entry_message(record)
    if record.get("event") == "CLOSE":
        return format_exit_message(record)
    return None


# ── Lecteur append-only JSONL avec checkpoint ────────────────────────────────


class PaperTradeLedgerFollower:
    """Suit databases/paper_trades.jsonl en lecture seule, incrémentale.

    Ne verrouille, ne tronque, ni ne renomme jamais le fichier source. Une
    ligne finale incomplète (écriture concurrente en cours) est ignorée
    jusqu'à ce qu'elle soit complète — l'offset n'avance pas dessus. Une
    ligne complète mais JSON invalide est déterministement sautée (jamais un
    blocage indéfini du notificateur), mais STRICTEMENT dans l'ordre
    source : `poll_new_records()` ne mute jamais l'offset committé
    elle-même (pur read-ahead) — c'est `run_once()` qui avance le
    checkpoint événement par événement, dans l'ordre, si bien qu'une ligne
    malformée ne peut jamais être sautée avant l'événement valide qui la
    précède si ce dernier est encore en attente de livraison Telegram.
    """

    def __init__(self, config: NotifierConfig, checkpoint_store: CheckpointStore) -> None:
        self._config = config
        self._checkpoint_store = checkpoint_store
        self._offset = 0
        self._bootstrapped = False

    def bootstrap(self) -> None:
        """Positionne l'offset de départ : checkpoint existant, ou EOF.

        Un checkpoint absent ou corrompu déclenche un bootstrap "live-only"
        à l'EOF courant du fichier (aucun replay historique), et sauvegarde
        immédiatement ce point de départ.
        """
        checkpoint = self._checkpoint_store.load()
        source_str = str(self._config.source_path)

        if checkpoint is not None and checkpoint.source_path == source_str:
            current_size = self._current_eof()
            if checkpoint.byte_offset < 0 or checkpoint.byte_offset > current_size:
                # Checkpoint incohérent avec la source actuelle (offset
                # négatif, ou au-delà de la taille réelle — p.ex. une
                # source tronquée/remplacée). Fail safe (§7) : jamais un
                # seek au-delà d'EOF suivi d'un blocage silencieux, jamais
                # un replay complet — on re-bootstrap sûrement à l'EOF
                # courant, comme un premier démarrage.
                logger.error(
                    "Checkpoint incohérent (offset=%d, taille source=%d) — "
                    "re-bootstrap sûr à l'EOF (%s)",
                    checkpoint.byte_offset,
                    current_size,
                    source_str,
                )
                checkpoint = None

        if checkpoint is not None and checkpoint.source_path == source_str:
            self._offset = checkpoint.byte_offset
            logger.info(
                "Notifier resuming from checkpoint offset=%d (%s)",
                self._offset,
                source_str,
            )
        else:
            self._offset = self._current_eof()
            logger.info(
                "Notifier first boot (no usable checkpoint) — starting at EOF "
                "offset=%d, zero historical replay (%s)",
                self._offset,
                source_str,
            )
            self._checkpoint_store.save(
                Checkpoint(source_path=source_str, byte_offset=self._offset)
            )
        self._bootstrapped = True

    def _current_eof(self) -> int:
        if not self._config.source_path.exists():
            return 0
        return self._config.source_path.stat().st_size

    def poll_new_records(self) -> list[tuple[str, Optional[dict], int]]:
        """Retourne les nouvelles lignes complètes, dans l'ordre source.

        Chaque élément est `(kind, record_or_none, offset_après_cette_ligne)`
        où `kind` vaut `"event"` (JSON valide, `record` peuplé) ou
        `"malformed"` (ligne complète mais JSON invalide, `record` vaut
        None). N'avance JAMAIS `self._offset` — cette méthode est un pur
        read-ahead. C'est exclusivement à l'appelant (`run_once`) de
        committer via `advance()`, un élément à la fois, dans l'ordre
        renvoyé ici. C'est ce qui garantit qu'un échec d'envoi Telegram sur
        un événement ne peut jamais être contourné par un effet de bord du
        parsing d'une ligne ultérieure (TG-PAPER-01-R1 §1/§2) : tant que
        l'appelant n'a pas committé l'événement en échec, cette méthode
        recommencera à le relire depuis le même `self._offset` au prochain
        appel.
        """
        assert self._bootstrapped, "bootstrap() doit être appelé avant poll"
        if not self._config.source_path.exists():
            return []

        results: list[tuple[str, Optional[dict], int]] = []
        with self._config.source_path.open("rb") as f:
            f.seek(self._offset)
            pos = self._offset
            while True:
                line = f.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    # Ligne finale incomplète (écriture concurrente en
                    # cours) — on ne l'avale pas, on réessaiera plus tard.
                    break
                pos += len(line)
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except Exception as e:
                    logger.error(
                        "Ligne JSONL complète mais invalide, sautée "
                        "(en ordre source, une fois son prédécesseur "
                        "committé): %s | line=%r",
                        e,
                        text[:200],
                    )
                    results.append(("malformed", None, pos))
                    continue
                results.append(("event", record, pos))
        return results

    def advance(self, offset: int, fingerprint_value: Optional[str] = None) -> None:
        self._offset = offset
        self._checkpoint_store.save(
            Checkpoint(
                source_path=str(self._config.source_path),
                byte_offset=self._offset,
                last_fingerprint=fingerprint_value,
            )
        )


# ── Boucle principale ─────────────────────────────────────────────────────────


def run_once(
    follower: PaperTradeLedgerFollower,
    send: Callable[[str], bool],
) -> int:
    """Traite les nouveaux événements disponibles. Retourne le nombre envoyé.

    AT-LEAST-ONCE : le checkpoint n'avance qu'après un send() réussi pour
    chaque événement, un par un, STRICTEMENT dans l'ordre source renvoyé par
    poll_new_records() — un send raté arrête immédiatement le traitement
    (`break`), avant de committer quoi que ce soit après lui, y compris une
    ligne malformée qui le suivrait dans le fichier. Cela garantit qu'aucun
    événement en attente de livraison ne peut être sauté par effet de bord
    du traitement d'une ligne ultérieure (TG-PAPER-01-R1 §1/§2).
    """
    sent = 0
    for kind, record, offset_after in follower.poll_new_records():
        if kind == "malformed":
            follower.advance(offset_after)
            continue
        if not is_main_machine_event(record):
            follower.advance(offset_after)
            continue
        text = format_message(record)
        if text is None:
            follower.advance(offset_after)
            continue
        if send(text):
            follower.advance(offset_after, fingerprint(record))
            sent += 1
        else:
            logger.warning(
                "Échec d'envoi Telegram — checkpoint non avancé, retry plus tard "
                "(trade_id=%s event=%s)",
                record.get("trade_id"),
                record.get("event"),
            )
            break
    return sent


def run_forever(config: Optional[NotifierConfig] = None) -> None:
    cfg = config or NotifierConfig.from_env()
    sender = TelegramSender(cfg.bot_token, cfg.chat_id)
    checkpoint_store = CheckpointStore(cfg.checkpoint_path)
    follower = PaperTradeLedgerFollower(cfg, checkpoint_store)
    follower.bootstrap()

    logger.info(
        "Paper Trade Notifier démarré (push-only, source=%s)", cfg.source_path
    )
    while True:
        try:
            run_once(follower, sender.send)
        except Exception as e:
            # Le notificateur ne doit jamais crasher le service pour une
            # cause transitoire (fichier absent, IO momentanée...).
            logger.error("Erreur non fatale dans la boucle du notificateur: %s", e)
        time.sleep(_POLL_INTERVAL_S)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_forever()


if __name__ == "__main__":
    main()
