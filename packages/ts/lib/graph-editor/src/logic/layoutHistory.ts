/**
 * 레이아웃 변경 되돌리기/다시 스택(graph-edges §2.4). 노드 추가·삭제 같은 다른 편집은 섞지 않는다.
 * 항목은 변경 전·후 그래프 한 쌍이다. 현재 그래프가 맨 위 항목의 결과와 다르면(그 사이 다른 편집·외부 갱신)
 * 스택이 낡은 것이므로 비운다. 비교에서 `ui`는 뺀다(viewport 같은 화면 상태가 자주 바뀐다). 단 `ui.layout`(그래프 기본 방향·모양)은
 * 정리([정리 ▾])가 함께 바꾸므로 비교하고 복원한다. 복원 때 `ui`의 나머지 키는 현재 값을 그대로 둔다.
 */
import type { Graph } from "@agent-console/contracts";

/** 스택 깊이(단계). */
export const LAYOUT_HISTORY_LIMIT = 30;

interface Entry {
  before: Graph;
  after: Graph;
}

/** 비교용 모습: `ui`를 빼되 `ui.layout`만 남긴다. */
const comparable = (g: Graph): Record<string, unknown> => {
  const { ui, ...rest } = g;
  const layout = ui?.["layout"];
  return layout === undefined ? rest : { ...rest, "ui.layout": layout };
};

/** 두 그래프가 `ui`(`ui.layout` 제외)를 빼고 같은가. */
export const sameGraphIgnoringUi = (a: Graph, b: Graph): boolean =>
  a === b || JSON.stringify(comparable(a)) === JSON.stringify(comparable(b));

/** 복원 그래프: 본문은 target, `ui`는 현재 것을 두되 `ui.layout`만 target 값으로 맞춘다. */
const keepUi = (target: Graph, current: Graph): Graph => {
  const { ui: _ui, ...rest } = target;
  void _ui;
  const ui: Record<string, unknown> = { ...(current.ui ?? {}) };
  const layout = target.ui?.["layout"];
  if (layout === undefined) delete ui["layout"];
  else ui["layout"] = layout;
  return (Object.keys(ui).length > 0 ? { ...rest, ui } : rest) as Graph;
};

export class LayoutHistory {
  private undoStack: Entry[] = [];
  private redoStack: Entry[] = [];

  constructor(private readonly limit: number = LAYOUT_HISTORY_LIMIT) {}

  /** 한 번의 레이아웃 변경을 기록한다(다시 스택은 비운다). 결과가 같으면 기록하지 않는다. */
  record(before: Graph, after: Graph): void {
    if (sameGraphIgnoringUi(before, after)) return;
    this.undoStack.push({ before, after });
    if (this.undoStack.length > this.limit) this.undoStack.shift();
    this.redoStack = [];
  }

  get undoSize(): number {
    return this.undoStack.length;
  }
  get redoSize(): number {
    return this.redoStack.length;
  }
  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
  }

  /** 한 단계 되돌린 그래프. 되돌릴 것이 없거나 스택이 낡았으면 `null`. */
  undo(current: Graph): Graph | null {
    const top = this.undoStack[this.undoStack.length - 1];
    if (top === undefined) return null;
    if (!sameGraphIgnoringUi(top.after, current)) {
      this.clear();
      return null;
    }
    this.undoStack.pop();
    this.redoStack.push(top);
    return keepUi(top.before, current);
  }

  /** 한 단계 다시 적용한 그래프. */
  redo(current: Graph): Graph | null {
    const top = this.redoStack[this.redoStack.length - 1];
    if (top === undefined) return null;
    if (!sameGraphIgnoringUi(top.before, current)) {
      this.clear();
      return null;
    }
    this.redoStack.pop();
    this.undoStack.push(top);
    return keepUi(top.after, current);
  }
}
