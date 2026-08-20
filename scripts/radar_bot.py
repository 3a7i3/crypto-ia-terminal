#!/usr/bin/env python3
"""radar_bot.py — Bot Telegram interactif CryptoRadar. LECTURE SEULE."""

from __future__ import annotations
import json, os, sys, threading, time, traceback, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DP_DIR = Path(os.getenv("DP_LOG_DIR", str(PROJECT / "databases")))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ALLOWED_CHATS = {CHAT_ID} if CHAT_ID else set()

# ── Alertes auto sur seuils (observer strict, ADR-0007) ─────────────────
# Seuils : desactive si <=0 (loss_pct) ou <=0 (signal_conf) ou <=0 (interval)
ALERT_PNL_LOSS_PCT = float(os.getenv("RADAR_ALERT_PNL_LOSS_PCT", "-3.0"))
ALERT_SIGNAL_CONF_MIN = float(os.getenv("RADAR_ALERT_SIGNAL_CONF_MIN", "90"))
ALERT_INTERVAL_S = int(os.getenv("RADAR_ALERT_INTERVAL_S", "300"))
# Anti-spam : ne pas realerter le meme (symbole, type) avant N secondes
ALERT_DEDUP_S = int(os.getenv("RADAR_ALERT_DEDUP_S", "3600"))

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
        latest = ([p for p in pks if p.get("entry_price")] or pks)[-1]
        results.append({"symbol": sym, "avg_confidence": round(avg, 1),
            "max_confidence": max(confs), "n_signals": len(pks),
            "dominant_side": dom, "dominance_pct": round(dom_pct, 0),
            "regime": regime, "entry": latest.get("entry_price"),
            "sl": latest.get("stop_loss"), "tp": latest.get("take_profit"),
            "r_multiple": latest.get("r_multiple")})
    results.sort(key=lambda r: r["avg_confidence"], reverse=True)
    return results

def extract_signals(packets):
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
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\U0001f4ca SCAN — {now_str}", f"Top {len(stats)} (24h, conf>=65)\n"]
    for s in stats:
        icon = "\U0001f7e2" if s["dominant_side"] == "LONG" else "\U0001f534" if s["dominant_side"] == "SHORT" else "⚪"
        lines.append(f"{icon} {s['symbol']} | {s['dominant_side']} {s['dominance_pct']:.0f}% | conf {s['avg_confidence']:.0f} (max {s['max_confidence']:.0f}) | {s['regime']}")
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
        lines.append("")
    return "\n".join(lines)

def cmd_signals(args):
    hours = 24
    a = args.strip().lower()
    if a:
        try:
            hours = float(a.replace("h", ""))
        except ValueError:
            pass
    packets = load_recent_packets(hours)
    sigs = extract_signals(packets)[:15]
    if not sigs:
        return f"\U0001f4cb SIGNALS ({hours:.0f}h) — Aucun signal avec Entry/SL/TP"
    lines = [f"\U0001f4cb SIGNALS — {len(sigs)} signaux ({hours:.0f}h)\n"]
    for s in sigs:
        icon = "\U0001f7e2" if s["side"] in ("BUY", "LONG") else "\U0001f534"
        d = "LONG" if s["side"] in ("BUY", "LONG") else "SHORT"
        r_str = f" | R:R {s['r_multiple']:.1f}" if s.get("r_multiple") else ""
        lines.append(f"{icon} {s['symbol']} {d}\n   Entry: {s['entry']:.6g}\n   SL: {s['sl']:.6g} (-{s['risk_pct']:.1f}%) | TP: {s['tp']:.6g} (+{s['reward_pct']:.1f}%)\n   Conf: {s['confidence']:.0f}/100 | {s['regime']}{r_str}\n")
    return "\n".join(lines)

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
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
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
        if s.get("entry"):
            lines.append(f"   Entry: {s['entry']:.6g} | SL: {s['sl']:.6g} | TP: {s['tp']:.6g}")
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
    with_levels = [p for p in matching if p.get("entry_price")]
    lines = [f"\U0001f50d {sym_name} — detail 24h\n",
        f"Signals: {len(matching)}",
        f"Conf:    avg {sum(confs)/len(confs):.1f} | max {max(confs):.0f} | min {min(confs):.0f}",
        f"LONG:    {longs}  |  SHORT: {shorts}",
        f"Regime:  {dom_regime}"]
    if with_levels:
        last = with_levels[-1]
        e, sl, tp = last["entry_price"], last.get("stop_loss", 0), last.get("take_profit", 0)
        side = last.get("side", "?")
        icon = "\U0001f7e2" if side in ("BUY", "LONG") else "\U0001f534"
        d = "LONG" if side in ("BUY", "LONG") else "SHORT"
        lines.append(f"\n{icon} Dernier signal: {d}")
        lines.append(f"   Entry: {e:.6g}")
        lines.append(f"   SL:    {sl:.6g}")
        lines.append(f"   TP:    {tp:.6g}")
        r = last.get("r_multiple")
        if r:
            lines.append(f"   R:R    {r:.1f}")
    return "\n".join(lines)

