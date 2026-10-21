import type { NodeTypeDescriptor } from "@agent-console/contracts";
import { latestById } from "./teamsLogic";

/** [+ 추가] 메뉴 항목이 하는 일. 종류 이름이 아니라 노드 타입 디스크립터에서 나온 값만 담는다. */
export type AddAction =
  | { op: "pick"; kind: string }
  | { op: "create"; kind: string }
  | { op: "node"; typeId: string };

export interface AddMenuEntry {
  id: string;
  label: string;
  action: AddAction;
}

export interface AddMenuInput {
  nodeTypes: readonly NodeTypeDescriptor[];
  /** 이 정의 종류를 고를 수 있는가(그 정의를 편집하는 모듈이 켜져 있고 고를 목록이 있다) */
  canPick: (kind: string) => boolean;
  /** 이 정의 종류로 새로 만드는 서랍이 있는가(정의 모듈이 켜져 있고 만들기 폼이 있다) */
  canCreate: (kind: string) => boolean;
  labels: {
    pick: (title: string) => string;
    create: (title: string) => string;
    node: (title: string) => string;
  };
}

/**
 * 추가 메뉴 항목을 노드 타입 디스크립터와 켜진 기능에서 만든다(항목 이름·순서는 코드에 없다).
 * 정의에 묶이는 타입(`binds`)은 종류마다 `고르기…`·`새 …`(만들 수 있을 때), 묶이지 않고 숨김이 아닌 실행 가능 타입은 `추가` 항목이다.
 * 정의 모듈이 꺼져 있으면 그 종류의 항목이 사라지고, 노드 타입 항목만 남을 수 있다.
 */
export function buildAddMenu({ nodeTypes, canPick, canCreate, labels }: AddMenuInput): AddMenuEntry[] {
  const out: AddMenuEntry[] = [];
  const seenKinds = new Set<string>();
  for (const type of latestById(nodeTypes)) {
    if (type.ui_hints?.hidden === true) continue;
    if (type.binds != null) {
      const kind = type.binds.kind;
      if (seenKinds.has(kind)) continue;
      seenKinds.add(kind);
      if (canPick(kind)) out.push({ id: `pick:${kind}`, label: labels.pick(type.title), action: { op: "pick", kind } });
      if (canCreate(kind)) out.push({ id: `create:${kind}`, label: labels.create(type.title), action: { op: "create", kind } });
    }
  }
  for (const type of latestById(nodeTypes)) {
    if (type.ui_hints?.hidden === true || type.binds != null || type.executable === false) continue;
    out.push({ id: `node:${type.id}`, label: labels.node(type.title), action: { op: "node", typeId: type.id } });
  }
  return out;
}
