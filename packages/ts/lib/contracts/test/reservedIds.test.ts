import { expect, expectTypeOf, test } from "vitest";

import type { CopyKindInfo } from "@agent-console/contracts/projects";
import type { SddInfo } from "@agent-console/contracts/sdd";
import { getContractSchema } from "@agent-console/contracts";

// 계약 0.15.1: 예약어 필드는 더하기만이다. 옛 서버 응답(필드 없음)도 같은 타입으로 읽히고,
// 읽는 쪽은 없으면 빈 목록으로 다룬다.
const reservedOf = (kind: CopyKindInfo): readonly string[] => kind.reserved_ids ?? [];
const templateReservedOf = (info: SddInfo): readonly string[] => info.reserved_template_ids ?? [];

test("옛 CopyKindInfo 응답(reserved_ids 없음)을 읽는다", () => {
  const old: CopyKindInfo = { kind: "made-up-kind", library: true, portable: false };
  expect(reservedOf(old)).toEqual([]);
  const fresh: CopyKindInfo = { ...old, reserved_ids: ["Zeta-Word"] };
  expect(reservedOf(fresh)).toEqual(["Zeta-Word"]);
  expectTypeOf<CopyKindInfo["reserved_ids"]>().toEqualTypeOf<string[] | undefined>();
});

test("옛 SddInfo 응답(reserved_template_ids 없음)을 읽는다", () => {
  const old: SddInfo = { limits: { max_bulk_start: 1, max_tasks: 1 } };
  expect(templateReservedOf(old)).toEqual([]);
  expect(templateReservedOf({ ...old, reserved_template_ids: ["omega"] })).toEqual(["omega"]);
  expectTypeOf<SddInfo["reserved_template_ids"]>().toEqualTypeOf<string[] | undefined>();
});

test("스키마에서 두 필드는 선택이다", () => {
  for (const [name, field] of [["CopyKindInfo", "reserved_ids"], ["SddInfo", "reserved_template_ids"]] as const) {
    const schema = getContractSchema(name) as { properties?: Record<string, unknown>; required?: string[] };
    expect(schema.properties).toHaveProperty(field);
    expect(schema.required ?? []).not.toContain(field);
  }
});

test("CopyKindInfo.open_role(0.16.0): 여는 화면 역할은 선택이고 옛 응답에는 없다", () => {
  const old: CopyKindInfo = { kind: "made-up-kind", library: true, portable: false };
  expect(old.open_role ?? null).toBeNull();
  const fresh: CopyKindInfo = { ...old, open_role: "zz-role:any" };
  expect(fresh.open_role).toBe("zz-role:any");
  expectTypeOf<CopyKindInfo["open_role"]>().toEqualTypeOf<string | null | undefined>();
  const schema = getContractSchema("CopyKindInfo") as { properties?: Record<string, unknown>; required?: string[] };
  expect(schema.properties).toHaveProperty("open_role");
  expect(schema.required ?? []).not.toContain("open_role");
});
