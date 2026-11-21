import { useEffect, useState } from "react";

type Point = { at: number; value: number };
type Publication = { status: "FRESH" | "STALE" | "UNAVAILABLE"; latest: Point | null; points: Point[] };
const periods = [1, 7, 30] as const;
const day = 86_400_000;
const dateLabel = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", timeZone: "UTC" });
const timeLabel = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
const balanceLabel = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function PaperBalanceChart() {
  const [days, setDays] = useState<(typeof periods)[number]>(1);
  const [now, setNow] = useState(Date.now);
  const [result, setResult] = useState<{ days: number; publication: Publication }>();
  const [failedPeriod, setFailedPeriod] = useState<number>();
  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const response = await fetch(`/api/operator/v1/paper-balance-history?days=${days}`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw Error("Historique indisponible");
        const publication: Publication = await response.json();
        if (!controller.signal.aborted) {
          setResult({ days, publication });
          setFailedPeriod(undefined);
        }
      } catch {
        if (!controller.signal.aborted) setFailedPeriod(days);
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(poll, 15_000);
      }
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [days]);
  const publication = result?.days === days ? result.publication : undefined;
  const latest = result?.publication.latest;
  const start = now - days * day;
  const points = (publication?.points ?? []).filter(p => p.at >= start && p.at <= now);
  const values = points.map(p => p.value);
  const lo = values.reduce((a, b) => Math.min(a, b), Infinity);
  const hi = values.reduce((a, b) => Math.max(a, b), -Infinity);
  const coords = points.map(p => [12 + 576 * (p.at - start) / (days * day), hi === lo ? 72 : 126 - 108 * (p.value - lo) / (hi - lo)]);
  const last = coords.at(-1);
  const label = days === 1 ? timeLabel : dateLabel;
  const minutes = latest ? Math.max(0, Math.floor((now - latest.at) / 60_000)) : undefined;
  const age = minutes === undefined ? "" : minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`;
  const status = failedPeriod === days || publication?.status === "UNAVAILABLE" ? "Source indisponible"
    : publication?.status === "STALE" ? "Dernière publication périmée" : publication ? "Source actualisée" : "Chargement";
  return <section className="fin-panel paper-balance" aria-label="Solde PAPER disponible">
    <h2>Solde PAPER disponible</h2>
    <div className="paper-balance-value">{latest ? balanceLabel.format(latest.value) : "—"} <small>USDT</small></div>
    <p className="source-date">{status}{latest && <> · observation il y a {age}</>}</p>
    <div className="paper-balance-periods" role="group" aria-label="Période du solde">
      {periods.map(period => <button key={period} type="button" aria-pressed={days === period} onClick={() => setDays(period)}>{period} j</button>)}
    </div>
    {last ? <svg viewBox="0 0 600 144" role="img" aria-label={`Solde PAPER observé, ${points.length} point(s) sur ${days} jour(s)`}>
      <path d="M12 126H588" stroke="var(--bg-border)" />
      {coords.length > 1 && <polyline points={coords.map(p => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />}
      <circle cx={last[0]} cy={last[1]} r="4" fill="currentColor" />
    </svg> : <p className="paper-balance-empty">Aucune observation sur cette période.</p>}
    <div className="paper-balance-axis" aria-label="Axe du temps UTC">
      {[start, (start + now) / 2, now].map(at => <time key={at} dateTime={new Date(at).toISOString()}>{label.format(at)}</time>)}
      <span>UTC</span>
    </div>
    {points.length > 0 && <p className="source-date">Observations disponibles depuis le {dateLabel.format(points[0].at)} à {timeLabel.format(points[0].at)} UTC.</p>}
  </section>;
}
