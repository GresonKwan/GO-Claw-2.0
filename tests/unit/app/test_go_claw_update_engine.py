import hashlib
import io
import json
import subprocess
from unittest.mock import Mock

import pytest

from qwenpaw.app.go_claw_update_engine import EngineClient, UpdateError


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.delenv("GO_CLAW_PROGRAM_ROOT", raising=False)
    (tmp_path / "portable.json").write_text('{"schemaVersion":1}')
    (tmp_path / "GO-CLAW-Portable.exe").write_bytes(b"MZshell")
    (tmp_path / "binaries").mkdir()
    (tmp_path / "binaries/go-claw-update-engine.exe").write_bytes(b"MZengine")
    return EngineClient(tmp_path)


def test_engine_copy_is_content_addressed_outside_slots_and_idempotent(engine):
    expected = hashlib.sha256(b"MZengine").hexdigest()
    path = engine._executable()
    assert (
        path
        == engine.root
        / "updates/engine"
        / expected
        / "go-claw-update-engine.exe"
    )
    stamp = path.stat().st_mtime_ns
    assert engine._executable() == path
    assert path.stat().st_mtime_ns == stamp


def test_engine_corrupted_cache_is_not_overwritten(engine):
    path = engine._executable()
    path.write_bytes(b"corrupt")
    with pytest.raises(UpdateError, match="HASH_MISMATCH"):
        engine._executable()
    assert path.read_bytes() == b"corrupt"


def test_engine_path_cannot_escape_product_root(engine, monkeypatch):
    monkeypatch.setenv("GO_CLAW_PROGRAM_ROOT", str(engine.root.parent))
    with pytest.raises(UpdateError, match="UNSAFE_PATH"):
        engine._executable()
    assert not (engine.root / "updates").exists()


def test_engine_refuses_invalid_product_before_writing(engine):
    (engine.root / "portable.json").write_text('{"schemaVersion":99}')
    with pytest.raises(UpdateError, match="INVALID_PRODUCT_ROOT"):
        engine._executable()
    assert not (engine.root / "updates").exists()


def test_engine_spawn_is_argv_hidden_and_does_not_pass_customer_secret(
    engine, monkeypatch
):
    monkeypatch.setenv("GO_CLAW_BILLING_TOKEN", "secret-never-child")
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    engine._spawn("install", {"root": str(engine.root)}, output=False)
    args, kwargs = launch.call_args
    assert isinstance(args[0], list) and args[0][-1] == str(engine.root)
    assert kwargs["shell"] is False and kwargs["close_fds"]
    assert "GO_CLAW_BILLING_TOKEN" not in kwargs["env"]
    assert kwargs["stdin"] == kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["creationflags"] == getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )


@pytest.mark.parametrize(
    "raw,code,error",
    [
        (b"not json", 0, "INVALID_ENGINE_RESPONSE"),
        (json.dumps({"error": "C:/secret/path"}).encode(), 1, "ENGINE_FAILED"),
        (b"a" * (1024 * 1024 + 1), 0, "INVALID_ENGINE_RESPONSE"),
    ],
    ids=["non-json", "redacted-error", "oversized"],
)
def test_engine_output_bounded_and_errors_redacted(
    engine, monkeypatch, raw, code, error
):
    child = Mock(stdout=io.BytesIO(raw), returncode=code)
    monkeypatch.setattr(engine, "_spawn", Mock(return_value=child))
    with pytest.raises(UpdateError, match=error):
        engine._run("discover", {}, 20)


@pytest.mark.asyncio
async def test_install_launch_is_detached_and_not_waited(engine, monkeypatch):
    child = Mock()
    spawn = Mock(return_value=child)
    monkeypatch.setattr(engine, "_spawn", spawn)
    assert (
        await engine.install(
            {"transactionId": "id", "targetManifestSha256": "a" * 64}
        )
        is child
    )
    child.wait.assert_not_called()
    child.kill.assert_not_called()
    assert spawn.call_args.args[0] == "install"
