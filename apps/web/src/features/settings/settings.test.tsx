import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { UserSettingsForm } from "./UserSettingsForm";
import type { VersionUiSettings } from "@agent-console/contracts";
import { VersionsUiEditor } from "./sections/VersionsUiSection";
import { UsageSourcesEditor, PrimaryOrderEditor } from "./sections/UsageSection";
import { parseEnumDescriptions } from "../../lib/schemaTools";

afterEach(cleanup);

// 도메인과 무관한 임의 스키마: 설정 키·값 어휘는 서버가 정한다.
const rootSchema = {
  type: "object",
  properties: {
    zeta: {
      type: "object",
      title: "제타",
      properties: {
        flavor: { $ref: "#/$defs/Flavor", title: "맛", description: "sweet: 달콤함, sour: 새콤함", default: "sweet" },
        limit: { anyOf: [{ type: "integer", minimum: 1 }, { type: "null" }], default: null, title: "한도" },
      },
    },
  },
  $defs: { Flavor: { type: "string", enum: ["sweet", "sour", "umami"] } },
};
const layers = [{ id: "L", label: "이 층" }];

function Host({ initial = {} }: { initial?: Record<string, unknown> }) {
  const [v, setV] = useState<Record<string, unknown>>(initial);
  return (
    <>
      <UserSettingsForm sections={["zeta"]} rootSchema={rootSchema} value={v} onChange={setV} layers={layers} editLayerId="L" />
      <output data-testid="value">{JSON.stringify(v)}</output>
    </>
  );
}

describe("UserSettingsForm: 스키마에서 위젯을 고른다", () => {
  it("모르는 enum도 라디오 카드로, 값별 설명은 필드 설명에서, 널 허용 숫자는 정하지 않음 체크로", () => {
    render(<Host />);
    expect(screen.getByRole("radio", { name: /sweet/ })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /umami/ })).toBeTruthy();
    expect(screen.getByText("달콤함")).toBeTruthy();
    // 기본값은 라벨 말풍선(별도 ⓘ 버튼 없음)에 있다
    expect(screen.queryByRole("button", { name: "도움말 (Alt+I)" })).toBeNull();
    expect(screen.getAllByText(/^기본값:/).length).toBeGreaterThan(0);
  });

  it("값 변경(바로 지정) → 상속으로 되돌리기가 이 층 값에만 반영된다", () => {
    render(<Host />);
    const row = screen.getByRole("radiogroup", { name: "맛" }).closest(".ac-sf-prov-row") as HTMLElement;
    fireEvent.click(within(row).getByRole("radio", { name: /sour/ }));
    expect(screen.getByTestId("value").textContent).toBe('{"zeta":{"flavor":"sour"}}');
    fireEvent.click(within(row).getByRole("button", { name: /상속으로 되돌리기/ }));
    expect(screen.getByTestId("value").textContent).toBe("{}");
  });
});

describe("값별 설명 파싱", () => {
  it("값 이름 뒤 ': '를 경계로 자른다", () => {
    expect(parseEnumDescriptions("sweet: 달콤함, sour: 새콤함", ["sweet", "sour", "umami"])).toEqual({ sweet: "달콤함", sour: "새콤함" });
  });
});

describe("사용량 출처·우선순위 편집기", () => {
  const sources = [
    { descriptor: { id: "a1", title: "출처 에이", trust: "official" }, enabled: true },
    { descriptor: { id: "b2", title: "출처 비", trust: "x-custom" }, enabled: false },
  ] as never;

  it("알 수 없는 신뢰 등급도 그대로 배지로 보이고 켜면 설정이 추가된다", () => {
    const calls: unknown[] = [];
    render(<UsageSourcesEditor sources={sources} settings={[]} onChange={(n) => calls.push(n)} />);
    expect(screen.getByText("x-custom")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "출처 비 사용" }));
    expect(calls[0]).toEqual([{ id: "b2", enabled: true }]);
  });

  it("우선순위는 체크한 출처만 들어가고 ↑↓로 순서를 바꾼다", () => {
    const calls: string[][] = [];
    render(<PrimaryOrderEditor sources={sources} order={["a1"]} onChange={(n) => calls.push(n)} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "출처 비 순서에 포함" }));
    expect(calls[0]).toEqual(["a1", "b2"]);
    cleanup();
    render(<PrimaryOrderEditor sources={sources} order={["a1", "b2"]} onChange={(n) => calls.push(n)} />);
    fireEvent.click(screen.getByRole("button", { name: "위로 이동: 출처 비" }));
    expect(calls[1]).toEqual(["b2", "a1"]);
  });
});

describe("VersionsUiEditor: ui.versions.item_label_keys", () => {
  it("키를 더하면 그 목록이 저장 값이 되고, 모두 지우면 키 자체가 없어진다(상속 = 기본값)", () => {
    const seen: unknown[] = [];
    function Wrap() {
      const [v, setV] = useState<VersionUiSettings | undefined>({ item_label_keys: ["name"] });
      return <VersionsUiEditor value={v} onChange={(n) => { seen.push(n); setV(n); }} />;
    }
    render(<Wrap />);
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "caption" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(seen.at(-1)).toEqual({ item_label_keys: ["name", "caption"] });
    fireEvent.click(screen.getByRole("button", { name: "caption 키 삭제" }));
    fireEvent.click(screen.getByRole("button", { name: "name 키 삭제" }));
    expect(seen.at(-1)).toBeUndefined();
  });
});
