/**
 * 공용 구성 › 문서 틀 화면(`/spec-templates`, screen-sdd §11): 문서 틀 목록(검색)과 요약(문서·실행 프로필·검사 이슈).
 * 공용(프로젝트와 무관) 저장소를 읽는다. 틀 이름·문서 이름·프로필 이름은 서버 데이터다.
 * 틀의 규칙·뼈대 파일 편집과 새로 만들기는 서버가 틀 읽기·쓰기 경로를 줄 때까지 없다(안내 문구로 알린다) — 지금은 읽기 전용 목록이다.
 */
import "@agent-console/sdd-view/styles.css";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, PageHeader } from "@agent-console/ui";
import type { SpecTemplateSummary } from "@agent-console/contracts/sdd";
import { useApi } from "../../app/ApiContext";
import { usePageTitle } from "../../shell/titles";
import { FailureBlock, ListSkeleton, SearchBox } from "./parts";
import { sddKeys } from "./useSddApi";
import { sddMessages as m } from "./messages";
import "./sdd.css";

const nameOf = (t: SpecTemplateSummary) => (t.name !== undefined && t.name !== "" ? t.name : t.id);

export function TemplatesScreen() {
  usePageTitle(m.templates.title);
  const { sdd } = useApi();
  const client = useMemo(() => sdd(null), [sdd]);
  const info = useQuery({ queryKey: sddKeys.info(""), queryFn: () => client.getSddInfo(), retry: false });
  const list = useQuery({ queryKey: sddKeys.templates(""), queryFn: () => client.listSpecTemplates(), retry: false, enabled: info.data?.capabilities?.templates === true });
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const items = useMemo(() => [...(list.data ?? [])].sort((a, b) => nameOf(a).localeCompare(nameOf(b), "ko")), [list.data]);
  const shown = q.trim() === "" ? items : items.filter((t) => `${nameOf(t)} ${t.id}`.toLowerCase().includes(q.trim().toLowerCase()));
  const selected = items.find((t) => t.id === picked);

  let body;
  if (info.isPending || (info.data?.capabilities?.templates === true && list.isPending)) body = <ListSkeleton />;
  else if (info.isError) body = <FailureBlock error={info.error} title={m.templates.loadFailed} onRetry={() => void info.refetch()} />;
  else if (info.data?.capabilities?.templates !== true) body = <div className="sdd-state" data-testid="sdd-templates-off"><EmptyState title={m.templates.off.title} description={m.templates.off.body} /></div>;
  else if (list.isError) body = <FailureBlock error={list.error} title={m.templates.loadFailed} onRetry={() => void list.refetch()} />;
  else if (items.length === 0) body = <div className="sdd-state" data-testid="sdd-templates-empty"><EmptyState title={m.templates.emptyTitle} description={m.templates.emptyBody} /></div>;
  else {
    body = (
      <div className="sdd-templates">
        <div className="sdd-templates-list">
          <SearchBox value={q} onCommit={setQ} label={m.templates.searchLabel} />
          <ul aria-label={m.templates.title}>
            {shown.map((t) => (
              <li key={t.id}>
                <button type="button" className="sdd-template-row" aria-current={t.id === picked ? "true" : undefined} onClick={() => setPicked(t.id)}>
                  <span className="ac-ellipsis"><strong>{nameOf(t)}</strong></span>
                  <span className="app-muted">{m.templates.meta((t.documents ?? []).length, (t.run_profiles ?? []).length)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="sdd-templates-detail">
          {selected === undefined ? (
            <p className="app-muted">{m.templates.pickOne}</p>
          ) : (
            <>
              <h2 className="sdd-section-title">{nameOf(selected)}</h2>
              {selected.description === undefined || selected.description === "" ? null : <p>{selected.description}</p>}
              <h3 className="sdd-label">{m.templates.documents}</h3>
              {(selected.documents ?? []).length === 0 ? <p className="app-muted">{m.templates.none}</p> : (
                <ul>{(selected.documents ?? []).map((d) => <li key={d.id}>{d.title} <span className="sdd-mono app-muted">{d.file}</span></li>)}</ul>
              )}
              <h3 className="sdd-label">{m.templates.profiles}</h3>
              {(selected.run_profiles ?? []).length === 0 ? <p className="app-muted">{m.templates.none}</p> : (
                <ul>{(selected.run_profiles ?? []).map((p) => <li key={p.id}>{p.title ?? p.id}</li>)}</ul>
              )}
              {(selected.issues ?? []).length > 0 ? (
                <>
                  <h3 className="sdd-label">{m.templates.issues((selected.issues ?? []).length)}</h3>
                  <ul>{(selected.issues ?? []).map((i, idx) => <li key={`${i.code}:${idx}`} data-tone={i.severity === "error" ? "danger" : "warning"}>{i.message}</li>)}</ul>
                </>
              ) : null}
              <p className="app-muted">{m.templates.detailReadonly}</p>
            </>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="app-screen-frame sdd-screen">
      <PageHeader title={m.templates.title} status={<span className="sdd-space-chip">{m.space.library}</span>} />
      <div className="sdd-screen-body">{body}</div>
    </div>
  );
}
