import type { CellRenderer, CellRenderProps } from "@agent-console/arch-view";

/** 칸의 `count` 지표 옆에 배지를 달고 기본 본문은 그대로 둔다. 값이 수집되지 않았으면(null) 배지를 달지 않는다. */
export function BadgeCellBody({ cell, defaultBody }: CellRenderProps) {
  const count = cell.metrics?.["count"]?.value;
  return (
    <>
      {defaultBody}
      {count == null ? null : (
        <span data-testid="badge-cell" data-cell-id={cell.id}>
          {`${count}회`}
        </span>
      )}
    </>
  );
}

/** 칸 그리기 하나(X24). 칸의 `view` 키가 이 이름이면 쓴다. */
export const badgeCellRenderer: CellRenderer = (props) => <BadgeCellBody {...props} />;

/** `ArchitectureDiagram`의 `cellRenderers` prop에 그대로 넘기는 표. 키 = 칸의 `view` 값(서버 데이터). */
export const cellRenderers: Readonly<Record<string, CellRenderer>> = { "example-badge": badgeCellRenderer };
