import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { applyServerCatalog, createI18n } from "@agent-console/i18n";
import { SchemaForm } from "@agent-console/schema-form";
import { AppI18nProvider } from "./AppI18n";
import { AppSchemaForm } from "./useSchemaFormI18n";

afterEach(cleanup);

const schema = { type: "object", properties: { a: { type: "string", title: "원문 제목", description: "원문 설명" } } };

describe("AppSchemaForm: schema-form translate·messages 연결", () => {
  it("서버 묶음 text로 스키마 제목·설명이 바뀌고, 라이브러리 문구도 현재 언어 묶음이다", () => {
    const i18n = createI18n({
      language: "en",
      bundled: { en: { "schema-form": { addItem: "Add entry" } } },
    });
    applyServerCatalog(i18n, { language: "en", text: { "원문 제목": "Translated title", "원문 설명": "Translated help" }, codes: {}, ns: {} });
    render(
      <AppI18nProvider i18n={i18n}>
        <AppSchemaForm schema={schema} value={{}} onChange={() => undefined} idPrefix="t" rawJsonToggle={false} />
      </AppI18nProvider>,
    );
    expect(screen.getByText("Translated title")).toBeTruthy();
    expect(screen.queryByText("원문 제목")).toBeNull();
  });

  it("공급자가 없으면 그냥 SchemaForm처럼 원문(한국어 기본 문구)을 그린다", () => {
    render(<AppSchemaForm schema={schema} value={{}} onChange={() => undefined} idPrefix="t" rawJsonToggle={false} />);
    expect(screen.getByText("원문 제목")).toBeTruthy();
    expect(SchemaForm).toBeTruthy();
  });
});
