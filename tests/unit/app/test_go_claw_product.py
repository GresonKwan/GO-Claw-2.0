# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from qwenpaw.config.config import ModelSlotConfig

from qwenpaw.app import go_claw_product as product


@dataclass
class _FakeModel:
    id: str
    name: str

    def model_dump(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


class _FakeProvider:
    def __init__(
        self,
        models: tuple[str, ...] = (),
        extra_models: tuple[str, ...] = (),
    ) -> None:
        self.models = [_FakeModel(model_id, model_id) for model_id in models]
        self.extra_models = [
            _FakeModel(model_id, model_id) for model_id in extra_models
        ]

    def has_model(self, model_id: str) -> bool:
        return any(
            model.id == model_id for model in self.models + self.extra_models
        )


class _FakeProviderManager:
    def __init__(
        self,
        provider: _FakeProvider,
        *,
        update_result: bool = True,
        persist_update: bool = True,
    ) -> None:
        self.provider = provider
        self.update_result = update_result
        self.persist_update = persist_update
        self.updates: list[dict] = []

    def get_provider(self, provider_id: str) -> _FakeProvider | None:
        return self.provider if provider_id == "token-plan" else None

    def update_provider(self, provider_id: str, config: dict) -> bool:
        if provider_id != "token-plan":
            return False
        self.updates.append(deepcopy(config))
        if not self.update_result:
            return False
        if self.persist_update:
            self.provider.extra_models = [
                _FakeModel(model["id"], model["name"])
                for model in config["extra_models"]
            ]
        return self.update_result


def _manager_with_all_tiers() -> _FakeProviderManager:
    return _FakeProviderManager(
        _FakeProvider(
            models=tuple(tier.model_id for tier in product.MODEL_TIERS)
        ),
    )


def test_private_model_catalog_is_exact_and_ordered() -> None:
    assert [tier.id for tier in product.MODEL_TIERS] == [
        "economy",
        "balanced",
        "performance",
    ]
    assert [tier.label for tier in product.MODEL_TIERS] == ["经济", "均衡", "高性能"]
    assert product.DEFAULT_MODEL_TIER == "economy"
    assert product.resolve_model_tier("performance").warning == (
        "高性能模型可以提高任务完成质量，但额度消耗更快。"
    )


def test_routing_state_write_is_strict_atomic_and_durable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[Path, dict[str, object], bool]] = []
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    monkeypatch.setattr(
        product,
        "write_json_atomic",
        lambda path, payload, durable=False: calls.append(
            (path, payload, durable),
        ),
    )

    product.write_routing_state("token-plan")

    path, payload, durable = calls[0]
    assert path == tmp_path / ".go-claw-product-routing.json"
    assert set(payload) == {"schemaVersion", "providerId", "updatedAt"}
    assert payload["schemaVersion"] == 1
    assert payload["providerId"] == "token-plan"
    assert durable is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "schemaVersion": 2,
            "providerId": "p",
            "updatedAt": "2026-01-01T00:00:00Z",
        },
        {
            "schemaVersion": 1,
            "providerId": "",
            "updatedAt": "2026-01-01T00:00:00Z",
        },
        {
            "schemaVersion": 1,
            "providerId": "p",
            "updatedAt": "2026-01-01T00:00:00Z",
            "extra": True,
        },
    ],
)
def test_routing_state_rejects_non_contract_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict,
) -> None:
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    (tmp_path / ".go-claw-product-routing.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    assert product.read_routing_state() is None


def test_v1_derivation_requires_existing_https_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    manager = SimpleNamespace(
        get_active_model=lambda: ModelSlotConfig(
            provider_id="token-plan",
            model="legacy",
        ),
        get_provider=lambda provider_id: SimpleNamespace(
            base_url="https://new-api.example/v1",
        )
        if provider_id == "token-plan"
        else None,
    )

    state = product.ensure_routing_state(manager)

    assert state is not None
    assert state.provider_id == "token-plan"
    assert product.read_routing_state() == state


def test_migration_maps_every_profile_once_and_writes_marker_last(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    product.write_routing_state("token-plan")
    source_models = {
        "a": "deepseek-v4-flash",
        "b": "deepseek-v4-flash-0731",
        "c": "qwen3.7-plus",
        "d": "qwen3.8-max",
        "e": "unknown-model",
        "f": None,
    }
    persisted = {
        agent_id: SimpleNamespace(
            active_model=(
                ModelSlotConfig(provider_id="old", model=model)
                if model is not None
                else None
            ),
        )
        for agent_id, model in source_models.items()
    }
    root = SimpleNamespace(
        agents=SimpleNamespace(profiles=dict.fromkeys(source_models)),
    )
    events: list[str] = []

    monkeypatch.setattr(product, "load_config", lambda **_kwargs: root)
    monkeypatch.setattr(
        product,
        "load_agent_config",
        lambda agent_id: deepcopy(persisted[agent_id]),
    )

    def save(agent_id, config) -> None:
        events.append(f"save:{agent_id}")
        persisted[agent_id] = deepcopy(config)

    monkeypatch.setattr(product, "save_agent_config", save)

    manager = _manager_with_all_tiers()
    assert product.ensure_go_claw_model_tiers(manager) is True

    assert [persisted[key].active_model.model for key in source_models] == [
        "deepseek-v4-flash-0731",
        "deepseek-v4-flash-0731",
        "qwen3.7-plus",
        "qwen3.8-max",
        "deepseek-v4-flash-0731",
        "deepseek-v4-flash-0731",
    ]
    assert {cfg.active_model.provider_id for cfg in persisted.values()} == {
        "token-plan",
    }
    marker = tmp_path / ".migrations" / "go-claw-model-tiers-v1.json"
    assert marker.exists()
    assert set(json.loads(marker.read_text(encoding="utf-8"))) == {
        "schemaVersion",
        "version",
        "completedAt",
    }

    persisted["a"].active_model = ModelSlotConfig(
        provider_id="token-plan",
        model="qwen3.8-max",
    )
    events.clear()
    assert product.ensure_go_claw_model_tiers(manager) is True
    assert persisted["a"].active_model.model == "qwen3.8-max"
    assert events == []


def test_completed_migration_repairs_missing_tier_catalog_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    product.write_routing_state("token-plan")
    marker = tmp_path / ".migrations" / "go-claw-model-tiers-v1.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "version": product.MIGRATION_VERSION,
                "completedAt": "2026-08-31T00:00:00Z",
            },
        ),
        encoding="utf-8",
    )
    manager = _FakeProviderManager(
        _FakeProvider(
            models=("deepseek-chat",),
            extra_models=("customer-model",),
        ),
    )
    monkeypatch.setattr(
        product,
        "load_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed migration must not rewrite employees"),
        ),
    )

    assert product.ensure_go_claw_model_tiers(manager) is True
    assert [model.id for model in manager.provider.extra_models] == [
        "customer-model",
        "deepseek-v4-flash-0731",
        "qwen3.7-plus",
        "qwen3.8-max",
    ]
    assert len(manager.updates) == 1

    assert product.ensure_go_claw_model_tiers(manager) is True
    assert len(manager.updates) == 1


