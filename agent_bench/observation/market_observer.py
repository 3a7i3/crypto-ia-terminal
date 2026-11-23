"""Observateur Marché : contrôles en lecture seule des données de marché servies sur le VPS.

Famille Observation, décision opérateur 2026-11-23 : observer les DONNÉES du VPS (pas le code
GitHub). L'agent lit des réponses GET déjà servies par la machine (scanner Spot Radar, route
/market de l'API opérateur) et en tire des constats. Il ne recalcule aucune valeur d'autorité :
il compare des champs publiés à des seuils déclarés dans la mission, et une donnée illisible
reste UNKNOWN, jamais 0.

`analyse(responses, mission, now_ms)` est pure : `responses` associe l'identifiant d'une source
de la mission à `{"http_status": int|None, "body": objet JSON|None, "error": str|None}`.
"""
from __future__ import annotations

import math

RUNTIME_REPORT_CONTRACT = "cat.observation.runtime-report.v1"
VERDICTS = ("OK", "WARN", "ALERT", "UNKNOWN")
# Sources attendues dans une mission Marché (identifiants fixes, URL dans la mission).
SOURCE_IDS = ("scanner_health", "scanner_rows", "operator_market")


def _int(v):
    """Entier depuis un nombre ou une chaîne décimale ; None sinon (jamais 0 par défaut)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v)
    if isinstance(v, float) and math.isfinite(v):
        return int(v)
    return None


def _check(code, verdict, *, source, field, observed=None, threshold=None, note=None):
    return {"code": code, "verdict": verdict, "source": source, "field": field,
            "observed": observed, "threshold": threshold, "note": note}


def _age_verdict(age_s, warn_s, alert_s):
    if age_s is None:
        return "UNKNOWN"
    return "OK" if age_s <= warn_s else "WARN" if age_s <= alert_s else "ALERT"


def _scanner_checks(body, th, now_ms):
    src = "scanner_health"
    out, metrics = [], {}
    col = body.get("collector") if isinstance(body.get("collector"), dict) else {}
    state = col.get("state") if isinstance(col.get("state"), str) else None
    last_ok = _int(col.get("last_success_ms"))
    age_s = round((now_ms - last_ok) / 1000, 1) if last_ok is not None else None
    metrics["collector_state"] = state
    metrics["collector_last_success_age_s"] = age_s
    # Les campagnes du collecteur s'enchaînent avec une courte pause : un état non RUNNING
    # n'est une alerte que si la dernière collecte réussie est elle-même ancienne.
    v_age = _age_verdict(age_s, th["collector_warn_s"], th["collector_alert_s"])
    out.append(_check("COLLECTOR_FRESHNESS", v_age, source=src, field="collector.last_success_ms",
                      observed=age_s, threshold=[th["collector_warn_s"], th["collector_alert_s"]],
                      note="âge de la dernière collecte réussie (s)"))
    if state is None:
        v_state = "UNKNOWN"
    elif state == "RUNNING":
        v_state = "OK"
    else:
        v_state = "WARN" if v_age == "OK" else "ALERT"
    out.append(_check("COLLECTOR_STATE", v_state, source=src, field="collector.state", observed=state,
                      threshold="RUNNING"))
    fails = _int(col.get("failures"))
    metrics["collector_failures"] = fails
    out.append(_check("COLLECTOR_FAILURES", "UNKNOWN" if fails is None else "OK" if fails == 0 else "WARN",
                      source=src, field="collector.failures", observed=fails, threshold=0))
    fi = col.get("fault_injection")
    out.append(_check("FAULT_INJECTION_OFF", "OK" if fi is False else "ALERT" if fi is True else "UNKNOWN",
                      source=src, field="collector.fault_injection", observed=fi, threshold=False))
    ek = body.get("evidence_kind")
    out.append(_check("EVIDENCE_PUBLIC_OBSERVED", "OK" if ek == "PUBLIC_OBSERVED" else "UNKNOWN" if ek is None else "ALERT",
                      source=src, field="evidence_kind", observed=ek, threshold="PUBLIC_OBSERVED"))
    states = body.get("states") if isinstance(body.get("states"), dict) else None
    selected = _int(body.get("selected_instruments"))
    metrics["instruments_selected"] = selected
    if states is None or selected is None:
        out.append(_check("INSTRUMENTS_LIVE", "UNKNOWN", source=src, field="states"))
    else:
        counts = {k: _int(states.get(k)) for k in ("LIVE", "STALE", "DISCONNECTED", "UNRESOLVED", "SYNTHETIC")}
        metrics["instruments_by_state"] = counts
        live = counts["LIVE"]
        if live is None:
            v = "UNKNOWN"
        elif counts["SYNTHETIC"]:
            v = "ALERT"
        elif live == selected:
            v = "OK"
        else:
            v = "WARN" if selected and live / selected >= th["live_ratio_warn"] else "ALERT"
        out.append(_check("INSTRUMENTS_LIVE", v, source=src, field="states.LIVE",
                          observed=f"{live}/{selected}" if live is not None else None,
                          threshold=th["live_ratio_warn"],
                          note=", ".join(f"{k} {n}" for k, n in counts.items() if n and k != "LIVE") or None))
    avail, exp = _int(body.get("histories_available")), _int(body.get("histories_expected"))
    metrics["histories"] = f"{avail}/{exp}" if avail is not None and exp is not None else None
    out.append(_check("HISTORY_COVERAGE",
                      "UNKNOWN" if avail is None or not exp else "OK" if avail >= exp else "WARN",
                      source=src, field="histories_available", observed=metrics["histories"], threshold="100 %"))
    un = body.get("unavailable")
    out.append(_check("UNAVAILABLE_INSTRUMENTS",
                      "UNKNOWN" if not isinstance(un, list) else "OK" if not un else "WARN",
                      source=src, field="unavailable", observed=len(un) if isinstance(un, list) else None,
                      threshold=0, note=", ".join(str(u)[:24] for u in un[:5]) if isinstance(un, list) and un else None))
    clock = body.get("clock") if isinstance(body.get("clock"), dict) else {}
    rtt = _int(clock.get("rtt_ms"))
    metrics["exchange_rtt_ms"] = rtt
    out.append(_check("EXCHANGE_RTT", "UNKNOWN" if rtt is None else "OK" if rtt <= th["rtt_warn_ms"] else "WARN",
                      source=src, field="clock.rtt_ms", observed=rtt, threshold=th["rtt_warn_ms"]))
    return out, metrics


def _rows_checks(body, th):
    src = "scanner_rows"
    rows = body.get("rows")
    if not isinstance(rows, list):
        return [_check("ROWS_FRESHNESS", "UNKNOWN", source=src, field="rows")], {}
    ages = [_int((r.get("freshness") or {}).get("age_ms")) for r in rows if isinstance(r, dict)]
    known = [a for a in ages if a is not None]
    worst = max(known) / 1000 if known else None
    issues = sorted({str(r.get("data_issue"))[:40] for r in rows if isinstance(r, dict) and r.get("data_issue")})
    not_live = sorted(str(r.get("display_symbol"))[:16] for r in rows
                      if isinstance(r, dict) and (r.get("freshness") or {}).get("state") != "LIVE")
    metrics = {"rows": len(rows), "rows_worst_age_s": worst, "rows_unknown_age": len(ages) - len(known),
               "rows_not_live": not_live[:10], "rows_data_issues": issues[:10]}
    out = [
        _check("ROWS_FRESHNESS", _age_verdict(worst, th["row_warn_s"], th["row_alert_s"]) if known else "UNKNOWN",
               source=src, field="rows[].freshness.age_ms", observed=worst,
               threshold=[th["row_warn_s"], th["row_alert_s"]],
               note=f"{len(ages) - len(known)} âge(s) inconnu(s)" if len(known) < len(ages) else None),
        _check("ROWS_NOT_LIVE", "OK" if not not_live else "WARN", source=src, field="rows[].freshness.state",
               observed=len(not_live), threshold=0, note=", ".join(not_live[:5]) or None),
        _check("ROWS_DATA_ISSUES", "OK" if not issues else "WARN", source=src, field="rows[].data_issue",
               observed=len(issues), threshold=0, note=", ".join(issues[:3]) or None),
    ]
    if body.get("complete") is not True:
        out.append(_check("ROWS_COMPLETE", "WARN" if body.get("complete") is False else "UNKNOWN",
                          source=src, field="complete", observed=body.get("complete"), threshold=True))
    return out, metrics


def _market_checks(body, th):
    src = "operator_market"
    gen = body.get("generated_at_utc")
    age = body.get("snapshot_age_s")
    age_s = round(float(age), 1) if isinstance(age, (int, float)) and not isinstance(age, bool) else None
    cls = body.get("freshness_classification")
    # Âge et classification publiés par l'API : repris tels quels, jamais recalculés.
    metrics = {"market_generated_at_utc": gen if isinstance(gen, str) else None, "market_snapshot_age_s": age_s,
               "market_freshness": cls if isinstance(cls, str) else None,
               "market_universe": _int(body.get("universe_size"))}
    v = _age_verdict(age_s, th["market_warn_s"], th["market_alert_s"])
    if cls == "STALE" and v == "OK":
        v = "WARN"
    return [_check("MARKET_SNAPSHOT_FRESHNESS", v, source=src, field="snapshot_age_s", observed=age_s,
                   threshold=[th["market_warn_s"], th["market_alert_s"]],
                   note=f"généré {gen} · classé {cls}" if gen or cls else None)], metrics


def analyse(responses: dict, mission: dict, now_ms: int) -> dict:
    """Contenu du rapport (déterministe pour des réponses et un instant donnés)."""
    th = mission["thresholds"]
    checks, metrics, unknowns, errors, sources = [], {}, [], [], []
    readers = {"scanner_health": lambda b: _scanner_checks(b, th, now_ms),
               "scanner_rows": lambda b: _rows_checks(b, th),
               "operator_market": lambda b: _market_checks(b, th)}
    read_ok = 0
    for s in mission["sources"]:
        sid = s["id"]
        r = responses.get(sid) or {}
        body, status = r.get("body"), r.get("http_status")
        sources.append({"id": sid, "endpoint": s["path"], "http_status": status, "bytes": r.get("bytes"),
                        "sha256": r.get("sha256"), "error": r.get("error")})
        if status != 200 or not isinstance(body, dict):
            # Une panne de lecture n'est pas une population vide : la source reste inconnue.
            unknowns.append({"code": "SOURCE_UNREADABLE", "source": sid,
                             "reason": r.get("error") or (f"HTTP {status}" if status else "aucune réponse")})
            checks.append(_check("SOURCE_READABLE", "UNKNOWN", source=sid, field="http_status", observed=status,
                                 threshold=200, note=r.get("error")))
            continue
        read_ok += 1
        try:
            cs, ms = readers[sid](body)
        except Exception as exc:  # noqa: BLE001 — une forme inattendue est une inconnue, pas un succès
            unknowns.append({"code": "SOURCE_SHAPE_UNEXPECTED", "source": sid, "reason": type(exc).__name__})
            continue
        checks.extend(cs)
        metrics.update(ms)
    for ch in checks:
        if ch["verdict"] == "UNKNOWN" and ch["code"] != "SOURCE_READABLE":
            unknowns.append({"code": ch["code"], "source": ch["source"], "reason": f"champ {ch['field']} absent ou illisible"})
    findings = [{"code": ch["code"], "severity": ch["verdict"], "source": ch["source"],
                 "claim": ch["note"] or f"{ch['field']} = {ch['observed']}"}
                for ch in checks if ch["verdict"] in ("WARN", "ALERT")]
    n = len(mission["sources"])
    status = "COMPLETE" if read_ok == n and not unknowns else "BLOCKED" if read_ok == 0 else "PARTIAL"
    counts = {v: sum(1 for ch in checks if ch["verdict"] == v) for v in VERDICTS}
    return {
        "contract": RUNTIME_REPORT_CONTRACT, "agent_id": mission["agent_id"], "mission_id": mission["mission_id"],
        "domain": mission["domain"], "profile": {"path": "profile:" + mission["profile"]["source_path"],
                                                  "blob_sha1": mission["profile"]["blob_sha1"]},
        "status": status, "verdict_counts": counts, "checks": checks, "findings": findings,
        "unknowns": unknowns, "metrics": metrics, "sources": sources, "errors": errors,
        "limits": ["READ_ONLY_GET_LOOPBACK", "NO_AUTHORITY_RECALCULATION", "THRESHOLDS_FROM_MISSION",
                   "REPORT_IS_NOT_SELF_CERTIFYING"],
    }
