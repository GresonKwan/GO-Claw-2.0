"""Focused tests for one-time portable batch credential import."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from qwenpaw.app.go_claw_credentials import (
    MARKER_FILENAME,
    MEDIA_TOOL_NAMES,
    import_go_claw_batch_credentials,
)
from qwenpaw.config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    Config,
    ModelSlotConfig,
    ToolsConfig,
)

VALID_DASHSCOPE_KEY = "sk-unit-test-dashscope-key-abcdefghijklmnopqrstuvwxyz-0123456789"
VALID_PAYLOAD = {
    "schemaVersion": 1,
    "batchId": "test-batch",
    "llm": {
        "providerId": "kimi-cn",
        "modelId": "kimi-k2.5",
        "baseUrl": "https://api.tokenbyte.example/v1",
        "apiKey": "unit-test-llm-key",
    },
    "dashscope": {
        "compatibleBaseUrl": "https://dashscope.example/compatible-mode/v1",
        "apiKey": VALID_DASHSCOPE_KEY,
    },
}
UpdateCall = tuple[str, dict[str, str]]


@dataclass
class FakeProvider:
    id: str
    models: tuple[str, ...]
    api_key: str = ""
    base_url: str = ""

    def has_model(self, model_id: str) -> bool:
        return model_id in self.models


@dataclass
class FakeProviderManager:
    providers: dict[str, FakeProvider] = field(
        default_factory=lambda: {
            "kimi-cn": FakeProvider("kimi-cn", ("kimi-k2.5",)),
            "dashscope": FakeProvider("dashscope", ("qwen-max",)),
        },
    )
    update_calls: list[UpdateCall] = field(default_factory=list)
    activate_calls: list[tuple[str, str]] = field(default_factory=list)
    active_model: ModelSlotConfig | None = None
    fail_update_for: str | None = None

    @property
    def builtin_providers(self) -> dict[str, FakeProvider]:
        return self.providers

    def get_provider(self, provider_id: str) -> FakeProvider | None:
        return self.providers.get(provider_id)

    def update_provider(
        self,
        provider_id: str,
        config: dict[str, str],
    ) -> bool:
        if provider_id == self.fail_update_for:
            return False
        provider = self.providers.get(provider_id)
        if provider is None:
            return False
        provider.api_key = config["api_key"].strip()
        provider.base_url = config["base_url"].strip()
        self.update_calls.append((provider_id, dict(config)))
        return True

    async def activate_model(self, provider_id: str, model_id: str) -> None:
        self.active_model = ModelSlotConfig(
            provider_id=provider_id,
            model=model_id,
        )
        self.activate_calls.append((provider_id, model_id))

    def load_provider(
        self,
        provider_id: str,
        is_builtin: bool = False,
    ) -> FakeProvider | None:
        assert is_builtin is True
        return self.providers.get(provider_id)

    def load_active_model(self) -> ModelSlotConfig | None:
        return self.active_model


@dataclass
class CredentialHarness:
    root: Path
    monkeypatch: pytest.MonkeyPatch
    manager: FakeProviderManager = field(default_factory=FakeProviderManager)
    root_config: Config = field(default_factory=Config)
    profiles: dict[str, AgentProfileConfig] = field(default_factory=dict)
    save_calls: list[str] = field(default_factory=list)
    fail_next_save: bool = False

    def __post_init__(self) -> None:
        data = self.root / "data"
        data.mkdir(parents=True)
        self.monkeypatch.setenv("QWENPAW_PORTABLE", "1")
        self.monkeypatch.setenv("QWENPAW_WORKING_DIR", str(data))
        for agent_id in ("default", "user-created"):
            workspace = data / "workspaces" / agent_id
            workspace.mkdir(parents=True)
            self.root_config.agents.profiles[agent_id] = AgentProfileRef(
                id=agent_id,
                workspace_dir=str(workspace),
            )
            self.root_config.agents.agent_order.append(agent_id)
            self.profiles[agent_id] = AgentProfileConfig(
                id=agent_id,
                name=agent_id,
                workspace_dir=str(workspace),
                tools=ToolsConfig(builtin_tools={}),
            )

    @property
    def credentials_path(self) -> Path:
        return self.root / "GO-CLAW-Config" / "credentials.json"

    @property
    def marker_path(self) -> Path:
        return self.root / "data" / MARKER_FILENAME

    def write_payload(self, payload: dict = VALID_PAYLOAD) -> None:
        self.credentials_path.parent.mkdir(exist_ok=True)
        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_root(self, *args, **kwargs) -> Config:
        return self.root_config

    def load_profile(self, agent_id: str) -> AgentProfileConfig:
        return self.profiles[agent_id].model_copy(deep=True)

    def save_profile(self, agent_id: str, profile: AgentProfileConfig) -> None:
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("injected save failure")
        self.profiles[agent_id] = profile.model_copy(deep=True)
        self.save_calls.append(agent_id)

    async def run(self) -> bool:
        return await import_go_claw_batch_credentials(
            self.manager,
            load_root_config=self.load_root,
            load_profile=self.load_profile,
            save_profile=self.save_profile,
        )


@pytest.fixture
def credential_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CredentialHarness:
    return CredentialHarness(tmp_path / "portable", monkeypatch)


@pytest.mark.asyncio
async def test_non_portable_and_missing_file_are_no_ops(
    credential_env: CredentialHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QWENPAW_PORTABLE")
    assert await credential_env.run() is True
    monkeypatch.setenv("QWENPAW_PORTABLE", "1")
    assert await credential_env.run() is True
    assert credential_env.manager.update_calls == []
    assert credential_env.save_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_valid_file_imports_providers_model_and_existing_agents(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True
    assert credential_env.manager.update_calls == [
        (
            "kimi-cn",
            {
                "api_key": "unit-test-llm-key",
                "base_url": "https://api.tokenbyte.example/v1",
            },
        ),
        (
            "dashscope",
            {
                "api_key": VALID_DASHSCOPE_KEY,
                "base_url": ("https://dashscope.example/compatible-mode/v1"),
            },
        ),
    ]
    assert credential_env.manager.activate_calls == [("kimi-cn", "kimi-k2.5")]
    assert credential_env.save_calls == ["default", "user-created"]
    for profile in credential_env.profiles.values():
        for tool_name in MEDIA_TOOL_NAMES:
            tool = profile.tools.builtin_tools[tool_name]
            assert tool.enabled is True
            assert tool.config == {}


def test_deepseek_provider_allows_batch_gateway_base_url() -> None:
    from qwenpaw.providers.provider_manager import PROVIDER_DEEPSEEK

    assert PROVIDER_DEEPSEEK.freeze_url is False


@pytest.mark.asyncio
async def test_marker_skips_changed_source_and_preserves_user_changes(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True
    credential_env.profiles["default"].tools.builtin_tools[
        "generate_image_qwen"
    ].enabled = False
    first_updates = list(credential_env.manager.update_calls)
    changed = deepcopy(VALID_PAYLOAD)
    changed["llm"]["apiKey"] = "unit-test-new-llm-key"
    credential_env.write_payload(changed)
    assert await credential_env.run() is True
    assert credential_env.manager.update_calls == first_updates
    assert (
        not credential_env.profiles["default"]
        .tools.builtin_tools["generate_image_qwen"]
        .enabled
    )


@pytest.mark.asyncio
async def test_deleting_marker_explicitly_reimports(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True
    credential_env.marker_path.unlink()
    assert await credential_env.run() is True
    assert len(credential_env.manager.activate_calls) == 2


def _set_schema_2(payload: dict) -> None:
    payload["schemaVersion"] = 2


def _add_unknown_field(payload: dict) -> None:
    payload["unexpected"] = True


def _set_missing_provider(payload: dict) -> None:
    payload["llm"]["providerId"] = "missing"


def _set_missing_model(payload: dict) -> None:
    payload["llm"]["modelId"] = "missing"


def _blank_llm_key(payload: dict) -> None:
    payload["llm"]["apiKey"] = "   "


def _blank_dashscope_key(payload: dict) -> None:
    payload["dashscope"]["apiKey"] = ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        _set_schema_2,
        _add_unknown_field,
        _set_missing_provider,
        _set_missing_model,
        _blank_llm_key,
        _blank_dashscope_key,
    ],
)
async def test_invalid_input_writes_nothing_and_no_marker(
    credential_env: CredentialHarness,
    mutation,
) -> None:
    payload = deepcopy(VALID_PAYLOAD)
    mutation(payload)
    credential_env.write_payload(payload)
    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []
    assert credential_env.save_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_key",
    [
        "fragment-without-sk-prefix-" + "x" * 48,
        "sk-too-short",
        "sk-" + "x" * 32 + "\\display-separator-" + "y" * 32,
        "sk-" + "x" * 32 + " embedded-space " + "y" * 32,
    ],
)
async def test_structurally_invalid_dashscope_key_writes_nothing(
    credential_env: CredentialHarness,
    invalid_key: str,
) -> None:
    payload = deepcopy(VALID_PAYLOAD)
    payload["dashscope"]["apiKey"] = invalid_key
    credential_env.write_payload(payload)

    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []
    assert credential_env.save_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_dashscope_chat_provider_rejects_conflicting_keys(
    credential_env: CredentialHarness,
) -> None:
    payload = deepcopy(VALID_PAYLOAD)
    payload["llm"].update(
        providerId="dashscope",
        modelId="qwen-max",
        apiKey="unit-test-other-key",
    )
    credential_env.write_payload(payload)
    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("symlink_directory", [False, True])
async def test_symlinked_delivery_is_rejected(
    credential_env: CredentialHarness,
    tmp_path: Path,
    symlink_directory: bool,
) -> None:
    if symlink_directory:
        outside = tmp_path / "outside-config"
        outside.mkdir()
        (outside / "credentials.json").write_text(
            json.dumps(VALID_PAYLOAD), encoding="utf-8"
        )
        credential_env.credentials_path.parent.symlink_to(
            outside, target_is_directory=True
        )
    else:
        credential_env.credentials_path.parent.mkdir()
        outside = tmp_path / "outside.json"
        outside.write_text(json.dumps(VALID_PAYLOAD), encoding="utf-8")
        credential_env.credentials_path.symlink_to(outside)
    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []


@pytest.mark.asyncio
async def test_provider_write_failure_has_no_marker_and_is_retryable(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    credential_env.manager.fail_update_for = "dashscope"
    assert await credential_env.run() is False
    assert not credential_env.marker_path.exists()
    credential_env.manager.fail_update_for = None
    assert await credential_env.run() is True
    assert credential_env.marker_path.is_file()


@pytest.mark.asyncio
async def test_partial_write_failure_has_no_marker_and_retry_completes(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    credential_env.fail_next_save = True
    assert await credential_env.run() is False
    assert not credential_env.marker_path.exists()
    assert await credential_env.run() is True
    assert credential_env.marker_path.is_file()


@pytest.mark.asyncio
async def test_marker_and_logs_never_contain_keys(
    credential_env: CredentialHarness,
    caplog: pytest.LogCaptureFixture,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True
    marker_text = credential_env.marker_path.read_text(encoding="utf-8")
    combined = marker_text + caplog.text
    assert "unit-test-llm-key" not in combined
    assert VALID_DASHSCOPE_KEY not in combined
    assert set(json.loads(marker_text)) == {
        "schemaVersion",
        "batchId",
        "sourceSha256",
        "importedAt",
    }


def test_app_imports_credentials_after_provider_and_presets_initialization():
    app_source = (
        Path(__file__).resolve().parents[3] / "src/qwenpaw/app/_app.py"
    ).read_text(encoding="utf-8")
    assert app_source.index("_run_agent_profile_startup_migrations()") < (
        app_source.index("ProviderManager.get_instance()")
    )
    assert app_source.index("ProviderManager.get_instance()") < (
        app_source.index("await import_go_claw_batch_credentials(")
    )
