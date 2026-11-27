import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { createTestAppI18n } from "../testing/TestI18n";
import { AppI18nProvider } from "./AppI18n";
import { useCollator } from "./collation";
import { useFormat } from "./useFormat";
import { useT } from "@agent-console/i18n";
import { raised, raisedAs, useErrorState, useErrorView } from "../app/errors";

afterEach(cleanup);

const SEC = Date.UTC(2026, 2, 4, 5, 6, 7) / 1000;

function Probe({ items }: { items: readonly string[] }) {
  const fmt = useFormat();
  const collator = useCollator();
  const [error, setError] = useErrorState();
  return (
    <div>
      <button type="button" onClick={() => setError(raised(new ApiError(409, { code: ERROR_CODES.PROJECT_CONFIG_READONLY, message: "server original" }), "fallback"))}>fail</button>
      <p data-testid="error">{error}</p>
      <p data-testid="count">{fmt.number(1234567.5)}</p>
      <p data-testid="date">{fmt.dateTimeFull(SEC)}</p>
      <p data-testid="ago">{fmt.relative(SEC, SEC * 1000 + 120_000)}</p>
      <p data-testid="sorted">{[...items].sort(collator.compare).join(",")}</p>
    </div>
  );
}

async function switchTo(i18n: ReturnType<typeof createTestAppI18n>, language: string) {
  await act(async () => {
    await i18n.changeLanguage(language);
  });
}

describe("화면 언어를 바꾸면 오류 문구·날짜·숫자·정렬이 새 언어를 따른다", () => {
  it("떠 있는 오류 문구는 저장된 오류 코드에서 새 언어로 다시 만들어진다", async () => {
    const i18n = createTestAppI18n("ko");
    render(<AppI18nProvider i18n={i18n}><Probe items={[]} /></AppI18nProvider>);
    fireEvent.click(screen.getByText("fail"));
    const ko = screen.getByTestId("error").textContent;
    expect(ko).not.toBe("server original");
    await switchTo(i18n, "en");
    const en = screen.getByTestId("error").textContent ?? "";
    expect(en).toContain("read-only");
    expect(en).not.toBe(ko);
  });

  it("숫자·시각·상대 시각 서식이 화면 언어를 쓴다(브라우저 기본이 아님)", async () => {
    const i18n = createTestAppI18n("ko");
    render(<AppI18nProvider i18n={i18n}><Probe items={[]} /></AppI18nProvider>);
    expect(screen.getByTestId("count").textContent).toBe(new Intl.NumberFormat("ko").format(1234567.5));
    expect(screen.getByTestId("ago").textContent).toBe("2분 전");
    const koDate = screen.getByTestId("date").textContent;
    await switchTo(i18n, "de");
    expect(screen.getByTestId("count").textContent).toBe("1.234.567,5");
    expect(screen.getByTestId("date").textContent).not.toBe(koDate);
    await switchTo(i18n, "en");
    expect(screen.getByTestId("ago").textContent).toMatch(/2 min/);
  });

  it("글자 정렬 순서가 화면 언어를 따른다", async () => {
    const i18n = createTestAppI18n("en");
    render(<AppI18nProvider i18n={i18n}><Probe items={["z", "ä", "a"]} /></AppI18nProvider>);
    expect(screen.getByTestId("sorted").textContent).toBe("a,ä,z");
    await switchTo(i18n, "sv");
    expect(screen.getByTestId("sorted").textContent).toBe("a,z,ä");
  });

  it("대체 문구와 화면이 직접 만든 문제 문구도 언어를 바꾸면 새 언어가 된다", async () => {
    const i18n = createTestAppI18n("ko");
    function Fallbacks() {
      const t = useT("boot");
      const [text, setText] = useErrorState(t("refreshFailed"), { own: t("retry") });
      const [view, setView] = useErrorView(t("refreshFailed"));
      return (
        <div>
          <button type="button" onClick={() => { setText(raised("not an Error")); setView(raised(undefined)); }}>plain</button>
          <button type="button" onClick={() => setText(raisedAs("own"))}>own</button>
          <p data-testid="text">{text}</p>
          <p data-testid="view">{view?.message}</p>
        </div>
      );
    }
    render(<AppI18nProvider i18n={i18n}><Fallbacks /></AppI18nProvider>);
    fireEvent.click(screen.getByText("plain"));
    const koText = screen.getByTestId("text").textContent;
    expect(koText).not.toBe("");
    expect(screen.getByTestId("view").textContent).toBe(koText);
    await switchTo(i18n, "en");
    expect(screen.getByTestId("text").textContent).not.toBe(koText);
    expect(screen.getByTestId("view").textContent).toBe(screen.getByTestId("text").textContent);
    fireEvent.click(screen.getByText("own"));
    const enOwn = screen.getByTestId("text").textContent;
    await switchTo(i18n, "ko");
    expect(screen.getByTestId("text").textContent).not.toBe(enOwn);
  });
});
