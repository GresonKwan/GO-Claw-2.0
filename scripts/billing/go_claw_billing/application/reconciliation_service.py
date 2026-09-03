"""Reconciliation result types."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconciliationDifference:
    severity: str
    kind: str
    reference: str
