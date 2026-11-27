import { act, cleanup, render, screen } from "@testing-library/react";
import { useMemo } from "react";
import { afterEach, describe, expect, test } from "vitest";

import {
  applyServerCatalog,
  createI18n,
  I18nProvider,
  setLanguage,
  useLibMessages,
  useServerText,
  useT,
} from "@agent-console/i18n";

const bundled = {
  en: { app: { hello: "Hello {name}" }, lib: { save: "Save", nested: { close: "Close {n}" } } },
  ko: { app: { hello: "{name}님" }, lib: { save: "저장", nested: { close: "닫기 {n}" } } },
};
const defaults = { save: "Save?", extra: "Extra", nested: { close: "Close? {n}" } };

function Probe() {
  const t = useT("app");
  const lib = useLibMessages("lib", defaults);
  const server = useServerText();
  return (
    <div>
      <p data-testid="t">{t("hello", { name: "Ann" })}</p>
      <p data-testid="lib">{`${lib.save}|${lib.extra}|${lib.nested.close}`}</p>
      <p data-testid="server">{server.text("Orig")}</p>
      <p data-testid="issue">{server.issue("a.b", { n: 2 }, "fallback")}</p>
    </div>
  );
}

afterEach(cleanup);

describe("react hooks", () => {
  test("render in the current language and re-render when it changes", async () => {
    const i18n = createI18n({ language: "en", bundled });
    render(
      <I18nProvider i18n={i18n}>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("t").textContent).toBe("Hello Ann");
    expect(screen.getByTestId("lib").textContent).toBe("Save|Extra|Close {n}");
    await act(async () => {
      await setLanguage(i18n, "ko");
    });
    expect(screen.getByTestId("t").textContent).toBe("Ann님");
    expect(screen.getByTestId("lib").textContent).toBe("저장|Extra|닫기 {n}");
  });

  test("a server catalog arriving later updates all three hooks", async () => {
    const i18n = createI18n({ language: "ko", bundled });
    render(
      <I18nProvider i18n={i18n}>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("server").textContent).toBe("Orig");
    expect(screen.getByTestId("issue").textContent).toBe("fallback");
    await act(async () => {
      applyServerCatalog(i18n, {
        language: "ko",
        text: { Orig: "원문" },
        codes: { "a.b": "{n}개" },
        ns: { app: { hello: "서버 {name}" }, lib: { save: "서버 저장" } },
      });
    });
    expect(screen.getByTestId("server").textContent).toBe("원문");
    expect(screen.getByTestId("issue").textContent).toBe("2개");
    expect(screen.getByTestId("t").textContent).toBe("서버 Ann");
    expect(screen.getByTestId("lib").textContent).toBe("서버 저장|Extra|닫기 {n}");
  });

  test("useServerText gets a new identity when the server catalog arrives (memo keys stay correct)", async () => {
    const i18n = createI18n({ language: "ko", bundled });
    const seen: unknown[] = [];
    function Capture() {
      const server = useServerText();
      seen.push(server.text);
      return <p data-testid="memo">{useMemo(() => server.text("Orig"), [server])}</p>;
    }
    render(
      <I18nProvider i18n={i18n}>
        <Capture />
      </I18nProvider>,
    );
    expect(screen.getByTestId("memo").textContent).toBe("Orig");
    await act(async () => {
      applyServerCatalog(i18n, { language: "ko", text: { Orig: "원문" }, codes: {}, ns: {} });
    });
    expect(screen.getByTestId("memo").textContent).toBe("원문");
    expect(new Set(seen).size).toBeGreaterThan(1);
  });

  test("useLibMessages keeps its identity while nothing changes", () => {
    const i18n = createI18n({ language: "en", bundled });
    const seen: unknown[] = [];
    function Capture() {
      seen.push(useLibMessages("lib", defaults));
      return null;
    }
    const { rerender } = render(
      <I18nProvider i18n={i18n}>
        <Capture />
      </I18nProvider>,
    );
    rerender(
      <I18nProvider i18n={i18n}>
        <Capture />
      </I18nProvider>,
    );
    expect(seen[0]).toBe(seen[seen.length - 1]);
  });
});