def load_live_positions():
    """Lit databases/live_snapshot.json (ecrit chaque cycle par advisor_loop)."""
    fp = DP_DIR / "live_snapshot.json"
    if not fp.exists():
        return []
    try:
        snap = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []
    return snap.get("positions", []) or []


def pnl_at_price(pos, price):
    """(pnl_pct, pnl_usd) hypothetiques pour une position ouverte a un prix donne."""
    entry = float(pos.get("entry", 0) or 0)
    if entry <= 0:
        return 0.0, 0.0
    side = str(pos.get("side", "")).lower()
    lev = float(pos.get("leverage", 1) or 1)
    size_usd = float(pos.get("size_usd", 0) or 0)
    if side in ("long", "buy"):
        pct = (price - entry) / entry
    elif side in ("short", "sell"):
        pct = (entry - price) / entry
    else:
        return 0.0, 0.0
    return round(pct * 100, 4), round(pct * size_usd * lev, 2)


def cmd_impact(args):
    """/impact <symbole> <prix>  |  /impact <symbole>  |  /impact  (agrege toutes)"""
    parts = args.strip().split()
    symbol = parts[0].upper() if parts else ""
    price = 0.0
    if len(parts) >= 2:
        try:
            price = float(parts[1])
        except ValueError:
            return f"Prix invalide: {parts[1]!r}"
    positions = load_live_positions()
    if symbol:
        q = symbol.replace("/", "").replace("-", "")
        positions = [p for p in positions
                     if q in str(p.get("symbol", "")).upper().replace("/", "").replace("-", "")]
    if not positions:
        return f"IMPACT — Aucune position ouverte{' pour ' + symbol if symbol else ''}"
    n_profit = n_loss = 0
    total_usd = sum_pct = 0.0
    details = []
    for p in positions:
        use_price = price if price > 0 else float(p.get("current", p.get("entry", 0)) or 0)
        pct, usd = pnl_at_price(p, use_price)
        if pct > 0:
            n_profit += 1
        else:
            n_loss += 1
        total_usd += usd
        sum_pct += pct
        details.append((p.get("symbol", "?"), str(p.get("side", "")).upper(),
                        use_price, pct, usd))
    n = len(positions)
    header = f"\U0001f4ca IMPACT — {symbol or 'toutes positions'}"
    if price > 0:
        header += f" @ {price:g}"
    else:
        header += " @ prix live"
    lines = [header, ""]
    lines.append(f"Positions: {n}  |  En profit: {n_profit} ({100 * n_profit / n:.0f}%)  |  En perte: {n_loss}")
    lines.append(f"Total PnL: {total_usd:+.2f} $  |  Avg PnL: {sum_pct / n:+.2f}%")
    lines.append("")
    for sym, side, px, pct, usd in details[:20]:
        icon = "\U0001f7e2" if pct > 0 else "\U0001f534"
        lines.append(f"{icon} {sym} {side} @ {px:g} -> {pct:+.2f}% ({usd:+.2f} $)")
    if n > 20:
        lines.append(f"... +{n - 20} autres")
    return "\n".join(lines)


