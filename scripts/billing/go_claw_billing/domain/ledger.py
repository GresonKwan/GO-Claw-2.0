"""Balanced, single-asset double-entry journal validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JournalLine:
    account_code: str
    asset_code: str
    debit: int = 0
    credit: int = 0

    def __post_init__(self) -> None:
        if self.debit < 0 or self.credit < 0:
            raise ValueError("journal amount cannot be negative")
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("each journal line must be exactly debit or credit")


def validate_balanced(lines: list[JournalLine]) -> None:
    if len(lines) < 2:
        raise ValueError("journal requires at least two lines")
    totals: dict[str, list[int]] = {}
    for line in lines:
        pair = totals.setdefault(line.asset_code, [0, 0])
        pair[0] += line.debit
        pair[1] += line.credit
    if any(debit != credit for debit, credit in totals.values()):
        raise ValueError("journal is not balanced per asset")
