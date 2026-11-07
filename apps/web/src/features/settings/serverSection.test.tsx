import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CONTRACTS_VERSION } from "@agent-console/contracts";
import type { PluginInfo } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

afterEach(cleanup);
const LONG = { timeout: 15_000 };

function mount(plugins: PluginInfo[], warnings: { severity: "warning"; code: string; message: string }[] = []) {
  const { clients } = createFakeClients({
    getServerInfo: async () => ({ server_version: "1.0.0", contracts_version: CONTRACTS_VERSION, plugins, warnings, attributes: {} }),
  });
  mountApp(clients, "/settings#server");
}

describe("설정: 서버 정보 플러그인", () => {
  it("skipped·disabled 플러그인은 reason을 그대로 보인다", async () => {
    mount([
      { name: "p-a", group: "g", status: "skipped", reason: "설정 plugins.disabled에 있음" },
      { name: "p-b", group: "g", status: "disabled", reason: "plugins.enabled에 없음" },
    ]);
    fireEvent.click(await screen.findByText(/플러그인 2개/, {}, LONG));
    expect(await screen.findByText(/설정 plugins\.disabled에 있음/)).toBeTruthy();
    expect(screen.getByText(/plugins\.enabled에 없음/)).toBeTruthy();
  });

  it("reason이 없거나 loaded이면 이유를 표시하지 않는다", async () => {
    mount([
      { name: "p-a", group: "g", status: "skipped", reason: null },
      { name: "p-b", group: "g", status: "loaded", reason: "무시됨" },
    ]);
    fireEvent.click(await screen.findByText(/플러그인 2개/, {}, LONG));
    await screen.findByText("p-a · skipped");
    expect(document.querySelector("[data-plugin-reason]")).toBeNull();
  });

  it("plugins.config 경고가 서버 경고 띠로 보인다", async () => {
    mount([], [{ severity: "warning", code: "plugins.config", message: "모르는 플러그인 이름: zzz" }]);
    expect(await screen.findByText(/모르는 플러그인 이름: zzz/, {}, LONG)).toBeTruthy();
    expect(screen.getByText("(plugins.config)")).toBeTruthy();
  });
});
