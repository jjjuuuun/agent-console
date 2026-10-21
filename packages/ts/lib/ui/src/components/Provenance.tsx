import { joinClass } from "./Status";

export interface ProvenanceLayer {
  id: string;
  label: string;
  /** 서버가 준 층 배열에서의 순서(낮은 우선순위가 앞). 색 슬롯 = index mod 6. */
  index: number;
}

export type ProvenanceVariant = "set" | "inherited" | "default" | "mixed";

export interface ProvenanceBadgeProps {
  layer: ProvenanceLayer;
  variant: ProvenanceVariant;
  /** mixed일 때 층 수. */
  count?: number;
  /** 있으면 버튼이 된다(팝오버 열기는 호출자). */
  onClick?: () => void;
  /** variant가 default일 때 표시할 문구 등 라벨을 바꾸고 싶을 때. 기본은 layer.label. */
  label?: string;
  className?: string;
}

export const PROVENANCE_SLOTS = 6;

/** 설정 출처 배지. 텍스트 라벨이 항상 보이고 색은 보조(층 순서로 선택). */
export function ProvenanceBadge({ layer, variant, count, onClick, label, className }: ProvenanceBadgeProps) {
  const slot = ((layer.index % PROVENANCE_SLOTS) + PROVENANCE_SLOTS) % PROVENANCE_SLOTS;
  const text = label ?? layer.label;
  const props = { className: joinClass("ac-prov", className), "data-variant": variant, "data-slot": slot, "data-layer": layer.id };
  const body = (
    <>
      {variant === "inherited" ? <span aria-hidden="true">↳</span> : <span className="ac-prov-dot" aria-hidden="true" />}
      <span className="ac-ellipsis">{text}</span>
      {variant === "mixed" && count !== undefined ? <span className="ac-num">{count}</span> : null}
    </>
  );
  return onClick === undefined ? (
    <span {...props}>{body}</span>
  ) : (
    <button type="button" {...props} onClick={onClick}>
      {body}
    </button>
  );
}
