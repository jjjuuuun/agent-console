import { describe, expect, it } from "vitest";
import type { BackendReadiness } from "@agent-console/contracts";
import { pickBackendTone } from "./pickBackendTone";

// 백엔드 id·톤 문자열은 전부 임의 값이다(코드는 모른다).
const be = (id: string) => ({ id });
const rd = (id: string, tone: string, extra: Partial<BackendReadiness> = {}): BackendReadiness => ({ backend_id: id, state: "zz", tone: tone as never, summary: `${id} 요약`, checked_at: 1, ...extra });
const base = { loading: false, failed: false } as const;

describe("pickBackendTone (BC-3)", () => {
  it("첫 응답 전이면 checking, 조회가 실패했으면 unavailable", () => {
    expect(pickBackendTone({ ...base, loading: true, backends: [be("a")], readiness: {} }).tone).toBe("checking");
    expect(pickBackendTone({ ...base, failed: true, backends: [be("a")], readiness: {} }).tone).toBe("unavailable");
  });

  it("기본 백엔드가 목록에 있으면 더 나쁜 다른 백엔드가 있어도 기본의 톤", () => {
    const r = pickBackendTone({ ...base, backends: [be("x1"), be("x2")], defaultBackendId: "x2", readiness: { x1: rd("x1", "error"), x2: rd("x2", "ok") } });
    expect(r.tone).toBe("ok");
    expect(r.backend?.id).toBe("x2");
    expect(r.readiness?.summary).toBe("x2 요약");
  });

  it("기본이 없거나 목록에 없으면 가장 나쁜 톤(error > warn > unknown > ok), 같으면 서버 순서 앞", () => {
    const list = [be("q1"), be("q2"), be("q3"), be("q4")];
    const readiness = { q1: rd("q1", "ok"), q2: rd("q2", "warn"), q3: rd("q3", "warn"), q4: rd("q4", "unknown") };
    const r = pickBackendTone({ ...base, backends: list, readiness });
    expect([r.tone, r.backend?.id]).toEqual(["warn", "q2"]);
    expect(pickBackendTone({ ...base, backends: list, defaultBackendId: "숨김-또는-없음", readiness }).backend?.id).toBe("q2");
    expect(pickBackendTone({ ...base, backends: list, readiness: { ...readiness, q4: rd("q4", "error") } }).backend?.id).toBe("q4");
  });

  it("모르는 톤·아직 못 읽은 백엔드는 unknown으로 본다(ok보다 나쁘다)", () => {
    expect(pickBackendTone({ ...base, backends: [be("a"), be("b")], readiness: { a: rd("a", "ok"), b: rd("b", "zz-new-tone") } })).toMatchObject({ tone: "unknown", backend: { id: "b" } });
    expect(pickBackendTone({ ...base, backends: [be("a")], readiness: {} })).toMatchObject({ tone: "unknown", backend: { id: "a" } });
  });

  it("목록이 비면 unknown·대표 없음", () => {
    expect(pickBackendTone({ ...base, backends: [], readiness: {} })).toEqual({ tone: "unknown", backend: undefined, readiness: undefined });
  });
});
