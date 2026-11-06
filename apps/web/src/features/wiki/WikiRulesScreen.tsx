/**
 * 공용 구성 › 위키 규칙 화면(`/wiki-rules`, screen-wiki §10): 왼쪽 목록(검색·행 보조 버튼) + 오른쪽 편집기(`WikiRulesEditor`).
 * 공간은 주소의 `?prj=`가 정한다: 없으면 공용(또는 단독 루트), 있으면 그 프로젝트의 사본(`SpaceScope`). 선택은 주소 경로(`/wiki-rules/:id`), 탭·섹션은 질의 인자가 진실이다.
 * 위키 규칙 REST는 정의 모듈 없이 동작한다. 규칙 이름·정의 종류 이름은 서버 데이터이고 코드에 없다(종류는 규칙 원문의 `kind`에서 읽는다).
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { useBlocker, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button, ConfirmDialog, EmptyState, PageHeader, useToast } from "@agent-console/ui";
import type { WikiRulesListItem } from "@agent-console/contracts/wiki";
import { useReportUnsaved } from "../../definition/unsaved";
import { GuardedButton } from "../../app/menuParts";
import { usePageTitle } from "../../shell/titles";
import { SpaceChip, SpaceNote, SpaceScope, useConfigTransfer } from "../projects";
import { NewWikiRulesDialog, type NewWikiRulesBody } from "./NewWikiRulesDialog";
import { WikiRulesEditor } from "./WikiRulesEditor";
import { DebouncedInput, FailureBlock, ListSkeleton } from "./parts";
import { useInvalidateWiki } from "./useWikiApi";
import { useWikiRulesItems, useWikiRulesKind, useWikiRulesSpace, wikiRulesKeys } from "./useWikiRulesApi";
import { WIKI_RULES_SCREEN } from "./wikiConfig";
import { wikiRulesPath } from "./wikiPaths";
import { wikiMessages as m } from "./messages";
import { wikiRulesMessages as t } from "./rulesScreenMessages";
import "./wiki.css";

const nameOf = (x: WikiRulesListItem) => (x.name !== undefined && x.name !== "" ? x.name : x.id);
const idOf = (x: WikiRulesListItem) => x.id;

export function WikiRulesScreen() {
  return (
    <SpaceScope>
      <WikiRulesBody />
    </SpaceScope>
  );
}

function WikiRulesBody() {
  usePageTitle(t.title);
  const space = useWikiRulesSpace();
  const toast = useToast();
  const qc = useQueryClient();
  const invalidate = useInvalidateWiki();
  const navigate = useNavigate();
  const location = useLocation();
  const { id: picked } = useParams();
  const [params, setParams] = useSearchParams();
  const list = useWikiRulesItems(space);
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const items = useMemo(() => [...(list.data ?? [])].sort((a, b) => nameOf(a).localeCompare(nameOf(b), "ko")), [list.data]);
  const kind = useWikiRulesKind(space.client, space.key, items[0]?.id, items.length > 0);
  const transfer = useConfigTransfer(items, { kind, idOf, nameOf });
  const shown = q.trim() === "" ? items : items.filter((x) => `${nameOf(x)} ${x.id}`.toLowerCase().includes(q.trim().toLowerCase()));
  const selected = items.find((x) => x.id === picked);
  const writeBlock = space.readOnly ? space.readOnlyReason : undefined;

  useReportUnsaved(dirty);
  // 다른 규칙을 고르거나 다른 화면으로 가는 이동(경로가 바뀌는 이동)을 막는다. 같은 규칙 안의 탭·섹션 이동은 질의 인자만 바뀌므로 막지 않는다
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirtyRef.current && currentLocation.pathname !== nextLocation.pathname);

  /** 규칙을 고른다: 경로만 바뀌고 `?prj=` 같은 질의는 이어 가되 탭·섹션·파일은 처음으로 돌린다. */
  const apply = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(location.search);
      next.delete(WIKI_RULES_SCREEN.params.tab);
      next.delete(WIKI_RULES_SCREEN.params.section);
      next.delete(WIKI_RULES_SCREEN.params.file);
      const base = wikiRulesPath(id ?? undefined);
      if (base === undefined) return;
      const search = next.toString();
      void navigate({ pathname: base, search: search === "" ? "" : `?${search}` });
    },
    [location.search, navigate],
  );
  const select = (id: string) => {
    if (id !== picked) apply(id);
  };
  const onDirtyChange = useCallback((next: boolean) => {
    dirtyRef.current = next;
    setDirty(next);
  }, []);

  const create = async (body: NewWikiRulesBody) => {
    const made = await space.client.createWikiRules({ ...body });
    setCreating(false);
    await invalidate();
    toast({ tone: "success", text: t.toast.created(made.value.rules.name || made.value.rules.id) });
    apply(made.value.rules.id);
  };

  let body;
  if (space.infoQuery.isPending || list.isPending) body = <ListSkeleton />;
  else if (space.infoQuery.isError) body = <FailureBlock error={space.infoQuery.error} title={t.loadFailed} onRetry={() => void space.infoQuery.refetch()} />;
  else if (list.isError) body = <FailureBlock error={list.error} title={t.loadFailed} onRetry={() => void list.refetch()} />;
  else if (items.length === 0) {
    body = (
      <div className="wiki-state" data-testid="wiki-rules-empty">
        <EmptyState title={t.empty.title} description={`${t.empty.body} ${t.empty.hint}`} />
      </div>
    );
  } else {
    body = (
      <div className="wiki-rules-screen">
        <div className="wiki-rules-list">
          <DebouncedInput value={q} onCommit={setQ} label={t.searchLabel} />
          <ul aria-label={t.listLabel}>
            {shown.map((x) => {
              const action = transfer.menuItem(x);
              return (
                <li key={x.id} className="wiki-rules-item">
                  <button type="button" className="wiki-rules-row" aria-current={x.id === picked ? "true" : undefined} onClick={() => select(x.id)}>
                    <span className="ac-ellipsis"><strong>{nameOf(x)}</strong></span>
                    <span className="app-muted">{t.rowSub(x.counts?.write ?? 0, x.counts?.lint ?? 0, x.counts?.templates ?? 0)}</span>
                  </button>
                  {action === null ? null : (
                    <Button size="sm" aria-disabled={action.disabled === true || undefined} title={action.title} aria-label={`${action.label}: ${nameOf(x)}`} onClick={() => { if (action.disabled !== true) action.onSelect(); }}>
                      {action.label}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
        <div className="wiki-rules-detail">
          {selected === undefined ? <p className="app-muted">{t.picked}</p> : (
            <WikiRulesEditor
              key={`${space.key}:${selected.id}`}
              space={space}
              id={selected.id}
              params={params}
              setParams={(next, options) => setParams(next, { replace: options?.replace === true })}
              onDirtyChange={onDirtyChange}
              onDeleted={(name) => {
                qc.removeQueries({ queryKey: wikiRulesKeys.one(space.key, selected.id) });
                void invalidate();
                toast({ tone: "success", text: t.toast.deleted(name) });
                dirtyRef.current = false;
                setDirty(false);
                apply(null);
              }}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-screen-frame wiki-screen">
      <PageHeader
        title={t.title}
        status={<SpaceChip />}
        actions={<GuardedButton variant="primary" blockedReason={writeBlock} onClick={() => setCreating(true)}>{t.new}</GuardedButton>}
      />
      <SpaceNote />
      <div className="wiki-screen-body">{body}</div>
      {creating ? <NewWikiRulesDialog open onClose={() => setCreating(false)} onSubmit={create} /> : null}
      {transfer.dialog}
      <ConfirmDialog open={blocker.state === "blocked"} title={m.leave.title} confirmLabel={m.leave.leave} cancelLabel={m.leave.stay} danger onConfirm={() => blocker.state === "blocked" && blocker.proceed()} onCancel={() => blocker.state === "blocked" && blocker.reset()}>{m.leave.body}</ConfirmDialog>
    </div>
  );
}
