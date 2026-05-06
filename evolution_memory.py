"""
evolution_memory.py — Stockage persistent de l'évolution génétique
Persiste: meilleurs genomes, fitness history, patterns d'apprentissage
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("evolution_memory")


@dataclass
class GenomeRecord:
    """Record d'un génome évoluté"""
    genome_id: str
    generation: int
    world: str  # "trend", "range", "crash", etc.
    fitness_score: float
    genes: Dict[str, float]  # Paramètres du génome
    timestamp: float = field(default_factory=time.time)
    win_count: int = 0  # Combien de fois ce génome a gagné
    loss_count: int = 0
    avg_return: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "genome_id": self.genome_id,
            "generation": self.generation,
            "world": self.world,
            "fitness_score": self.fitness_score,
            "genes": self.genes,
            "timestamp": self.timestamp,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "avg_return": self.avg_return,
        }


@dataclass
class IncidentPattern:
    """Pattern récurrent d'incident"""
    pattern_id: str
    incident_type: str  # "crash", "memory_leak", "slow_scan", etc.
    frequency: int  # Combien de fois observé
    first_seen: float
    last_seen: float
    severity: str  # "LOW", "MED", "HIGH", "CRIT"
    mitigation_applied: Optional[str] = None


class EvolutionMemoryDB:
    """Base de données SQLite pour mémoire d'évolution"""

    def __init__(self, db_path: str = "cache/evolution_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Crée schéma SQLite"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS genomes (
                    genome_id TEXT PRIMARY KEY,
                    generation INTEGER,
                    world TEXT,
                    fitness_score REAL,
                    genes TEXT,  -- JSON
                    timestamp REAL,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    avg_return REAL DEFAULT 0.0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    pattern_id TEXT PRIMARY KEY,
                    incident_type TEXT,
                    frequency INTEGER,
                    first_seen REAL,
                    last_seen REAL,
                    severity TEXT,
                    mitigation_applied TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS fitness_history (
                    timestamp REAL,
                    world TEXT,
                    best_fitness REAL,
                    avg_fitness REAL,
                    population_size INTEGER
                )
            """)

            conn.commit()
        log.info(f"Evolution memory DB initialized: {self.db_path}")

    def save_genome(self, genome: GenomeRecord) -> bool:
        """Sauvegarde un génome"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO genomes
                    (genome_id, generation, world, fitness_score, genes, timestamp, win_count, loss_count, avg_return)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    genome.genome_id,
                    genome.generation,
                    genome.world,
                    genome.fitness_score,
                    json.dumps(genome.genes),
                    genome.timestamp,
                    genome.win_count,
                    genome.loss_count,
                    genome.avg_return,
                ))
                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to save genome: {e}")
            return False

    def get_best_genomes(self, world: Optional[str] = None, limit: int = 10) -> List[GenomeRecord]:
        """Retourne meilleurs genomes (optionnellement par world)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if world:
                    rows = conn.execute("""
                        SELECT * FROM genomes WHERE world = ?
                        ORDER BY fitness_score DESC LIMIT ?
                    """, (world, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM genomes
                        ORDER BY fitness_score DESC LIMIT ?
                    """, (limit,)).fetchall()

            genomes = []
            for row in rows:
                genes = json.loads(row[4])
                g = GenomeRecord(
                    genome_id=row[0],
                    generation=row[1],
                    world=row[2],
                    fitness_score=row[3],
                    genes=genes,
                    timestamp=row[5],
                    win_count=row[6],
                    loss_count=row[7],
                    avg_return=row[8],
                )
                genomes.append(g)
            return genomes
        except Exception as e:
            log.error(f"Failed to get best genomes: {e}")
            return []

    def save_incident_pattern(self, pattern: IncidentPattern) -> bool:
        """Sauvegarde pattern d'incident"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO incidents
                    (pattern_id, incident_type, frequency, first_seen, last_seen, severity, mitigation_applied)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pattern.pattern_id,
                    pattern.incident_type,
                    pattern.frequency,
                    pattern.first_seen,
                    pattern.last_seen,
                    pattern.severity,
                    pattern.mitigation_applied,
                ))
                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to save incident pattern: {e}")
            return False

    def get_incident_patterns(self, min_frequency: int = 2) -> List[IncidentPattern]:
        """Retourne patterns récurrents"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("""
                    SELECT * FROM incidents WHERE frequency >= ?
                    ORDER BY frequency DESC
                """, (min_frequency,)).fetchall()

            patterns = []
            for row in rows:
                p = IncidentPattern(
                    pattern_id=row[0],
                    incident_type=row[1],
                    frequency=row[2],
                    first_seen=row[3],
                    last_seen=row[4],
                    severity=row[5],
                    mitigation_applied=row[6],
                )
                patterns.append(p)
            return patterns
        except Exception as e:
            log.error(f"Failed to get incident patterns: {e}")
            return []

    def save_fitness_snapshot(self, world: str, best_fitness: float, avg_fitness: float, pop_size: int) -> bool:
        """Sauvegarde snapshot fitness pour trending"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO fitness_history
                    (timestamp, world, best_fitness, avg_fitness, population_size)
                    VALUES (?, ?, ?, ?, ?)
                """, (time.time(), world, best_fitness, avg_fitness, pop_size))
                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to save fitness snapshot: {e}")
            return False

    def get_fitness_trend(self, world: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Retourne trending fitness sur N heures"""
        try:
            cutoff = time.time() - (hours * 3600)
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("""
                    SELECT timestamp, best_fitness, avg_fitness, population_size
                    FROM fitness_history
                    WHERE world = ? AND timestamp > ?
                    ORDER BY timestamp
                """, (world, cutoff)).fetchall()

            return [
                {
                    "timestamp": row[0],
                    "best_fitness": row[1],
                    "avg_fitness": row[2],
                    "pop_size": row[3],
                }
                for row in rows
            ]
        except Exception as e:
            log.error(f"Failed to get fitness trend: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Statistiques globales"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                genome_count = conn.execute("SELECT COUNT(*) FROM genomes").fetchone()[0]
                incident_count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
                history_count = conn.execute("SELECT COUNT(*) FROM fitness_history").fetchone()[0]

            file_size_kb = self.db_path.stat().st_size / 1024 if self.db_path.exists() else 0

            return {
                "db_path": str(self.db_path),
                "db_size_kb": file_size_kb,
                "genomes_stored": genome_count,
                "incident_patterns": incident_count,
                "fitness_snapshots": history_count,
            }
        except Exception as e:
            log.error(f"Failed to get stats: {e}")
            return {}

    def cleanup_old_records(self, days: int = 30) -> int:
        """Nettoie records > N jours"""
        try:
            cutoff = time.time() - (days * 86400)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM fitness_history WHERE timestamp < ?", (cutoff,))
                deleted = cursor.rowcount
                conn.commit()
            if deleted > 0:
                log.info(f"Cleaned {deleted} old fitness records")
            return deleted
        except Exception as e:
            log.error(f"Failed to cleanup: {e}")
            return 0


# Singleton
_db_instance: Optional[EvolutionMemoryDB] = None


def get_evolution_memory_db() -> EvolutionMemoryDB:
    """Retourne instance unique"""
    global _db_instance
    if _db_instance is None:
        _db_instance = EvolutionMemoryDB()
    return _db_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = get_evolution_memory_db()
    stats = db.get_stats()
    print(json.dumps(stats, indent=2))
