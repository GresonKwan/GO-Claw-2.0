from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

PROMPT_SOURCE_PATHS = (
    "src/qwenpaw/app/chats/utils.py",
    "src/qwenpaw/agents/templates.py",
    "src/qwenpaw/agents/md_files/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/zh/BOOTSTRAP.md",
    "src/qwenpaw/agents/md_files/go-claw-marketing-growth/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/go-claw-content-production/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/go-claw-data-processing/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/go-claw-business-analysis/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/qa/zh/AGENTS.md",
    "src/qwenpaw/agents/md_files/qa/zh/SOUL.md",
    "src/qwenpaw/agents/md_files/qa/zh/PROFILE.md",
    "src/qwenpaw/agents/skills/guidance-zh/SKILL.md",
    "src/qwenpaw/agents/skills/QA_source_index-zh/SKILL.md",
    "src/qwenpaw/agents/skills/browser_cdp-zh/SKILL.md",
    "src/qwenpaw/agents/skills/dingtalk_channel-zh/SKILL.md",
    "src/qwenpaw/agents/skills/make-skill-zh/SKILL.md",
)


def _customer_prose(path: str) -> str:
    text = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
    return text.replace("QwenPaw_QA_Agent_0.2", "INTERNAL_QA_ID")


def test_runtime_prompt_sources_use_go_claw_customer_identity():
    offenders = {
        path: [line for line in _customer_prose(path).splitlines() if "QwenPaw" in line]
        for path in PROMPT_SOURCE_PATHS
    }
    offenders = {path: lines for path, lines in offenders.items() if lines}

    assert offenders == {}
    assert all(
        "https://github.com/agentscope-ai/QwenPaw" not in _customer_prose(path)
        and "qwenpaw.agentscope.io" not in _customer_prose(path)
        for path in PROMPT_SOURCE_PATHS
    )
    exact_forbidden_fallbacks = {
        "src/qwenpaw/runtime/builder.py": ('name=agent_config.name or "QwenPaw"',),
        "src/qwenpaw/runtime/builtin_commands.py": (
            'else "QwenPaw"',
            'agent_name = "QwenPaw"',
        ),
        "src/qwenpaw/runtime/commands/daemon.py": ('agent_name: str = "QwenPaw"',),
    }
    for path, forbidden in exact_forbidden_fallbacks.items():
        source = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)


def test_no_customer_response_filter_is_introduced():
    source = (REPOSITORY_ROOT / "src/qwenpaw/app/chats/utils.py").read_text(
        encoding="utf-8",
    )
    assert '.replace("QwenPaw", "GO CLAW")' not in source
    assert ".replace('QwenPaw', 'GO CLAW')" not in source
