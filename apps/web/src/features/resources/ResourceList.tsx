import { useMemo, useRef, useState, type ReactNode } from "react";
import type { ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import { Button, EmptyState, ListPane } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { Skeleton } from "../settings";
import { DescriptorIcon, libraryMessages as lm, useListShortcuts } from "../library";
import { resourceMessages as t } from "./messages";
import { countByType, filterResources } from "./resourceLogic";

export interface ResourceListProps {
  resources: readonly ResourceSummary[] | undefined;
  types: readonly ResourceTypeDescriptor[] | undefined;
  typesFailed: boolean;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  /** 종류를 미리 골라 새로 만들기(종류 칩이 선택된 상태에서 빈 결과일 때) */
  onNew: (typeId?: string) => void;
  onImport: () => void;
  onRename: (id: string) => void;
  onDelete: (id: string) => void;
  /** 방금 가져온 항목만 보기(id 집합). null이면 필터 없음 */
  onlyIds: ReadonlySet<string> | null;
  onClearOnlyIds: () => void;
  /** 목록 머리에 끼울 줄(프로젝트 범위 필터 등, 없으면 생략) */
  scopeBar?: ReactNode;
  /** 이름 줄에 붙일 요소(범위 태그·선택 표시 등) */
  rowExtra?: (resource: ResourceSummary) => ReactNode;
}

/** 리소스 목록 패널: 종류 칩(디스크립터), 검색, 이름순. 종류 이름은 코드에 없고 디스크립터에서 온다. */
export function ResourceList(props: ResourceListProps) {
  const { resources, types, typesFailed, loading, error, onRetry, selectedId, onSelect, onNew, onImport, onRename, onDelete, onlyIds, onClearOnlyIds, scopeBar, rowExtra } = props;
  const [query, setQuery] = useState("");
  const [typeId, setTypeId] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const typeById = useMemo(() => new Map((types ?? []).map((x) => [x.id, x])), [types]);
  const counts = useMemo(() => countByType(resources ?? []), [resources]);
  // 디스크립터가 없어도(플러그인 제거·로딩 실패) 목록에 있는 종류 id는 칩으로 보인다
  const chipIds = useMemo(() => [...new Set([...(types ?? []).map((x) => x.id), ...counts.keys()])], [types, counts]);
  const rows = useMemo(
    () => filterResources([...(resources ?? [])].sort((a, b) => a.name.localeCompare(b.name, "ko")), { typeId, query, onlyIds }),
    [resources, typeId, query, onlyIds],
  );

  useListShortcuts({
    scope: "resources",
    onNew: () => onNew(typeId ?? undefined),
    onSearch: () => root.current?.querySelector<HTMLInputElement>('input[type="search"]')?.focus(),
    ...(selectedId === undefined ? {} : { onRename: () => onRename(selectedId), onDelete: () => onDelete(selectedId) }),
  });

  const totallyEmpty = (resources ?? []).length === 0;
  const empty = totallyEmpty ? (
    <EmptyState
      title={t.list.empty}
      description={t.list.emptyBody}
      action={<Button variant="primary" onClick={() => onNew()}>{t.list.new}</Button>}
      secondaryAction={<Button onClick={onImport}>{t.list.emptyImport}</Button>}
    />
  ) : typeId !== null && query === "" ? (
    <EmptyState title={t.list.noneOfType} action={<Button onClick={() => onNew(typeId)}>{t.list.createOfType}</Button>} />
  ) : (
    <p className="app-muted app-pad">{t.list.noMatch}</p>
  );

  return (
    <div ref={root} className="lib-split-list">
      {scopeBar}
      <div className="lib-list-toolbar">
        <Button size="sm" onClick={onImport}>{t.list.import}</Button>
      </div>
      {typesFailed ? <p className="app-muted lib-field-note app-pad" role="status">{t.list.typesFailed}</p> : null}
      <div className="lib-chips app-pad" role="group" aria-label={t.list.typeFilter}>
        <button type="button" className="lib-chip" aria-pressed={typeId === null && onlyIds === null} onClick={() => { setTypeId(null); onClearOnlyIds(); }}>
          {t.list.all} {resources === undefined ? "" : resources.length}
        </button>
        {onlyIds === null ? null : (
          <button type="button" className="lib-chip" aria-pressed onClick={onClearOnlyIds}>
            {t.list.justImported} ×
          </button>
        )}
        {chipIds.map((id) => (
          <button key={id} type="button" className="lib-chip" aria-pressed={typeId === id} onClick={() => setTypeId(typeId === id ? null : id)}>
            {typeById.get(id)?.title ?? id} {counts.get(id) ?? 0}
          </button>
        ))}
      </div>
      <ListPane<ResourceSummary>
        items={rows}
        selectedId={selectedId}
        onSelect={(id) => onSelect(id)}
        rowHeight={48}
        searchValue={query}
        onSearchChange={setQuery}
        toolbar={<Button variant="primary" size="sm" onClick={() => onNew(typeId ?? undefined)} title="N">+ {t.list.new}</Button>}
        loading={loading ? <Skeleton rows={6} /> : undefined}
        error={error ? <ErrorBlock title={t.list.loadFailed} message={error.message} retryLabel={lm.retry} onRetry={onRetry} /> : undefined}
        empty={empty}
        messages={{ listLabel: t.list.label, searchLabel: t.list.search, searchPlaceholder: t.list.searchPlaceholder }}
        renderItem={(r) => {
          const type = typeById.get(r.type);
          return (
            <span className="lib-row">
              <span className="lib-row-main">
                <DescriptorIcon hint={type?.ui_hints?.icon} title={type?.title ?? r.type} size={18} />
                {rowExtra?.(r)}
                <span className="lib-row-name ac-ellipsis" title={r.name}>{r.name}</span>
              </span>
              <span className="lib-row-sub ac-ellipsis">{[type?.title ?? r.type, r.description, r.usage_count == null ? "" : t.list.usageText(r.usage_count)].filter(Boolean).join(" · ")}</span>
            </span>
          );
        }}
      />
    </div>
  );
}
