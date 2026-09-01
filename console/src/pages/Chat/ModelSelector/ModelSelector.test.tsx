import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import ModelSelector from "./index";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/modules/goClawProduct", () => ({
  goClawProductApi: {
    getModelTier: vi.fn(),
    setModelTier: vi.fn(),
  },
}));

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: vi.fn(() => ({ selectedAgent: "default" })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

import { goClawProductApi } from "@/api/modules/goClawProduct";

const tierResponse = {
  schemaVersion: 1 as const,
  agentId: "default",
  selectedTier: "economy" as const,
  tiers: [
    {
      id: "economy" as const,
      label: "经济",
      description: "适合日常任务，额度更耐用",
      warning: null,
      icon: "leaf" as const,
    },
    {
      id: "balanced" as const,
      label: "均衡",
      description: "质量与额度消耗更均衡",
      warning: null,
      icon: "balance" as const,
    },
    {
      id: "performance" as const,
      label: "高性能",
      description: "适合复杂和高要求任务",
      warning: "高性能模型可以提高任务完成质量，但额度消耗更快。",
      icon: "rocket" as const,
    },
  ],
  effectiveMaxInputLength: 32768,
};

function setupDefaultMocks() {
  vi.mocked(goClawProductApi.getModelTier).mockResolvedValue(tierResponse);
  vi.mocked(goClawProductApi.setModelTier).mockResolvedValue({
    ...tierResponse,
    selectedTier: "balanced",
    effectiveMaxInputLength: 65536,
  });
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

  it("shows only the public tier label and its dedicated icon", async () => {
    renderWithProviders(<ModelSelector />);
    expect(await screen.findByText("经济")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "经济" })).toBeInTheDocument();
  });

  it("loads the selected employee independently", async () => {
    renderWithProviders(<ModelSelector />);
    await screen.findByText("经济");
    expect(goClawProductApi.getModelTier).toHaveBeenCalledWith("default");
  });

  it("opens a fixed three-tier menu without provider controls", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await user.click(await screen.findByRole("button", { name: /经济/ }));
    expect(await screen.findByText("均衡")).toBeInTheDocument();
    expect(screen.getByText("高性能")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/search/i)).not.toBeInTheDocument();
  });

  it("updates only the public tier contract", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await user.click(await screen.findByRole("button", { name: /经济/ }));
    await user.click(await screen.findByText("均衡"));
    expect(goClawProductApi.setModelTier).toHaveBeenCalledWith({
      schemaVersion: 1,
      agentId: "default",
      tier: "balanced",
    });
  });

  it("shows the performance warning and publishes resolved context", async () => {
    vi.mocked(goClawProductApi.setModelTier).mockResolvedValue({
      ...tierResponse,
      selectedTier: "performance",
      effectiveMaxInputLength: 131072,
    });
    const switched = vi.fn();
    window.addEventListener("model-switched", switched);
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await user.click(await screen.findByRole("button", { name: /经济/ }));
    switched.mockClear();
    expect(
      await screen.findByText(
        "高性能模型可以提高任务完成质量，但额度消耗更快。",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByText("高性能"));

    await waitFor(() => expect(switched).toHaveBeenCalledOnce());
    const event = switched.mock.calls[0][0] as CustomEvent;
    expect(event.detail).toEqual({ maxInputLength: 131072 });
    window.removeEventListener("model-switched", switched);
  });

  it("does not send a request for the selected tier", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await user.click(await screen.findByRole("button", { name: /经济/ }));
    await user.click((await screen.findAllByText("经济"))[1]);
    expect(goClawProductApi.setModelTier).not.toHaveBeenCalled();
  });

  it("keeps the previous tier when saving fails", async () => {
    vi.mocked(goClawProductApi.setModelTier).mockRejectedValue(
      new Error("API"),
    );
    const user = userEvent.setup();
    renderWithProviders(<ModelSelector />);
    await user.click(await screen.findByRole("button", { name: /经济/ }));
    await user.click(await screen.findByText("均衡"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /经济/ })).toBeInTheDocument(),
    );
  });

  it("shows an enabled retry instead of permanent loading after failure", async () => {
    vi.mocked(goClawProductApi.getModelTier)
      .mockRejectedValueOnce(new Error("API"))
      .mockResolvedValueOnce(tierResponse);
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    const user = userEvent.setup();

    try {
      renderWithProviders(<ModelSelector />);
      const retry = await screen.findByRole("button", {
        name: "模型档位加载失败，点击重试",
      });
      expect(retry).toBeEnabled();
      expect(screen.getByText("重新加载")).toBeInTheDocument();
      expect(screen.queryByText("加载中")).not.toBeInTheDocument();

      await user.click(retry);
      expect(await screen.findByText("经济")).toBeInTheDocument();
      expect(goClawProductApi.getModelTier).toHaveBeenCalledTimes(2);
    } finally {
      consoleError.mockRestore();
    }
  });

  it("keeps the initial pending state disabled", () => {
    vi.mocked(goClawProductApi.getModelTier).mockImplementation(
      () => new Promise(() => {}),
    );

    renderWithProviders(<ModelSelector />);

    expect(screen.getByRole("button", { name: "加载模型档位" })).toBeDisabled();
    expect(screen.getByText("加载中")).toBeInTheDocument();
  });
});
