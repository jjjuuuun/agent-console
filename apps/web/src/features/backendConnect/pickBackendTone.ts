import type { BackendDescriptor, BackendReadiness, ReadinessTone } from "@agent-console/contracts";
import { resolveTone } from "../backendReadiness";

/** 바로가기 배지의 상태: 서버가 준 톤 넷, 첫 응답 전(`checking`), 상태 조회 실패(`unavailable`). */
export type BackendConnectTone = ReadinessTone | "checking" | "unavailable";

export interface PickToneInput<B extends Pick<BackendDescriptor, "id"> = Pick<BackendDescriptor, "id">> {
  /** 보이는 백엔드(서버 순서, 준비 상태 카드를 그리는 것만) */
  backends: readonly B[];
  /** 공통 설정의 기본 백엔드 id(없을 수 있다) */
  defaultBackendId?: string | undefined;
  /** 백엔드 id → 준비 상태(아직 못 읽은 것은 없음) */
  readiness: Readonly<Record<string, BackendReadiness | undefined>>;
  /** 첫 응답 전인가(값이 아직 없다) */
  loading: boolean;
  /** 준비 상태 조회가 404가 아닌 오류로 실패했고 가진 값이 없는가 */
  failed: boolean;
}

export interface PickedTone<B> {
  tone: BackendConnectTone;
  /** 대표 백엔드(`checking`·`unavailable`이거나 백엔드가 없으면 없음) */
  backend: B | undefined;
  /** 대표 백엔드의 점검 결과(없으면 아직 못 읽음) */
  readiness: BackendReadiness | undefined;
}

/** 나쁜 정도(클수록 나쁨). 모르는 톤은 `resolveTone`이 unknown으로 바꾼 뒤 비교한다. */
const BADNESS: Readonly<Record<ReadinessTone, number>> = { ok: 0, unknown: 1, warn: 2, error: 3 };

/**
 * 도구줄·사용량·명령이 함께 쓰는 대표 상태 하나를 고른다(순수 함수, BC-3).
 * 1) 첫 응답 전 = checking, 2) 기본 백엔드가 목록에 있으면 그 톤, 3) 없으면 가장 나쁜 톤(error > warn > unknown > ok, 같으면 서버 순서 앞),
 * 4) 조회 실패 = unavailable. 백엔드 id나 상태 이름을 문자열로 비교하지 않는다.
 */
export function pickBackendTone<B extends Pick<BackendDescriptor, "id">>(input: PickToneInput<B>): PickedTone<B> {
  const { backends, defaultBackendId, readiness, loading, failed } = input;
  if (loading) return { tone: "checking", backend: undefined, readiness: undefined };
  if (failed) return { tone: "unavailable", backend: undefined, readiness: undefined };
  const preferred = defaultBackendId === undefined ? undefined : backends.find((b) => b.id === defaultBackendId);
  let chosen: B | undefined = preferred;
  if (chosen === undefined) {
    for (const b of backends) {
      if (chosen === undefined || BADNESS[resolveTone(readiness[b.id]?.tone)] > BADNESS[resolveTone(readiness[chosen.id]?.tone)]) chosen = b;
    }
  }
  if (chosen === undefined) return { tone: "unknown", backend: undefined, readiness: undefined };
  const found = readiness[chosen.id];
  return { tone: resolveTone(found?.tone), backend: chosen, readiness: found };
}
