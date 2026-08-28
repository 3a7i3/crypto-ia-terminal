#!/usr/bin/env python3
"""radar_bot.py — Bot Telegram interactif CryptoRadar. LECTURE SEULE.

Domaine : découverte d'opportunités de marché.
Ce bot répond à une seule question : « Où se passe-t-il quelque chose sur le marché ? »
Il n'affiche jamais d'Entry/SL/TP, de données portfolio, ni de métriques système.
Voir docs/architecture/TELEGRAM_BOT_REGISTRY.md pour le contrat complet.
"""

from __future__ import annotations
import json, os, sys, time, traceback, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DP_DIR = Path(os.getenv("DP_LOG_DIR", str(PROJECT / "databases")))
# Token dédié CryptoRadar — AUCUN fallback cross-identité (constitution
# Telegram, Principe 3 : "No Cross-Identity Token Fallback"). Voir
# docs/architecture/TELEGRAM_BOT_REGISTRY.md et docs/TELEGRAM_CONSTITUTION.md.
TOKEN = os.getenv("RADAR_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("RADAR_CHAT_ID", "").strip()
ALLOWED_CHATS = {CHAT_ID} if CHAT_ID else set()

def tg_request(method, payload=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if payload:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def send_message(chat_id, text):
    MAX_LEN = 4000
    chunks = [text] if len(text) <= MAX_LEN else []
    if not chunks:
        chunk = ""
        for line in text.split("\n"):
            if len(chunk) + len(line) + 1 > MAX_LEN:
                chunks.append(chunk)
                chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk.strip():
            chunks.append(chunk)
    for i, ch in enumerate(chunks):
        tg_request("sendMessage", {"chat_id": chat_id, "text": ch, "disable_web_page_preview": True})
        if i < len(chunks) - 1:
            time.sleep(0.3)

def load_recent_packets(hours=24):
    now = datetime.utcnow()
    dates = set()
    for h in range(int(hours) + 1):
        dates.add((now - timedelta(hours=h)).strftime("%Y-%m-%d"))
    packets = []
    for date_str in sorted(dates):
        fp = DP_DIR / f"decision_packets_{date_str}.jsonl"
        if not fp.exists():
            continue
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    packets.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return packets

def compute_symbol_stats(packets, min_conf=0):
    by_sym = defaultdict(list)
    for p in packets:
        conf = p.get("confidence", 0)
        if conf < min_conf:
            continue
        sym = p.get("symbol", "")
        if sym:
            by_sym[sym].append(p)
    results = []
    for sym, pks in by_sym.items():
        confs = [p.get("confidence", 0) for p in pks]
        avg = sum(confs) / len(confs)
        sides = [p.get("side", "") for p in pks]
        longs = sum(1 for s in sides if s in ("BUY", "LONG"))
        shorts = sum(1 for s in sides if s in ("SELL", "SHORT"))
        if longs > shorts:
            dom, dom_pct = "LONG", longs / len(sides) * 100
        elif shorts > longs:
            dom, dom_pct = "SHORT", shorts / len(sides) * 100
        else:
            dom, dom_pct = "MIXED", 50.0
        regimes = defaultdict(int)
        for p in pks:
            regimes[p.get("regime", "?")] += 1
        regime = max(regimes, key=regimes.get)
        results.append({"symbol": sym, "avg_confidence": round(avg, 1),
            "max_confidence": max(confs), "n_signals": len(pks),
            "dominant_side": dom, "dominance_pct": round(dom_pct, 0),
            "regime": regime})
    results.sort(key=lambda r: r["avg_confidence"], reverse=True)
    return results

def extract_signals(packets):
    """Extrait les signaux avec Entry/SL/TP des packets.
    USAGE INTERNE UNIQUEMENT — pas exposé comme commande Telegram CryptoRadar.
    Ces données appartiennent au domaine Portfolio (voir TELEGRAM_BOT_REGISTRY.md).
    """
    signals = []
    seen = set()
    for p in packets:
        entry = p.get("entry_price")
        sl = p.get("stop_loss")
        tp = p.get("take_profit")
        if not entry or not sl or not tp:
            continue
        sym = p.get("symbol", "?")
        side = p.get("side", "?")
        key = f"{sym}:{side}:{round(entry, 4)}"
        if key in seen:
            continue
        seen.add(key)
        if side in ("BUY", "LONG"):
            risk = (entry - sl) / entry * 100 if entry > 0 else 0
            reward = (tp - entry) / entry * 100 if entry > 0 else 0
        else:
            risk = (sl - entry) / entry * 100 if entry > 0 else 0
            reward = (entry - tp) / entry * 100 if entry > 0 else 0
        signals.append({"symbol": sym, "side": side, "entry": entry,
            "sl": sl, "tp": tp, "r_multiple": p.get("r_multiple"),
            "confidence": p.get("confidence", 0), "regime": p.get("regime", "?"),
            "risk_pct": round(risk, 2), "reward_pct": round(reward, 2)})
    signals.sort(key=lambda s: s["confidence"], reverse=True)
    return signals

def cmd_scan(args):
    top_n = 10
    if args.strip().isdigit():
        top_n = min(int(args.strip()), 50)
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=65)[:top_n]
    if not stats:
        return "\U0001f4ca SCAN — Aucun symbole avec conf >= 65"
    now_str = datetime.utcnow().strftime("%d %b · %H:%M UTC")
    regime_counts: dict = defaultdict(int)
    for s in compute_symbol_stats(packets, min_conf=0):
        regime_counts[s["regime"]] += 1
    main_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "?"
    total_universe = len(compute_symbol_stats(packets, min_conf=0))
    watchlist = len(compute_symbol_stats(packets, min_conf=50)) - len(stats)
    lines = [
        f"\U0001f4e1 CRYPTORADAR",
        f"{now_str}",
        "",
        f"March\u00e9: {main_regime}",
        f"Univers: {total_universe} paires \u00b7 Actionnables: {len(stats)} (\u226565)",
        "",
        "\U0001f525 TOP OPPORTUNIT\u00c9S",
    ]
    for i, s in enumerate(stats, 1):
        icon = "\U0001f7e2" if s["dominant_side"] == "LONG" else "\U0001f534" if s["dominant_side"] == "SHORT" else "\u26aa"
        lines.append(f"{i}. {icon} {s['symbol']}  {s['avg_confidence']:.0f}  {s['dominant_side']}  {s['regime']}")
    if watchlist > 0:
        lines += ["", f"\U0001f440 SURVEILLANCE", f"{watchlist} paires entre 50\u201364"]
    lines += ["", "Mode: OBSERVATION"]
    return "\n".join(lines)

def cmd_signals(_args):
    """Redirige vers Portfolio Bot — domaine incorrect pour CryptoRadar."""
    return (
        "\U0001f4e1 CryptoRadar — domaine marché uniquement\n\n"
        "Les signaux avec Entry/SL/TP appartiennent au domaine Portfolio.\n"
        "Utilise \U0001f4bc Mon Portfolio pour consulter les niveaux d'exécution.\n\n"
        "Commandes disponibles ici : /scan /top50 /longs /shorts /symbol /lmi"
    )

def cmd_top50(_args):
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=60)[:50]
    if not stats:
        return "\U0001f4ca TOP50 — Aucun symbole"
    lines = ["\U0001f4ca TOP 50 — conf>=60 (24h)\n"]
    for i, s in enumerate(stats, 1):
        icon = "\U0001f7e2" if s["dominant_side"] == "LONG" else "\U0001f534" if s["dominant_side"] == "SHORT" else "⚪"
        lines.append(f"{i:2d}. {icon} {s['symbol']:12s} {s['dominant_side']:5s} {s['dominance_pct']:3.0f}% | conf {s['avg_confidence']:.0f} | {s['regime']}")
    return "\n".join(lines)


