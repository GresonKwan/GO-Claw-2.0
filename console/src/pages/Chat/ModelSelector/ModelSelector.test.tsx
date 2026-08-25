import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import ModelSelector from "./index";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/modules/provider", () => ({
  providerApi: {
    listProviders: vi.fn(),
    getActiveModels: vi.fn(),
    setActiveLlm: vi.fn(),
  },
}));

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: vi.fn(() => ({ selectedAgent: "default" })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

vi.mock("lucide-react", () => ({
  Loader2: () => "Loader2",
  ExternalLink: () => "ExternalLink",
  ChevronDown: () => "ChevronDown",
  ChevronRight: () => "ChevronRight",
  Search: () => "Search",
  X: () => "X",
  Check: () => "Check",
  AlertCircle: () => "AlertCircle",
  Eye: () => "Eye",
  Zap: () => "Zap",
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

import { providerApi } from "@/api/modules/provider";

const mockProvider = {
  id: "openai",
  name: "OpenAI",
  api_key: "sk-xxx",
  api_key_prefix: "",
  chat_model: "OpenAIChatModel",
  require_api_key: true,
  base_url: "",
  is_custom: false,
  is_local: false,
  support_model_discovery: false,
  support_connection_check: false,
  freeze_url: false,
  generate_kwargs: {},
  models: [
    {
      id: "deepseek-v4-pro",
      name: "DeepSeek-V4 Pro",
      supports_multimodal: false,
      supports_image: false,
      supports_video: false,
      generate_kwargs: {},
      max_tokens: 8192,
      max_input_length: 32768,
      relay_reasoning: true,
      thinking_enabled: null,
      thinking_budget: null,
      reasoning_effort: null,
    },
    {
      id: "qwen3.7-plus",
      name: "Qwen3.7 Plus",
      supports_multimodal: false,
      supports_image: false,
      supports_video: false,
      generate_kwargs: {},
      max_tokens: 4096,
      max_input_length: 16384,
      relay_reasoning: true,
      thinking_enabled: null,
      thinking_budget: null,
      reasoning_effort: null,
    },
  ],
  extra_models: [],
};

const mockActiveModels = {
  active_llm: { provider_id: "openai", model: "deepseek-v4-pro" },
};

function setupDefaultMocks() {
  vi.mocked(providerApi.listProviders).mockResolvedValue([mockProvider]);
  vi.mocked(providerApi.getActiveModels).mockResolvedValue(mockActiveModels);
  vi.mocked(providerApi.setActiveLlm).mockResolvedValue({});
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ModelSelector", () => {
  beforeEach(() => {
    setupDefaultMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("displays current active model name on trigger button after loading", async () => {
    renderWithProviders(<ModelSelector />);
    expect(
      (await screen.findAllByText("DeepSeek-V4 Pro"))[0],
    ).toBeInTheDocument();
  });

  it("displays i18n key when there is no active model", async () => {
    vi.mocked(providerApi.getActiveModels).mockResolvedValue({
      active_llm: undefined,
    });
    renderWithProviders(<ModelSelector />);
    expect(
      (await screen.findAllByText("modelSelector.selectModel"))[0],
    ).toBeInTheDocument();
  });

  it("displays bare model id when active model is outside the eligible list", async () => {
    // provider has no api_key configured, so it is excluded from eligible list
    vi.mocked(providerApi.listProviders).mockResolvedValue([
      { ...mockProvider, api_key: "" },
    ]);
    renderWithProviders(<ModelSelector />);
    expect(
      (await screen.findAllByText("deepseek-v4-pro"))[0],
    ).toBeInTheDocument();
  });

  it("calls listProviders and getActiveModels on mount", async () => {
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");
    expect(providerApi.listProviders).toHaveBeenCalledOnce();
    expect(providerApi.getActiveModels).toHaveBeenCalledWith({
      scope: "effective",
      agent_id: "default",
    });
  });

  it("clicking trigger button opens dropdown and shows provider list", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");

    await user.click(screen.getAllByText("DeepSeek-V4 Pro")[0]);

    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
  });

  it("clicking a model calls setActiveLlm with correct parameters", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");

    await user.click(screen.getAllByText("DeepSeek-V4 Pro")[0]);
    const gpt35 = await screen.findByText("Qwen3.7 Plus");
    await user.click(gpt35);

    expect(providerApi.setActiveLlm).toHaveBeenCalledWith({
      provider_id: "openai",
      model: "qwen3.7-plus",
      scope: "agent",
      agent_id: "default",
    });
  });

  it("publishes the backend-resolved context window after a model switch", async () => {
    vi.mocked(providerApi.setActiveLlm).mockResolvedValue({
      active_llm: {
        provider_id: "openai",
        model: "qwen3.7-plus",
      },
      effective_max_input_length: 65536,
    });
    const switched = vi.fn();
    window.addEventListener("model-switched", switched);
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");

    await user.click(screen.getAllByText("DeepSeek-V4 Pro")[0]);
    await user.click(await screen.findByText("Qwen3.7 Plus"));

    await waitFor(() => expect(switched).toHaveBeenCalledOnce());
    const event = switched.mock.calls[0][0] as CustomEvent;
    expect(event.detail).toEqual({
      maxInputLength: 65536,
    });
    window.removeEventListener("model-switched", switched);
  });

  it("publishes the backend-resolved context window after loading active models", async () => {
    vi.mocked(providerApi.getActiveModels).mockResolvedValue({
      ...mockActiveModels,
      effective_max_input_length: 262144,
    });
    const switched = vi.fn();
    window.addEventListener("model-switched", switched);
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");

    await waitFor(() => expect(switched).toHaveBeenCalledOnce());
    const event = switched.mock.calls[0][0] as CustomEvent;
    expect(event.detail).toEqual({
      maxInputLength: 262144,
    });
    window.removeEventListener("model-switched", switched);
  });

  it("clicking the already active model does not call setActiveLlm", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");

    await user.click(screen.getAllByText("DeepSeek-V4 Pro")[0]);
    const gpt4Items = await screen.findAllByText("DeepSeek-V4 Pro");
    await user.click(gpt4Items[gpt4Items.length - 1]);

    expect(providerApi.setActiveLlm).not.toHaveBeenCalled();
  });

  it("dropdown shows empty state when no providers are available", async () => {
    vi.mocked(providerApi.listProviders).mockResolvedValue([]);
    vi.mocked(providerApi.getActiveModels).mockResolvedValue({
      active_llm: undefined,
    });
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("modelSelector.selectModel");

    await user.click(screen.getAllByText("modelSelector.selectModel")[0]);

    expect(
      await screen.findByText("modelSelector.noConfiguredModels"),
    ).toBeInTheDocument();
  });

  it("still displays original active model after setActiveLlm failure", async () => {
    vi.mocked(providerApi.setActiveLlm).mockRejectedValue(
      new Error("API error"),
    );
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await screen.findAllByText("DeepSeek-V4 Pro");

    await user.click(screen.getAllByText("DeepSeek-V4 Pro")[0]);
    const gpt35 = await screen.findByText("Qwen3.7 Plus");
    await user.click(gpt35);

    // GPT-4 may appear in two places when dropdown is still open (trigger + dropdown item)
    await waitFor(() => {
      expect(
        screen.getAllByText("DeepSeek-V4 Pro").length,
      ).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("GO CLAW customer model list", () => {
  const makeModel = (id: string, name: string) => ({
    id,
    name,
    supports_multimodal: false,
    supports_image: false,
    supports_video: false,
    generate_kwargs: {},
    max_tokens: 8192,
    max_input_length: 32768,
    relay_reasoning: true,
    thinking_enabled: null,
    thinking_budget: null,
    reasoning_effort: null,
  });

  const duplicateProviders = [
    {
      ...mockProvider,
      id: "dashscope",
      name: "DashScope",
      models: [
        makeModel("deepseek-v4-pro", "DeepSeek-V4 Pro"),
        makeModel("qwen3.7-plus", "Qwen3.7 Plus"),
        makeModel("qwen3.6-plus", "Qwen3.6 Plus"),
      ],
      extra_models: [],
    },
    {
      ...mockProvider,
      id: "deepseek",
      name: "DeepSeek",
      models: [
        makeModel("deepseek-v4-pro", "DeepSeek-V4 Pro"),
        makeModel("deepseek-chat", "DeepSeek Chat"),
      ],
      extra_models: [makeModel("qwen3.7-plus", "qwen3.7-plus")],
    },
  ];

  it("dedupes models across providers and hides non-allowed models", async () => {
    vi.mocked(providerApi.listProviders).mockResolvedValue(duplicateProviders);
    vi.mocked(providerApi.getActiveModels).mockResolvedValue({
      active_llm: { provider_id: "dashscope", model: "deepseek-v4-pro" },
    });
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);

    // 打开下拉（触发按钮显示当前激活模型）
    await screen.findAllByText("DeepSeek-V4 Pro");
    await user.click(screen.getAllByText("DeepSeek-V4 Pro")[0]);

    // 去重 + 白名单后，第二个 provider（DeepSeek）的所有模型都被
    // 过滤（v4-pro 与 extra 的 qwen3.7-plus 为重复项、deepseek-chat
    // 不在白名单），该 provider 组应整体消失；DashScope 组保留
    await waitFor(() => {
      expect(screen.getByText("DashScope")).toBeInTheDocument();
    });
    expect(screen.queryByText("DeepSeek")).not.toBeInTheDocument();
    // extra_models 的裸 id 重复项不出现
    expect(screen.queryByText("qwen3.7-plus")).not.toBeInTheDocument();
    // 白名单外的目录项隐藏
    expect(screen.queryByText("Qwen3.6 Plus")).not.toBeInTheDocument();
    expect(screen.queryByText("DeepSeek Chat")).not.toBeInTheDocument();
  });
});
