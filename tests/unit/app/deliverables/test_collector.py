from __future__ import annotations

from pathlib import Path

from qwenpaw.app.deliverables import collector
from qwenpaw.app.deliverables.store import DeliverablesStore


def test_candidate_requires_final_reference_and_published_is_deduplicated(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cited = workspace / "引用.txt"
    cited.write_text("one", encoding="utf-8")
    hidden = workspace / "temporary.txt"
    hidden.write_text("two", encoding="utf-8")
    published = workspace / "结果.zip"
    published.write_bytes(b"PK\x03\x04")
    store = DeliverablesStore(tmp_path / "manifests")
    monkeypatch.setattr(collector, "DeliverablesStore", lambda: store)

    token = collector.bind_turn(
        agent_id="agent-a",
        chat_id="chat-a",
        turn_id="turn-a",
        workspace_root=workspace,
    )
    try:
        collector.register_candidate(cited)
        collector.register_candidate(hidden)
        collector.register_published(published)
        collector.register_published(published)
        manifest = collector.finalize_turn("response-a", "请查看引用.txt")
    finally:
        collector.reset_turn(token)

    assert manifest is not None
    assert [item.name for item in manifest.items] == ["引用.txt", "结果.zip"]
    assert len({item.id for item in manifest.items}) == 2


def test_registration_without_turn_is_noop(tmp_path: Path) -> None:
    collector.register_published(tmp_path / "nothing")
    assert collector.finalize_turn("response", "") is None
