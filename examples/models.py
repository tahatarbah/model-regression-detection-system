"""Toy classical models for the iris demo suite."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = ["sepal_length", "sepal_width", "petal_length", "petal_width"]


def _data_path() -> Path:
    return Path(__file__).resolve().parent / "iris.csv"


def train_and_save(out_dir: Path | None = None) -> tuple[Path, Path]:
    out_dir = out_dir or Path(__file__).resolve().parent
    df = pd.read_csv(_data_path())
    X = df[FEATURE_COLUMNS]
    y = df["species"]

    good = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500)),
        ]
    )
    good.fit(X, y)

    # Intentionally weak: k=1 on unscaled noisy-ish neighbor with tiny k on wrong metric
    bad = KNeighborsClassifier(n_neighbors=1, metric="euclidean")
    # Train only on first 30 rows to make it worse on full eval
    bad.fit(X.iloc[:30], y.iloc[:30])

    good_path = out_dir / "iris_good.joblib"
    bad_path = out_dir / "iris_bad.joblib"
    joblib.dump(good, good_path)
    joblib.dump(bad, bad_path)
    return good_path, bad_path


def good_clf():
    """Load good model — usable as module:callable."""
    path = Path(__file__).resolve().parent / "iris_good.joblib"
    if not path.exists():
        train_and_save()
    return joblib.load(path)


def bad_clf():
    path = Path(__file__).resolve().parent / "iris_bad.joblib"
    if not path.exists():
        train_and_save()
    return joblib.load(path)


if __name__ == "__main__":
    g, b = train_and_save()
    print(f"Wrote {g} and {b}")
