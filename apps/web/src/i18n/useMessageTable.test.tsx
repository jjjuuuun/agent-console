import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { addBundle, createI18n, type Translate } from "@agent-console/i18n";
import { AppI18nProvider } from "./AppI18n";
import { useMessageTable } from "./useMessageTable";

afterEach(cleanup);

let builds = 0;
const tableA = (t: Translate) => {
  builds += 1;
  return { hello: t("hello") };
};

function Cell({ id }: { id: string }) {
  const table = useMessageTable("a", tableA);
  return <p data-testid={id}>{table.hello}</p>;
}

function setup() {
  builds = 0;
  const i18n = createI18n({ bundled: { ko: { a: { hello: "안녕" }, b: { x: "x" } } }, fallbackLanguage: "ko" });
  render(
    <AppI18nProvider i18n={i18n}>
      <Cell id="c1" />
      <Cell id="c2" />
      <Cell id="c3" />
    </AppI18nProvider>,
  );
  return i18n;
}

describe("useMessageTable", () => {
  it("같은 표를 쓰는 컴포넌트가 여럿이어도 표 만들기는 한 번만 돈다", () => {
    setup();
    expect(screen.getByTestId("c3").textContent).toBe("안녕");
    expect(builds).toBe(1);
  });

  it("다른 네임스페이스 묶음이 들어와도 표를 다시 만들지 않는다", () => {
    const i18n = setup();
    act(() => addBundle(i18n, "ko", { b: { y: "y" } }));
    expect(builds).toBe(1);
  });

  it("자기 네임스페이스 묶음이 바뀌면 한 번만 다시 만들고 모든 컴포넌트가 새 글자를 그린다", () => {
    const i18n = setup();
    act(() => addBundle(i18n, "ko", { a: { hello: "반가워" } }));
    expect(screen.getByTestId("c1").textContent).toBe("반가워");
    expect(screen.getByTestId("c3").textContent).toBe("반가워");
    expect(builds).toBe(2);
  });
});
