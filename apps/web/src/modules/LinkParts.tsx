import { createContext, useContext, useMemo, type ReactNode } from "react";
import { lookupMessage } from "../app/messages";
import { useRequires } from "./ModulesContext";

/**
 * 연동 부분 한 줄(데이터). 다른 기능과 이어져야만 의미가 있는 화면 안의 부분을 등록한다(`docs/design/screen-modules.md` 4).
 * 화면 컴포넌트는 부분 id만 알고, 어떤 모듈·역할이 필요한지는 이 데이터가 정한다.
 */
export interface LinkPartDef {
  /** 부분 id(예: `chat.delegation-chip`) */
  id: string;
  /** 모듈 id 또는 역할(AND). 보통 연동 모듈이 선언한 역할 */
  requires: readonly string[];
  /** `hide`: 보이지 않음(자리도 없음, 보너스 정보). `disable`: 자리는 두고 비활성 + 이유(주 동작이 막힘) */
  onMissing: "hide" | "disable";
  /** `disable`일 때 이유 문구의 `messages.linkPart.note` 키 */
  noteKey?: string;
}

interface PartsValue {
  byId: ReadonlyMap<string, LinkPartDef>;
  list: readonly LinkPartDef[];
}
const PartsContext = createContext<PartsValue>({ byId: new Map(), list: [] });

/** 연동 부분 등록 데이터를 하위 훅에 공급한다. 데이터는 앱 조립 층(`links/`)이 정한다. */
export function LinkPartsProvider({ parts, children }: { parts: readonly LinkPartDef[]; children: ReactNode }) {
  const value = useMemo<PartsValue>(() => ({ byId: new Map(parts.map((p) => [p.id, p])), list: parts }), [parts]);
  return <PartsContext.Provider value={value}>{children}</PartsContext.Provider>;
}

/** 등록된 연동 부분 전체(설정의 "영향받는 부분" 계산용). */
export function useLinkPartDefs(): readonly LinkPartDef[] {
  return useContext(PartsContext).list;
}

export interface LinkPartState {
  /** 그려도 되는가. `hide`이고 꺼졌으면 false(래퍼는 아무것도 그리지 않는다) */
  visible: boolean;
  /** 자리는 두되 동작은 막아야 하는가(`disable`이고 꺼졌거나 확인 중) */
  disabled: boolean;
  /** 꺼져서 막혔는가(확인 중인 로딩과 구분) */
  off: boolean;
  /** 이유 문구(`disable`이고 꺼졌을 때) */
  note: string | undefined;
}

const ON: LinkPartState = { visible: true, disabled: false, off: false, note: undefined };

/**
 * 연동 부분이 지금 켜져 있는가. 등록되지 않은 id는 제한 없음(켜짐)으로 본다.
 * 숨긴 부분은 API를 부르지 않아야 하므로 호출하는 쪽은 `visible`이 false이면 훅·구독도 만들지 않는다
 * (조건부 렌더 컴포넌트 안에 두고 `enabled` 옵션으로 막는다).
 */
export function useLinkPart(id: string): LinkPartState {
  const def = useContext(PartsContext).byId.get(id);
  const r = useRequires(def?.requires ?? []);
  return useMemo<LinkPartState>(() => {
    if (def === undefined || r.phase === "met") return ON;
    if (def.onMissing === "hide") return { visible: false, disabled: true, off: r.phase === "unmet", note: undefined };
    return {
      visible: true,
      disabled: true,
      off: r.phase === "unmet",
      note: r.phase === "unmet" && def.noteKey !== undefined ? lookupMessage(`linkPart.note.${def.noteKey}`) : undefined,
    };
  }, [def, r.phase]);
}

export interface LinkPartProps {
  id: string;
  /** 노드 또는 상태를 받는 함수(`disable` 부분이 입력을 막고 이유를 보일 때) */
  children: ReactNode | ((state: LinkPartState) => ReactNode);
}

/** 연동 부분 래퍼: 꺼졌고 `hide`이면 자식을 그리지 않는다(DOM에 자리를 남기지 않는다). */
export function LinkPart({ id, children }: LinkPartProps) {
  const state = useLinkPart(id);
  if (!state.visible) return null;
  return <>{typeof children === "function" ? children(state) : children}</>;
}
