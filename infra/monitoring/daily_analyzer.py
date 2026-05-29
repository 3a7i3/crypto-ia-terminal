"""
daily_analyzer.py — Rapport journalier d'analyse système
Surveillance simple et claire: stabilité, dérives, incidents
"""

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("daily_analyzer")


@dataclass
class SystemSnapshot:
    """Snapshot état système"""
    timestamp: float
    uptime_seconds: float
    memory_used_mb: float
    cpu_percent: float
    error_count: int
    warning_count: int
    best_strategy_name: str
    best_fitness_score: float
    force_level: float  # Pieuvre force 0-100
    system_health: str  # "GREEN", "YELLOW", "RED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DailyAnalyzer:
    """Génère rapports analysés jour/jour"""

    DB_PATH = Path("cache/daily_analysis.db")

    def __init__(self):
        self._init_db()
        self.boot_time = time.time()

    def _init_db(self):
        """Crée schéma SQLite"""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    timestamp REAL PRIMARY KEY,
                    uptime_seconds REAL,
                    memory_used_mb REAL,
                    cpu_percent REAL,
                    error_count INTEGER,
                    warning_count INTEGER,
                    best_strategy TEXT,
                    best_fitness REAL,
                    force_level REAL,
                    system_health TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_reports (
                    report_date TEXT PRIMARY KEY,
                    created_at REAL,
                    uptime_percent REAL,
                    error_count INTEGER,
                    warning_count INTEGER,
                    avg_memory_mb REAL,
                    avg_cpu_percent REAL,
                    system_health_summary TEXT,
                    force_evolution REAL,
                    incidents TEXT,  -- JSON list
                    report_json TEXT  -- Full report
                )
            """)

            conn.commit()
        log.info(f"Daily analyzer DB initialized: {self.DB_PATH}")

    def save_snapshot(self, snapshot: SystemSnapshot) -> bool:
        """Sauvegarde snapshot point-in-time"""
        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO snapshots
                    (timestamp, uptime_seconds, memory_used_mb, cpu_percent,
                     error_count, warning_count, best_strategy, best_fitness,
                     force_level, system_health)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    snapshot.timestamp,
                    snapshot.uptime_seconds,
                    snapshot.memory_used_mb,
                    snapshot.cpu_percent,
                    snapshot.error_count,
                    snapshot.warning_count,
                    snapshot.best_strategy_name,
                    snapshot.best_fitness_score,
                    snapshot.force_level,
                    snapshot.system_health,
                ))
                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to save snapshot: {e}")
            return False

    def generate_daily_report(self, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Génère rapport pour date donnée (défaut: aujourd'hui)"""
        if report_date is None:
            report_date = datetime.now().strftime("%Y-%m-%d")

        # Calcul horaires de la journée
        day_start = datetime.strptime(report_date, "%Y-%m-%d").timestamp()
        day_end = day_start + 86400

        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                # Fetch snapshots du jour
                snapshots = conn.execute("""
                    SELECT * FROM snapshots
                    WHERE timestamp >= ? AND timestamp < ?
                    ORDER BY timestamp
                """, (day_start, day_end)).fetchall()

                if not snapshots:
                    log.warning(f"No snapshots for {report_date}")
                    return None

                # Agrégations
                uptimes = [row[1] for row in snapshots]
                memories = [row[2] for row in snapshots]
                cpus = [row[3] for row in snapshots]
                errors = sum(row[4] for row in snapshots)
                warnings = sum(row[5] for row in snapshots)
                health_states = [row[9] for row in snapshots]

                avg_uptime = sum(uptimes) / len(uptimes) if uptimes else 0
                avg_memory = sum(memories) / len(memories) if memories else 0
                avg_cpu = sum(cpus) / len(cpus) if cpus else 0
                uptime_percent = 100 * (avg_uptime / 86400) if avg_uptime else 0

                # Détermine santé globale du jour
                green_count = health_states.count("GREEN")
                yellow_count = health_states.count("YELLOW")
                red_count = health_states.count("RED")
                health_summary = "🟢 STABLE" if red_count == 0 else ("🟡 DRIFT" if yellow_count > 0 else "🔴 INCIDENT")

                best_strategy = snapshots[-1][6] if snapshots else "N/A"
                best_fitness = snapshots[-1][7] if snapshots else 0.0

        except Exception as e:
            log.error(f"Failed to generate daily report: {e}")
            return None

        report: Dict[str, Any] = {
            "date": report_date,
            "generated_at": datetime.now().isoformat(),
            "summary": health_summary,
            "metrics": {
                "uptime_percent": round(uptime_percent, 2),
                "avg_memory_mb": round(avg_memory, 1),
                "avg_cpu_percent": round(avg_cpu, 2),
                "error_count": errors,
                "warning_count": warnings,
                "snapshot_count": len(snapshots),
            },
            "strategy": {
                "best_name": best_strategy,
                "best_fitness": round(best_fitness, 4),
            },
            "health_distribution": {
                "green": green_count,
                "yellow": yellow_count,
                "red": red_count,
            }
        }

        return report

    def save_daily_report(self, report: Dict[str, Any]) -> bool:
        """Sauvegarde rapport dans DB"""
        try:
            incidents_json = json.dumps(report.get("incidents", []))
            full_report = json.dumps(report)

            with sqlite3.connect(self.DB_PATH) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO daily_reports
                    (report_date, created_at, uptime_percent, error_count,
                     warning_count, avg_memory_mb, avg_cpu_percent,
                     system_health_summary, incidents, report_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    report["date"],
                    time.time(),
                    report["metrics"]["uptime_percent"],
                    report["metrics"]["error_count"],
                    report["metrics"]["warning_count"],
                    report["metrics"]["avg_memory_mb"],
                    report["metrics"]["avg_cpu_percent"],
                    report["summary"],
                    incidents_json,
                    full_report,
                ))
                conn.commit()
            log.info(f"Daily report saved: {report['date']}")
            return True
        except Exception as e:
            log.error(f"Failed to save daily report: {e}")
            return False

    def get_report_by_date(self, report_date: str) -> Optional[Dict[str, Any]]:
        """Récupère rapport sauvegardé"""
        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                row = conn.execute(
                    "SELECT report_json FROM daily_reports WHERE report_date = ?",
                    (report_date,)
                ).fetchone()

                if row:
                    return json.loads(row[0])
            return None
        except Exception as e:
            log.error(f"Failed to get report: {e}")
            return None

    def get_last_n_reports(self, n: int = 7) -> List[Dict[str, Any]]:
        """Retourne derniers N rapports"""
        try:
            with sqlite3.connect(self.DB_PATH) as conn:
                rows = conn.execute("""
                    SELECT report_json FROM daily_reports
                    ORDER BY report_date DESC LIMIT ?
                """, (n,)).fetchall()

                return [json.loads(row[0]) for row in rows]
        except Exception as e:
            log.error(f"Failed to get reports: {e}")
            return []

    def format_report_text(self, report: Dict[str, Any]) -> str:
        """Formate rapport en texte lisible"""
        lines = [
            "=" * 60,
            f"📊 DAILY REPORT — {report['date']}",
            "=" * 60,
            f"Status: {report['summary']}",
            "",
            "📈 METRICS:",
            f"  • Uptime: {report['metrics']['uptime_percent']:.1f}%",
            f"  • Memory: {report['metrics']['avg_memory_mb']:.1f}MB avg",
            f"  • CPU: {report['metrics']['avg_cpu_percent']:.1f}% avg",
            f"  • Errors: {report['metrics']['error_count']}",
            f"  • Warnings: {report['metrics']['warning_count']}",
            "",
            "🎯 STRATEGY:",
            f"  • Best: {report['strategy']['best_name']}",
            f"  • Fitness: {report['strategy']['best_fitness']:.4f}",
            "",
            "🔍 HEALTH DISTRIBUTION:",
            f"  • 🟢 Green: {report['health_distribution']['green']}",
            f"  • 🟡 Yellow: {report['health_distribution']['yellow']}",
            f"  • 🔴 Red: {report['health_distribution']['red']}",
            "=" * 60,
        ]
        return "\n".join(lines)

    def export_report_json(self, report_date: str, output_path: str) -> bool:
        """Export rapport en JSON"""
        try:
            report = self.get_report_by_date(report_date)
            if not report:
                log.error(f"No report found for {report_date}")
                return False

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2)
            log.info(f"Report exported: {output_path}")
            return True
        except Exception as e:
            log.error(f"Failed to export report: {e}")
            return False


# Singleton
_analyzer_instance: Optional[DailyAnalyzer] = None


def get_daily_analyzer() -> DailyAnalyzer:
    """Retourne instance unique"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = DailyAnalyzer()
    return _analyzer_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = get_daily_analyzer()

    # Simule snapshot
    snapshot = SystemSnapshot(
        timestamp=time.time(),
        uptime_seconds=3600,
        memory_used_mb=512,
        cpu_percent=25.5,
        error_count=2,
        warning_count=5,
        best_strategy_name="MomentumV3",
        best_fitness_score=1.45,
        force_level=75.0,
        system_health="GREEN",
    )
    analyzer.save_snapshot(snapshot)

    # Génère rapport
    report = analyzer.generate_daily_report()
    if report:
        print(analyzer.format_report_text(report))
