import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyServerCatalog, setSourceLanguage } from "@agent-console/i18n";
import type { BackendDescriptor, BackendReadiness, TextTemplate } from "@agent-console/contracts";
import { AppI18nProvider } from "../../i18n/AppI18n";
import { createTestAppI18n } from "../../testing/TestI18n";
import { BackendReadinessCard } from "./BackendReadinessCard";
import { ProbeResultBlock } from "./ProbeResultBlock";

afterEach(cleanup);

// 서버가 준 문구는 전부 임의 값이다(서버 원문 언어 = ko, 영어는 서버 묶음이 옮긴다).
const descriptor = { id: "be-x", title: "테스트 백엔드", capabilities: { status: true, probe: false } } as BackendDescriptor;
const t = (template: string, params: TextTemplate["params"] = {}): TextTemplate => ({ template, params });
const readiness: BackendReadiness = {
  backend_id: "be-x",
  state: "zz",
  tone: "ok",
  summary: "준비됨 (인증 필요 없음)",
  detail: "20초 기다립니다. 비밀 'k': 있음",
  checked_at: Date.now() / 1000,
  checks: [{ id: "c1", title: "비밀 확인", ok: true, note: "비밀 'k': 있음" }],
  text_templates: {
    "/detail": [t("{seconds}초 기다립니다.", { seconds: 20 }), t("비밀 '{name}': {state}", { name: "k", state: t("있음") })],
    "/checks/0/note": [t("비밀 '{name}': {state}", { name: "k", state: t("있음") })],
  },
};
const probe = { running: false, result: null, requestError: null, finishedAtMs: null, run: () => undefined };
const catalogEn = {
  language: "en",
  text: {
    "테스트 백엔드": "Test backend",
    "준비됨 (인증 필요 없음)": "Ready (no sign-in needed)",
    "비밀 확인": "Secret check",
    "{seconds}초 기다립니다.": "Waiting {seconds} seconds.",
    "비밀 '{name}': {state}": "Secret '{name}': {state}",
    "있음": "present",
  },
  codes: {},
  ns: {},
};

function mount(language: "ko" | "en", data: BackendReadiness = readiness) {
  const i18n = createTestAppI18n(language);
  setSourceLanguage(i18n, "ko");
  applyServerCatalog(i18n, catalogEn);
  render(
    <AppI18nProvider i18n={i18n}>
      <MemoryRouter>
        <BackendReadinessCard descriptor={descriptor} readiness={data} probe={probe} onRecheck={vi.fn()} nowMs={Date.now()} />
      </MemoryRouter>
    </AppI18nProvider>,
  );
  return i18n;
}

describe("준비 상태 카드의 서버 문구", () => {
  it("영어에서는 이름·요약·틀 문장·점검 메모가 번역돼 한글이 남지 않는다", () => {
    mount("en");
    const card = screen.getByTestId("backend-readiness-be-x");
    expect(card.textContent).toContain("Test backend");
    expect(card.textContent).toContain("Ready (no sign-in needed)");
    expect(card.textContent).toContain("Waiting 20 seconds. Secret 'k': present");
    expect(card.textContent).toContain("Secret check");
    expect(card.textContent).toContain("Secret 'k': present");
    expect(card.textContent).not.toMatch(/[가-힣]/u);
  });

  it("서버 원문 언어(ko)에서는 서버가 쓴 문장 그대로다", () => {
    mount("ko");
    const card = screen.getByTestId("backend-readiness-be-x");
    expect(card.textContent).toContain("20초 기다립니다. 비밀 'k': 있음");
    expect(card.textContent).toContain("준비됨 (인증 필요 없음)");
  });

  it("설치자가 바꾼 틀은 번역되지 않고 서버가 쓴 문장이 그대로 보인다", () => {
    mount("en", { ...readiness, detail: "설치자 문구 20", text_templates: { "/detail": [t("설치자 문구 {seconds}", { seconds: 20 })] } });
    expect(screen.getByTestId("backend-readiness-be-x").textContent).toContain("설치자 문구 20");
  });

  it("언어를 en에서 ko로 바꾸면 원문으로 돌아온다", async () => {
    const i18n = mount("en");
    await act(async () => {
      await i18n.changeLanguage("ko");
    });
    const text = screen.getByTestId("backend-readiness-be-x").textContent ?? "";
    expect(text).toContain("준비됨 (인증 필요 없음)");
    expect(text).not.toContain("Ready (no sign-in needed)");
  });
});

describe("연결 테스트 결과의 서버 문구", () => {
  it("실패 문장은 /message 틀로 번역해 채운다", () => {
    const i18n = createTestAppI18n("en");
    setSourceLanguage(i18n, "ko");
    applyServerCatalog(i18n, { ...catalogEn, text: { "{seconds}초 안에 응답이 없었습니다.": "No response within {seconds} seconds." } });
    render(
      <AppI18nProvider i18n={i18n}>
        <MemoryRouter>
          <ProbeResultBlock
            nowMs={Date.now()}
            probe={{
              running: false,
              requestError: null,
              finishedAtMs: Date.now(),
              result: { backend_id: "be-x", ok: false, reason: "timeout", message: "20초 안에 응답이 없었습니다.", finished_at: 1, text_templates: { "/message": [t("{seconds}초 안에 응답이 없었습니다.", { seconds: 20 })] } },
            }}
          />
        </MemoryRouter>
      </AppI18nProvider>,
    );
    expect(screen.getByTestId("probe-result").textContent).toContain("No response within 20 seconds.");
  });
});
