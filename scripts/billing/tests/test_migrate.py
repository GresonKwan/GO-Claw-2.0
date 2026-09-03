from pathlib import Path

import pytest
from migrate import migration_files


def test_migration_files_are_contiguous() -> None:
    directory = Path(__file__).resolve().parents[1] / "migrations"
    assert [version for version, _ in migration_files(directory)] == [1, 2, 3, 4]


def test_migration_files_reject_a_gap(tmp_path: Path) -> None:
    (tmp_path / "0001_first.sql").write_text("SELECT 1", "utf-8")
    (tmp_path / "0003_third.sql").write_text("SELECT 3", "utf-8")
    with pytest.raises(RuntimeError, match="contiguous"):
        migration_files(tmp_path)
