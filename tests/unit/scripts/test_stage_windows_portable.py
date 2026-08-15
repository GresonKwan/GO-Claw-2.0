#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).parents[3] / "scripts" / "pack-tauri" / "stage_windows_portable.py"
)
SPEC = importlib.util.spec_from_file_location(
    "stage_windows_portable",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
stage_portable = MODULE.stage_portable


def _write_runtime_layout(binaries: Path) -> None:
    for relative in (
        "qwenpaw-backend/qwenpaw-backend.exe",
        "python-runtime/python/python.exe",
        "node-runtime/node.exe",
    ):
        path = binaries / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime")


def _write_credentials_example(tmp_path: Path) -> Path:
    path = tmp_path / "credentials.example.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "batchId": "填写批次编号",
                "llm": {
                    "providerId": "kimi-cn",
                    "modelId": "kimi-k2.5",
                    "baseUrl": "https://api.tokenbyte.ai/v1",
                    "apiKey": "填写批次 LLM API Key",
                },
                "dashscope": {
                    "compatibleBaseUrl": ("https://example.invalid/compatible-mode/v1"),
                    "apiKey": "填写批次 DashScope API Key",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_stage_portable_layout_manifest_zip_and_checksum(tmp_path):
    exe = tmp_path / "target" / "release" / "qwenpaw-desktop.exe"
    binaries = tmp_path / "binaries"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ-test")
    _write_runtime_layout(binaries)
    license_file = tmp_path / "LICENSE"
    readme_file = tmp_path / "README.txt"
    license_file.write_text("Apache-2.0\n", encoding="utf-8")
    readme_file.write_text("portable\n", encoding="utf-8")
    credentials_example_file = _write_credentials_example(tmp_path)

    output = stage_portable(
        version="2.0.1",
        exe=exe,
        binaries=binaries,
        dist=tmp_path / "dist",
        license_file=license_file,
        readme_file=readme_file,
        credentials_example_file=credentials_example_file,
    )

    root = output.stage_dir
    assert (root / "GO-CLAW-Portable.exe").read_bytes() == b"MZ-test"
    assert json.loads((root / "portable.json").read_text("utf-8")) == {
        "schemaVersion": 1,
        "clientMode": "browser",
    }
    assert output.zip_path.name == "GO-CLAW-Portable-2.0.1-Windows-x64.zip"
    expected_digest = hashlib.sha256(output.zip_path.read_bytes()).hexdigest()
    assert output.sha256_path.read_text("ascii") == (
        f"{expected_digest}  {output.zip_path.name}\n"
    )
    with zipfile.ZipFile(output.zip_path) as archive:
        names = set(archive.namelist())
    prefix = "GO-CLAW-Portable-2.0.1-Windows-x64/"
    assert prefix + "GO-CLAW-Portable.exe" in names
    assert prefix + "binaries/node-runtime/node.exe" in names
    example_path = root / "GO-CLAW-Config/credentials.example.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))
    assert example["schemaVersion"] == 1
    assert example["llm"]["apiKey"] == "填写批次 LLM API Key"
    assert example["dashscope"]["apiKey"] == "填写批次 DashScope API Key"
    assert not (root / "GO-CLAW-Config/credentials.json").exists()
    assert prefix + "GO-CLAW-Config/credentials.example.json" in names
    assert prefix + "GO-CLAW-Config/credentials.json" not in names


def test_stage_rejects_missing_runtime_entry(tmp_path):
    exe = tmp_path / "qwenpaw-desktop.exe"
    exe.write_bytes(b"MZ-test")
    binaries = tmp_path / "binaries"
    binaries.mkdir()
    license_file = tmp_path / "LICENSE"
    readme_file = tmp_path / "README.txt"
    license_file.write_text("license", encoding="utf-8")
    readme_file.write_text("readme", encoding="utf-8")
    credentials_example_file = _write_credentials_example(tmp_path)

    with pytest.raises(FileNotFoundError, match="qwenpaw-backend.exe"):
        stage_portable(
            version="2.0.1",
            exe=exe,
            binaries=binaries,
            dist=tmp_path / "dist",
            license_file=license_file,
            readme_file=readme_file,
            credentials_example_file=credentials_example_file,
        )


def test_stage_includes_explicit_batch_credentials(tmp_path):
    exe = tmp_path / "qwenpaw-desktop.exe"
    exe.write_bytes(b"MZ-test")
    binaries = tmp_path / "binaries"
    _write_runtime_layout(binaries)
    license_file = tmp_path / "LICENSE"
    readme_file = tmp_path / "README.txt"
    license_file.write_text("license", encoding="utf-8")
    readme_file.write_text("readme", encoding="utf-8")
    example = _write_credentials_example(tmp_path)
    credentials = tmp_path / "credentials.json"
    credentials.write_text('{"schemaVersion": 1}', encoding="utf-8")

    output = stage_portable(
        version="2.0.1",
        exe=exe,
        binaries=binaries,
        dist=tmp_path / "dist",
        license_file=license_file,
        readme_file=readme_file,
        credentials_example_file=example,
        credentials_file=credentials,
    )

    delivered = output.stage_dir / "GO-CLAW-Config/credentials.json"
    assert delivered.read_text(encoding="utf-8") == '{"schemaVersion": 1}'


def test_windows_workflow_materializes_batch_credentials_from_secrets():
    workflow = (
        Path(__file__).parents[3] / ".github/workflows/desktop-build.yml"
    ).read_text(encoding="utf-8")
    assert "GO_CLAW_LLM_API_KEY" in workflow
    assert "GO_CLAW_DASHSCOPE_API_KEY" in workflow
    assert '"$configDir/credentials.json"' in workflow


def test_stage_refuses_repository_root_as_dist(tmp_path):
    exe = tmp_path / "qwenpaw-desktop.exe"
    exe.write_bytes(b"MZ-test")
    binaries = tmp_path / "binaries"
    _write_runtime_layout(binaries)
    license_file = tmp_path / "LICENSE"
    readme_file = tmp_path / "README.txt"
    license_file.write_text("license", encoding="utf-8")
    readme_file.write_text("readme", encoding="utf-8")
    credentials_example_file = _write_credentials_example(tmp_path)

    with pytest.raises(ValueError, match="repository root"):
        stage_portable(
            version="2.0.1",
            exe=exe,
            binaries=binaries,
            dist=tmp_path,
            license_file=license_file,
            readme_file=readme_file,
            credentials_example_file=credentials_example_file,
            repository_root=tmp_path,
        )
