import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import AgentSelector from "./index";

const mocks = vi.hoisted(() => ({
  setSelectedAgent: vi.fn(),
  setAgents: vi.fn(),
  refreshAgents: vi.fn(),
  toggleAgentEnabled: vi.fn(),
  setAgentPinned: vi.fn(),
  navigate: vi.fn(),
  storeState: {
    selectedAgent: "default",
    agents: [] as Array<Record<string, unknown>>,
  },
}));

vi.mock("@/api/modules/agents", () => ({
  agentsApi: {
    toggleAgentEnabled: mocks.toggleAgentEnabled,
    setAgentPinned: mocks.setAgentPinned,
  },
}));

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: vi.fn(() => ({
    ...mocks.storeState,
    setSelectedAgent: mocks.setSelectedAgent,
    setAgents: mocks.setAgents,
    refreshAgents: mocks.refreshAgents,
  })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "agent.currentWorkspace": "当前数字员工",
        "agent.defaultDisplayName": "通用数字员工",
      })[key] ?? key,
  }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

const agents = [
  {
    id: "default",
    name: "Default Agent",
    enabled: true,
    description: "",
    workspace_dir: "",
    startup_status: "running",
    pinned: true,
  },
  {
    id: "marketing-growth",
    name: "营销获客",
    enabled: true,
    description: "",
    workspace_dir: "",
    startup_status: "running",
    pinned: false,
  },
  {
    id: "content-production",
    name: "内容生产",
    enabled: true,
    description: "",
    workspace_dir: "",
    startup_status: "running",
    pinned: false,
  },
  {
    id: "data-processing",
    name: "数据处理",
    enabled: true,
    description: "",
    workspace_dir: "",
    startup_status: "running",
    pinned: false,
  },
  {
    id: "business-analysis",
    name: "商业分析",
    enabled: true,
    description: "",
    workspace_dir: "",
    startup_status: "running",
    pinned: false,
  },
];

const disabledAgent = {
  id: "disabled-agent",
  name: "Disabled Employee",
  enabled: false,
  description: "",
  workspace_dir: "",
  startup_status: "disabled",
  pinned: false,
};

describe("AgentSelector", () => {
  beforeEach(() => {
    mocks.storeState.selectedAgent = "default";
    mocks.storeState.agents = agents;
    mocks.refreshAgents.mockResolvedValue(undefined);
    mocks.toggleAgentEnabled.mockResolvedValue({
      success: true,
      agent_id: "disabled-agent",
      enabled: true,
    });
    mocks.setAgentPinned.mockResolvedValue({
      success: true,
      agent_id: "marketing-growth",
      pinned: true,
    });
  });

  afterEach(() => vi.clearAllMocks());

  it("refreshes the shared agent store on mount", async () => {
    renderWithProviders(<AgentSelector />);
    await waitFor(() => expect(mocks.refreshAgents).toHaveBeenCalledOnce());
  });

  it("does not render Select in collapsed mode", async () => {
    renderWithProviders(<AgentSelector collapsed />);
    await waitFor(() => expect(mocks.refreshAgents).toHaveBeenCalled());
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows five enabled digital employees in the configured order", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AgentSelector />);

    expect(screen.getByText("当前数字员工").parentElement).toHaveTextContent(
      "当前数字员工 (5)",
    );

    await user.click(screen.getByRole("combobox"));
    const expectedNames = [
      "通用数字员工",
      "营销获客",
      "内容生产",
      "数据处理",
      "商业分析",
    ];
    const dropdown = document.querySelector(".ant-select-dropdown");
    expect(dropdown).toBeInTheDocument();
    const displayedNames = expectedNames.map((name) =>
      within(dropdown as HTMLElement).getByText(name),
    );

    for (let index = 1; index < displayedNames.length; index += 1) {
      expect(
        displayedNames[index - 1].compareDocumentPosition(
          displayedNames[index],
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it("shows disabled agents only after expanding the footer", async () => {
    mocks.storeState.agents = [...agents, disabledAgent];
    const user = userEvent.setup();
    renderWithProviders(<AgentSelector />);

    await user.click(screen.getByRole("combobox"));
    expect(screen.queryByText("Disabled Employee")).not.toBeInTheDocument();

    const disabledHeader = screen.getByRole("button", {
      name: "agent.disabledAgents",
    });
    expect(disabledHeader).toHaveAttribute("aria-expanded", "false");
    await user.click(disabledHeader);

    expect(disabledHeader).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Disabled Employee")).toBeInTheDocument();
  });

  it("keeps a pinned disabled agent visible and lets it be enabled", async () => {
    const pinnedDisabledAgent = {
      id: "agent-3",
      name: "Pinned Disabled",
      enabled: false,
      pinned: true,
      description: "",
      workspace_dir: "",
      startup_status: "disabled",
    };
    const nextAgents = [...agents, pinnedDisabledAgent];
    mocks.storeState.agents = nextAgents;
    const user = userEvent.setup();
    renderWithProviders(<AgentSelector />);

    await user.click(screen.getByRole("combobox"));
    expect(screen.getByText("Pinned Disabled")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "agent.enableAgent" }));

    expect(mocks.toggleAgentEnabled).toHaveBeenCalledWith("agent-3", true);
  });

  it("optimistically marks an enabled agent as starting", async () => {
    mocks.storeState.agents = [...agents, disabledAgent];
    const user = userEvent.setup();
    renderWithProviders(<AgentSelector />);
    await user.click(screen.getByRole("combobox"));
    await user.click(
      screen.getByRole("button", { name: "agent.disabledAgents" }),
    );
    await user.click(screen.getByRole("button", { name: "agent.enableAgent" }));

    expect(mocks.toggleAgentEnabled).toHaveBeenCalledWith(
      "disabled-agent",
      true,
    );
    expect(mocks.setAgents).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          id: "disabled-agent",
          enabled: true,
          startup_status: "starting",
        }),
      ]),
    );
  });

  it("switches to default after disabling the selected agent", async () => {
    mocks.storeState.selectedAgent = "marketing-growth";
    const user = userEvent.setup();
    renderWithProviders(<AgentSelector />);
    await user.click(screen.getByRole("combobox"));
    const dropdown = document.querySelector(".ant-select-dropdown");
    expect(dropdown).toBeInTheDocument();
    const selectedOption = within(dropdown as HTMLElement)
      .getByText("营销获客")
      .closest(".ant-select-item-option");
    expect(selectedOption).toBeInTheDocument();
    await user.click(
      within(selectedOption as HTMLElement).getByRole("button", {
        name: "agent.disableAgent",
      }),
    );

    await waitFor(() => {
      expect(mocks.toggleAgentEnabled).toHaveBeenCalledWith(
        "marketing-growth",
        false,
      );
    });
    expect(mocks.setSelectedAgent).toHaveBeenCalledWith("default");
  });
});