def cmd_portfolio(_args):
    """/portfolio -- snapshot instantane des positions ouvertes."""
    positions = load_live_positions()
    if not positions:
        return "\U0001f4bc PORTFOLIO — Aucune position ouverte"
    total_pnl_usd = 0.0
    with_pct = []
    for p in positions:
        pct = float(p.get("pnl_pct", 0) or 0)
        usd = float(p.get("pnl_usd", 0) or 0)
        total_pnl_usd += usd
        with_pct.append((p.get("symbol", "?"), str(p.get("side", "")).upper(),
                         float(p.get("entry", 0) or 0), float(p.get("current", 0) or 0),
                         pct, usd, float(p.get("leverage", 1) or 1)))
    with_pct.sort(key=lambda x: x[4], reverse=True)
    n = len(positions)
    n_profit = sum(1 for x in with_pct if x[4] > 0)
    lines = ["\U0001f4bc PORTFOLIO — snapshot live", "",
             f"Positions ouvertes: {n}",
             f"En profit: {n_profit} ({100 * n_profit / n:.0f}%)  |  En perte: {n - n_profit}",
             f"Total PnL: {total_pnl_usd:+.2f} $", ""]
    lines.append("\U0001f4c8 TOP 3 GAINERS")
    for sym, side, entry, cur, pct, usd, lev in with_pct[:3]:
        icon = "\U0001f7e2" if side.startswith("L") else "\U0001f534"
        lines.append(f"{icon} {sym} {side} x{lev:.0f} | {pct:+.2f}% ({usd:+.2f} $) | {entry:g} -> {cur:g}")
    lines.append("")
    lines.append("\U0001f4c9 TOP 3 LOSERS")
    for sym, side, entry, cur, pct, usd, lev in with_pct[-3:][::-1]:
        icon = "\U0001f7e2" if side.startswith("L") else "\U0001f534"
        lines.append(f"{icon} {sym} {side} x{lev:.0f} | {pct:+.2f}% ({usd:+.2f} $) | {entry:g} -> {cur:g}")
    return "\n".join(lines)


def cmd_status(_args):
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    fp = DP_DIR / f"decision_packets_{today}.jsonl"
    n_today = 0
    last_ts = ""
    if fp.exists():
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n_today += 1
                try:
                    p = json.loads(line)
                    ts = p.get("created_at", "")
                    if ts:
                        last_ts = ts
                except Exception:
                    pass
    db_path = PROJECT / "databases" / "market_data.sqlite"
    db_size = db_path.stat().st_size if db_path.exists() else 0
    dp_files = sorted(DP_DIR.glob("decision_packets_*.jsonl"))
    n_files = len(dp_files)
    total_size = sum(f.stat().st_size for f in dp_files)
    lines = [f"STATUS — {now.strftime('%Y-%m-%d %H:%M UTC')}\n",
        f"Packets aujourd'hui: {n_today}",
        f"Dernier packet:      {last_ts[:19] if last_ts else '?'}",
        f"Fichiers DP:         {n_files} ({total_size / 1e9:.1f} GB)",
        f"market_data.sqlite:  {db_size / 1e6:.1f} MB"]
    return "\n".join(lines)

def cmd_help(_args):
    return ("\U0001f916 CryptoRadar Bot\n\n"
        "/scan        Top 10 par confiance (24h)\n"
        "/scan 5      Top N symboles\n"
        "/signals     Signaux avec Entry/SL/TP (24h)\n"
        "/signals 4h  Signaux des N dernieres heures\n"
        "/top50       Top 50 compact\n"
        "/longs       Uniquement les LONG\n"
        "/shorts      Uniquement les SHORT\n"
        "/symbol BTC  Detail d'un symbole\n"
        "/portfolio   Snapshot live positions ouvertes\n"
        "/impact SYM P  PnL hypothetique des positions a prix P\n"
        "/status      Etat du systeme\n"
        "/help        Cette aide")