@pytest.mark.parametrize(
    ("update_result", "persist_update"),
    [(False, True), (True, False)],
)
def test_catalog_repair_fails_closed_when_update_is_not_persisted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    update_result: bool,
    persist_update: bool,
) -> None:
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    product.write_routing_state("token-plan")
    manager = _FakeProviderManager(
        _FakeProvider(models=("deepseek-chat",)),
        update_result=update_result,
        persist_update=persist_update,
    )
    monkeypatch.setattr(
        product,
        "load_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("failed repair must not migrate employees"),
        ),
    )

    assert product.ensure_go_claw_model_tiers(manager) is False
    assert len(manager.updates) == 1
    assert not (
        tmp_path / ".migrations" / "go-claw-model-tiers-v1.json"
    ).exists()


def test_failed_profile_save_never_writes_completion_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        product,
        "get_config_path",
        lambda: tmp_path / "config.json",
    )
    product.write_routing_state("token-plan")
    root = SimpleNamespace(agents=SimpleNamespace(profiles={"a": object()}))
    monkeypatch.setattr(product, "load_config", lambda **_kwargs: root)
    monkeypatch.setattr(
        product,
        "load_agent_config",
        lambda _agent_id: SimpleNamespace(active_model=None),
    )
    monkeypatch.setattr(
        product,
        "save_agent_config",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert (
        product.ensure_go_claw_model_tiers(_manager_with_all_tiers()) is False
    )
    assert not (
        tmp_path / ".migrations" / "go-claw-model-tiers-v1.json"
    ).exists()
