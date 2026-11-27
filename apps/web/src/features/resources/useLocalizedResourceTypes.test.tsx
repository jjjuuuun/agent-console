import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyServerCatalog, createI18n } from "@agent-console/i18n";
import { AppI18nProvider } from "../../i18n/AppI18n";

const data = [{ id: "instruction", title: "지침", description: "지침 문서" }, { id: "mine", title: "내 종류" }];
vi.mock("../settings", () => ({ useResourceTypes: () => ({ data, isSuccess: true }) }));

import { useLocalizedResourceTypes } from "./useLocalizedResourceTypes";

afterEach(cleanup);

function Probe() {
  const types = useLocalizedResourceTypes();
  return <p data-testid="out">{(types.data ?? []).map((x) => `${x.title}|${x.description ?? ""}`).join(";")}</p>;
}

describe("useLocalizedResourceTypes", () => {
  it("서버 묶음에 있는 종류 이름·설명은 화면 언어로, 없는 것(사용자 데이터)은 그대로, 묶음이 늦게 와도 바뀐다", () => {
    const i18n = createI18n({ language: "en", bundled: { en: {} } });
    render(
      <AppI18nProvider i18n={i18n}>
        <Probe />
      </AppI18nProvider>,
    );
    expect(screen.getByTestId("out").textContent).toBe("지침|지침 문서;내 종류|");
    act(() => applyServerCatalog(i18n, { language: "en", text: { 지침: "Instructions", "지침 문서": "Instruction docs" }, codes: {}, ns: {} }));
    expect(screen.getByTestId("out").textContent).toBe("Instructions|Instruction docs;내 종류|");
  });
});
