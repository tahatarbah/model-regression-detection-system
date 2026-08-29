"""Shared adapter protocol."""

from __future__ import annotations

from typing import Protocol

from mrds.core.schema import Example, Prediction


class ModelAdapter(Protocol):
    def predict_batch(self, examples: list[Example]) -> list[Prediction]: ...
