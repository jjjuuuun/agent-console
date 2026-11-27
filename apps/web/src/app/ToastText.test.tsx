import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ToastProvider, useToast } from "@agent-console/ui";
import { AppI18nProvider } from "../i18n/AppI18n";
import { createTestAppI18n } from "../testing/TestI18n";
import { useT } from "@agent-console/i18n";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { createToastText, ToastText } from "./ToastText";

const useBootT = () => useT("boot");
const BootToast = createToastText(useBootT);


afterEach(cleanup);

function Fire() {
  const toast = useToast();
  return <button type="button" onClick={() => toast({ tone: "info", durationMs: 600_000, text: <ToastText render={({ shell }) => shell.pending.none} /> })}>fire</button>;
}

describe("떠 있는 알림은 언어를 바꿔도 닫히지 않고 문구만 바뀐다", () => {
  it("ToastText로 넘긴 알림 글이 새 언어로 바뀐다", async () => {
    const i18n = createTestAppI18n("ko");
    render(
      <AppI18nProvider i18n={i18n}>
        <ToastProvider>
          <Fire />
        </ToastProvider>
      </AppI18nProvider>,
    );
    fireEvent.click(screen.getByText("fire"));
    const ko = screen.getByRole("status").textContent ?? "";
    expect(ko).not.toBe("");
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    const en = screen.getByRole("status").textContent ?? "";
    expect(en).not.toBe("");
    expect(en).not.toBe(ko);
  });

  it("createToastText: 기능이 고른 문구 표와 오류 코드 문구로 글을 만들고, 언어를 바꾸면 따라 바뀐다", async () => {
    const i18n = createTestAppI18n("ko");
    const error = new ApiError(409, { code: ERROR_CODES.PROJECT_CONFIG_READONLY, message: "server original" });
    function FireFeature() {
      const toast = useToast();
      return <button type="button" onClick={() => toast({ tone: "danger", durationMs: 600_000, text: <BootToast render={(t, d) => `${t("refreshFailed")} / ${d(error, "x").message}`} /> })}>fire2</button>;
    }
    render(
      <AppI18nProvider i18n={i18n}>
        <ToastProvider>
          <FireFeature />
        </ToastProvider>
      </AppI18nProvider>,
    );
    fireEvent.click(screen.getByText("fire2"));
    const ko = screen.getByRole("alert").textContent ?? "";
    expect(ko).not.toContain("server original");
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    const en = screen.getByRole("alert").textContent ?? "";
    expect(en).toContain("read-only");
    expect(en).not.toBe(ko);
  });
});
