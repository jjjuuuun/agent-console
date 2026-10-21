import type { ReadinessTone } from "@agent-console/contracts";
import type { Tone } from "@agent-console/ui";

/** 상태 톤 하나를 화면 요소(상태 아이콘 종류·배너 톤)로 옮기는 표. 상태 이름(`state`)은 보지 않는다. */
export interface ReadinessToneView {
  /** `StatusIcon`의 status 값 */
  icon: string;
  /** `Banner` 톤 */
  banner: Tone;
}

export const READINESS_TONES: Readonly<Record<ReadinessTone, ReadinessToneView>> = {
  ok: { icon: "succeeded", banner: "success" },
  warn: { icon: "unknown", banner: "warning" },
  error: { icon: "failed", banner: "danger" },
  unknown: { icon: "unknown", banner: "info" },
};

/** 모르는 톤은 `unknown`으로 취급한다(서버가 새 톤을 줘도 화면이 깨지지 않는다). */
export function resolveTone(tone: string | undefined): ReadinessTone {
  return tone !== undefined && Object.prototype.hasOwnProperty.call(READINESS_TONES, tone) ? (tone as ReadinessTone) : "unknown";
}

/** 연결 테스트 결과를 다시 "N분 전 통과"로 바꾸는 기준(ms). */
export const PROBE_PASS_FRESH_MS = 10 * 60 * 1000;

/** "다음부터 묻지 않기" 저장 키 접두사(뒤에 백엔드 id가 붙는다. 값은 데이터일 뿐 코드 분기가 아니다). */
export const PROBE_CONFIRMED_KEY_PREFIX = "ac.backend.probe.confirmed.";