def cmd_longs(_args):
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=65)
    longs = [s for s in stats if s["dominant_side"] == "LONG"][:15]
    if not longs:
        return "\U0001f7e2 LONGS — Aucun"
    lines = [f"\U0001f7e2 TOP LONGS — {len(longs)} symboles (24h)\n"]
    for s in longs:
        lines.append(f"\U0001f7e2 {s['symbol']} | {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        lines.append("")
    return "\n".join(lines)


def cmd_shorts(_args):
    packets = load_recent_packets(24)
    stats = compute_symbol_stats(packets, min_conf=65)
    shorts = [s for s in stats if s["dominant_side"] == "SHORT"][:15]
    if not shorts:
        return "\U0001f534 SHORTS — Aucun"
    lines = [f"\U0001f534 TOP SHORTS — {len(shorts)} symboles (24h)\n"]
    for s in shorts:
        lines.append(f"\U0001f534 {s['symbol']} | {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        lines.append("")
    return "\n".join(lines)

def cmd_symbol(args):
    query = args.strip().upper()
    if not query:
        return "Usage: /symbol BTC  ou  /symbol BTC/USDT"
    packets = load_recent_packets(24)
    matching = [p for p in packets if query in p.get("symbol", "").upper()]
    if not matching:
        return f"Aucun signal pour '{query}' (24h)"
    sym_name = matching[0].get("symbol", query)
    confs = [p.get("confidence", 0) for p in matching]
    sides = [p.get("side", "") for p in matching]
    longs = sum(1 for s in sides if s in ("BUY", "LONG"))
    shorts = sum(1 for s in sides if s in ("SELL", "SHORT"))
    regimes = defaultdict(int)
    for p in matching:
        regimes[p.get("regime", "?")] += 1
    dom_regime = max(regimes, key=regimes.get)
    lines = [f"\U0001f50d {sym_name} — detail 24h\n",
        f"Signals: {len(matching)}",
        f"Conf:    avg {sum(confs)/len(confs):.1f} | max {max(confs):.0f} | min {min(confs):.0f}",
        f"LONG:    {longs}  |  SHORT: {shorts}",
        f"Regime:  {dom_regime}"]
    return "\n".join(lines)

def cmd_status(_args):
    """Redirige vers les outils Ops — domaine incorrect pour CryptoRadar."""
    return (
        "\U0001f4e1 CryptoRadar — domaine marché uniquement\n\n"
        "Les métriques système (fichiers DB, taille, uptime) appartiennent "
        "au domaine Ops/Watchdog.\n\n"
        "Commandes disponibles ici : /scan /top50 /longs /shorts /symbol /lmi"
    )

def cmd_lmi(args):
    """Live Market Interaction — observation microstructure (lecture seule)."""
    try:
        from trade_analysis.integrations.radar_adapter import (
            format_lmi_message, format_lmi_overview)
    except Exception:
        return "Module LMI indisponible."
    sym = args.strip().split()[0] if args.strip() else ""
    if sym:
        return format_lmi_message(sym)
    return format_lmi_overview()

def cmd_help(_args):
    return ("\U0001f916 CryptoRadar — Observatoire marché\n\n"
        "/scan        Top 10 opportunités par score (24h)\n"
        "/scan 5      Top N symboles\n"
        "/top50       Top 50 compact (conf>=60)\n"
        "/longs       Opportunités directionnelles LONG\n"
        "/shorts      Opportunités directionnelles SHORT\n"
        "/symbol BTC  Analyse détaillée d'un symbole\n"
        "/lmi         Vue microstructure marché (tous)\n"
        "/lmi BTC     Microstructure d'un symbole\n"
        "/help        Cette aide\n\n"
        "Domaine : découverte d'opportunités. Pas de portfolio ni de métriques système.")

COMMANDS = {"scan": cmd_scan, "top50": cmd_top50,
    "longs": cmd_longs, "shorts": cmd_shorts, "symbol": cmd_symbol,
    "lmi": cmd_lmi, "help": cmd_help, "start": cmd_help,
    # Commandes hors-domaine — redirigent vers le bot approprié
    "signals": cmd_signals, "status": cmd_status}

def poll_loop():
    print(f"[RadarBot] Demarre — polling Telegram...")
    offset = 0
    while True:
        try:
            result = tg_request("getUpdates", {"timeout": 30, "offset": offset})
            updates = result.get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not text or not chat_id:
                    continue
                if ALLOWED_CHATS and chat_id not in ALLOWED_CHATS:
                    print(f"[RadarBot] Chat non autorise: {chat_id}")
                    continue
                if not text.startswith("/"):
                    continue
                parts = text[1:].split(maxsplit=1)
                cmd = parts[0].lower().split("@")[0]
                args = parts[1] if len(parts) > 1 else ""
                handler = COMMANDS.get(cmd)
                if handler:
                    print(f"[RadarBot] /{cmd} {args} (chat={chat_id})")
                    try:
                        reply = handler(args)
                        send_message(chat_id, reply)
                    except Exception as exc:
                        print(f"[RadarBot] Erreur: {exc}")
                        traceback.print_exc()
                        send_message(chat_id, f"Erreur: {exc}")
                else:
                    send_message(chat_id, f"Commande inconnue: /{cmd}\nTape /help")
        except urllib.error.URLError as e:
            print(f"[RadarBot] Erreur reseau: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[RadarBot] Erreur: {e}")
            traceback.print_exc()
            time.sleep(5)

def main():
    if not TOKEN:
        print("[ERREUR] RADAR_BOT_TOKEN manquant", file=sys.stderr)
        sys.exit(1)
    if "--once" in sys.argv:
        result = tg_request("getUpdates", {"timeout": 0})
        updates = result.get("result", [])
        print(f"[RadarBot] {len(updates)} messages en attente")
        for upd in updates:
            msg = upd.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if text.startswith("/"):
                parts = text[1:].split(maxsplit=1)
                cmd = parts[0].lower().split("@")[0]
                args = parts[1] if len(parts) > 1 else ""
                handler = COMMANDS.get(cmd)
                if handler:
                    send_message(chat_id, handler(args))
        return
    poll_loop()

if __name__ == "__main__":
    main()
