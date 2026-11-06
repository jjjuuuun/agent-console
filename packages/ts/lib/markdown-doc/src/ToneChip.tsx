import { toneAttr, statusTone, type StatusLike } from "./tone";

export interface ToneChipProps {
  label: string;
  /** 서버 톤 어휘(열린 문자열). 모르면 중립. */
  tone?: string | null;
  /** 밀집 행(18px) 또는 머리·상세(24px) */
  size?: "dense" | "normal";
  /** 마우스 설명(기본: label) */
  title?: string;
  className?: string;
}

/**
 * 상태·결과·빈 곳을 한 규칙으로 그리는 칩(아이콘 + 글자). 이름을 모르는 표현 부품이다.
 * 색은 `data-tone`만 달고 CSS가 정한다(JS에 톤 표가 없다). 글자는 항상 본문색이라 톤 색 위 대비를 따지지 않는다.
 */
export function ToneChip({ label, tone, size = "dense", title, className }: ToneChipProps) {
  return (
    <span className={`ac-md-chip${className ? ` ${className}` : ""}`} data-tone={toneAttr(tone)} data-size={size} title={title ?? label}>
      <span className="ac-md-chip-icon" aria-hidden="true" />
      <span className="ac-md-chip-text">{label}</span>
    </span>
  );
}

export interface DocumentStateChipProps {
  /** 문서 상태 id. 없으면 아무것도 그리지 않는다(상태 없는 문서). */
  state?: string | null;
  /** 상태 정의(`SpecView.document_states`). 없는 상태는 id 원문 + 중립. */
  states?: readonly StatusLike[];
  /** 정의 없이 이미 풀린 라벨·톤이 있을 때(`SpecDocumentSummary.state_label`·`tone`) */
  label?: string | null;
  tone?: string | null;
  size?: "dense" | "normal";
}

/** 문서 상태 칩. 상태 이름은 서버 데이터(`label`)다. */
export function DocumentStateChip({ state, states, label, tone, size }: DocumentStateChipProps) {
  if (state === undefined || state === null || state === "") return null;
  const shown = statusTone(state, states);
  return <ToneChip label={label && label !== "" ? label : shown.label} tone={tone ?? shown.tone} {...(size ? { size } : {})} />;
}
