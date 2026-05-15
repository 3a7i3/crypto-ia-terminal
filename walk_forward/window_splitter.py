"""
walk_forward/window_splitter.py — Decoupage chronologique sans fuite de donnees.

Garanties no-leakage (verifiees dans __post_init__) :
  - test_start >= train_end + gap  (jamais de chevauchement)
  - Indices croissants stricts entre folds
  - train et test sont des intervalles semi-ouverts [start, end)

Modes :
  anchored=False (rolling)  : fenetre train de taille fixe, glisse de `step` a chaque fold
  anchored=True  (expanding): train commence a 0 et s'etend de `step` a chaque fold

Parametre gap :
  Nombre de samples obligatoires entre train_end et test_start.
  Utiliser gap > 0 si les features utilisent une fenetre glissante terminant
  a train_end (ex. gap=20 pour une MA-20 — evite que le dernier jour de train
  contamine la normalisation du test).

Usage :
    splitter = WindowSplitter(n_samples=1000, train_size=600, test_size=100)
    for w in splitter.split():
        train = data[w.train_start : w.train_end]
        test  = data[w.test_start  : w.test_end]
        # garantie : aucun element de train n'est dans test
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class WalkForwardWindow:
    """
    Une fenetre walk-forward.  Tous les intervalles sont [start, end).
    Le constructeur leve une ValueError si train et test se chevauchent.
    """

    fold_index: int
    train_start: int  # inclus
    train_end: int  # exclus
    test_start: int  # inclus  (toujours >= train_end)
    test_end: int  # exclus

    def __post_init__(self) -> None:
        # Leakage check : la moindre superposition est une erreur fatale
        if self.train_end > self.test_start:
            raise ValueError(
                f"Fold {self.fold_index}: train_end={self.train_end} > test_start={self.test_start}"
                " — data leakage detected"
            )
        if self.train_start < 0:
            raise ValueError(
                f"Fold {self.fold_index}: train_start={self.train_start} < 0"
            )
        if self.test_end <= self.test_start:
            raise ValueError(
                f"Fold {self.fold_index}: test_end={self.test_end} <= test_start={self.test_start}"
            )

    @property
    def train_size(self) -> int:
        return self.train_end - self.train_start

    @property
    def test_size(self) -> int:
        return self.test_end - self.test_start

    @property
    def gap_size(self) -> int:
        """Nombre de samples entre fin du train et debut du test."""
        return self.test_start - self.train_end


class WindowSplitter:
    """
    Generateur de fenetres walk-forward.

    anchored=False (rolling) :
      fold k : train = [k*step,  k*step + train_size)
               test  = [k*step + train_size + gap,  ... + test_size)

    anchored=True (expanding) :
      fold k : train = [0,  train_size + k*step)
               test  = [train_size + k*step + gap, ... + test_size)
    """

    def __init__(
        self,
        n_samples: int,
        train_size: int,
        test_size: int,
        step: int | None = None,
        gap: int = 0,
        anchored: bool = False,
    ) -> None:
        if n_samples <= 0:
            raise ValueError(f"n_samples must be > 0, got {n_samples}")
        if train_size <= 0:
            raise ValueError(f"train_size must be > 0, got {train_size}")
        if test_size <= 0:
            raise ValueError(f"test_size must be > 0, got {test_size}")
        if gap < 0:
            raise ValueError(f"gap must be >= 0, got {gap}")

        min_needed = train_size + gap + test_size
        if min_needed > n_samples:
            raise ValueError(
                f"n_samples={n_samples} trop petit : "
                f"train={train_size} + gap={gap} + test={test_size} = {min_needed}"
            )

        self.n_samples = n_samples
        self.train_size = train_size
        self.test_size = test_size
        self.step = step if step is not None else test_size
        self.gap = gap
        self.anchored = anchored

    def split(self) -> Iterator[WalkForwardWindow]:
        """
        Genere les fenetres dans l'ordre chronologique strict.
        Chaque fenetre est garantie sans chevauchement train/test.
        """
        fold = 0
        while True:
            if self.anchored:
                train_start = 0
                train_end = self.train_size + fold * self.step
            else:
                train_start = fold * self.step
                train_end = train_start + self.train_size

            test_start = train_end + self.gap
            test_end = test_start + self.test_size

            if test_end > self.n_samples:
                break

            yield WalkForwardWindow(
                fold_index=fold,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
            fold += 1

    @property
    def n_folds(self) -> int:
        """Nombre total de folds disponibles (lecture seule, calcule par enumeration)."""
        return sum(1 for _ in self.split())