COMMANDS = {"scan": cmd_scan, "signals": cmd_signals, "top50": cmd_top50,
    "longs": cmd_longs, "shorts": cmd_shorts, "symbol": cmd_symbol,
    "portfolio": cmd_portfolio, "impact": cmd_impact,
    "status": cmd_status, "help": cmd_help, "start": cmd_help}


# ── Alertes auto sur seuils (thread daemon, observer strict) ─────────────
_alert_last_sent: dict[str, float] = {}


def _should_alert(key):
    """True si l'alerte `key` n'a pas ete envoyee dans les ALERT_DEDUP_S dernieres s."""
    last = _alert_last_sent.get(key, 0.0)
    if time.time() - last < ALERT_DEDUP_S:
        return False
    _alert_last_sent[key] = time.time()
    return True


def _check_and_alert():
    """Une passe : verifie positions ouvertes + derniers signaux, envoie alertes."""
    if not CHAT_ID:
        return
    # 1. Positions ouvertes -- alerte si PnL < seuil
    if ALERT_PNL_LOSS_PCT < 0:
        for p in load_live_positions():
            pct = float(p.get("pnl_pct", 0) or 0)
            sym = str(p.get("symbol", "?"))
            if pct <= ALERT_PNL_LOSS_PCT and _should_alert(f"pnl_loss:{sym}"):
                side = str(p.get("side", "")).upper()
                usd = float(p.get("pnl_usd", 0) or 0)
                cur = float(p.get("current", 0) or 0)
                sl = float(p.get("sl", 0) or 0)
                msg = (f"⚠️ ALERTE PnL — {sym} {side}\n"
                       f"PnL: {pct:+.2f}% ({usd:+.2f} $) <= seuil {ALERT_PNL_LOSS_PCT:g}%\n"
                       f"Prix: {cur:g} | SL: {sl:g}")
                try:
                    send_message(CHAT_ID, msg)
                except Exception as exc:
                    print(f"[RadarBot][alert] send failed: {exc}")
    # 2. Signaux recents -- alerte si confidence >= seuil
    if ALERT_SIGNAL_CONF_MIN > 0:
        try:
            packets = load_recent_packets(1)
            for s in extract_signals(packets):
                if s["confidence"] < ALERT_SIGNAL_CONF_MIN:
                    continue
                key = f"signal:{s['symbol']}:{s['side']}:{round(s['entry'], 4)}"
                if not _should_alert(key):
                    continue
                icon = "\U0001f7e2" if s["side"] in ("BUY", "LONG") else "\U0001f534"
                d = "LONG" if s["side"] in ("BUY", "LONG") else "SHORT"
                msg = (f"\U0001f680 SIGNAL FORT — conf {s['confidence']:.0f}/100\n"
                       f"{icon} {s['symbol']} {d}\n"
                       f"Entry: {s['entry']:g} | SL: {s['sl']:g} (-{s['risk_pct']:.1f}%)\n"
                       f"TP: {s['tp']:g} (+{s['reward_pct']:.1f}%) | {s['regime']}")
                try:
                    send_message(CHAT_ID, msg)
                except Exception as exc:
                    print(f"[RadarBot][alert] send failed: {exc}")
        except Exception as exc:
            print(f"[RadarBot][alert] scan signals failed: {exc}")


def alerts_loop():
    """Boucle background pour les alertes auto. Idempotent, ne bloque jamais le poll."""
    print(f"[RadarBot] Alerts loop actif (interval={ALERT_INTERVAL_S}s, "
          f"loss<={ALERT_PNL_LOSS_PCT}%, conf>={ALERT_SIGNAL_CONF_MIN})")
    while True:
        try:
            _check_and_alert()
        except Exception as exc:
            print(f"[RadarBot][alerts_loop] {exc}")
            traceback.print_exc()
        time.sleep(max(60, ALERT_INTERVAL_S))

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
        print("[ERREUR] TELEGRAM_BOT_TOKEN manquant")
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
    # Alertes auto en thread daemon (interval > 0 = actif)
    if ALERT_INTERVAL_S > 0:
        threading.Thread(target=alerts_loop, daemon=True, name="radar-alerts").start()
    poll_loop()

if __name__ == "__main__":
    main()
