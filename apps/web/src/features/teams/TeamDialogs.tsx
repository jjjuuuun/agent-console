import { useState } from "react";
import type { EdgeTypeDescriptor, GraphSummary, NodeTypeDescriptor } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { DEFINITION_KINDS, useInvalidateLists, NewDefinitionDialog, type NewDefinitionValues } from "../library";
import { projectBody, useProjectId } from "../../app/projectScope";
import { useNewScope } from "../projects";
import { teamMessages as t } from "./messages";
import { entrySourceNodeTypes, starterGraph } from "./teamsLogic";

type Start = "node" | "empty" | "clone";

export interface NewTeamDialogProps {
  graphs: readonly GraphSummary[];
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  onClose: () => void;
  /** 만든 뒤(편집기로 이동 등) */
  onCreated: (id: string) => void;
}

/** 새 팀 구성: 이름·id·설명 + 시작 방식(사용자 노드 하나 / 빈 / 복제). 사용자 노드 타입은 속성으로 찾는다. */
export function NewTeamDialog({ graphs, nodeTypes, edgeTypes, onClose, onCreated }: NewTeamDialogProps) {
  const { rest } = useApi();
  const invalidate = useInvalidateLists();
  const userTypes = entrySourceNodeTypes(nodeTypes, edgeTypes);
  // 사용자가 고르기 전에는 (나중에 도착하는) 노드 종류 조회 결과를 따라간다.
  const [pickedStart, setStart] = useState<Start | null>(null);
  const [pickedUserType, setUserTypeId] = useState<string | null>(null);
  const [pickedClone, setCloneId] = useState<string | null>(null);
  const start: Start = pickedStart ?? (userTypes.length > 0 ? "node" : "empty");
  const userTypeId = pickedUserType ?? userTypes[0]?.id ?? "";
  const cloneId = pickedClone ?? graphs[0]?.id ?? "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scope = useNewScope(DEFINITION_KINDS.graph ?? "");

  const submit = async (v: NewDefinitionValues) => {
    setBusy(true);
    setError(null);
    try {
      if (start === "clone") {
        await rest.duplicateGraph(cloneId, { id: v.id, name: v.name });
      } else {
        const startNode = start === "node" ? userTypes.find((x) => x.id === userTypeId) : undefined;
        await rest.createGraph({ ...starterGraph({ id: v.id, name: v.name, ...(v.description ? { description: v.description } : {}), ...(startNode ? { startNode } : {}) }), ...scope.patch });
      }
      await invalidate();
      onCreated(v.id);
    } catch (e) {
      setError(describeError(e, t.create.failed).message);
      setBusy(false);
    }
  };

  const options: { id: Start; label: string; hidden?: boolean }[] = [
    { id: "node", label: t.create.startUser, hidden: userTypes.length === 0 },
    { id: "empty", label: t.create.startEmpty },
    { id: "clone", label: t.create.startClone, hidden: graphs.length === 0 },
  ];
  return (
    <NewDefinitionDialog
      open
      title={t.create.title}
      submitLabel={t.create.submit}
      existingIds={new Set(graphs.map((g) => g.id))}
      fallbackId={t.create.fallbackId}
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={(v) => void submit(v)}
      extra={
        <>
        <fieldset className="lib-fieldset">
          <legend>{t.create.start}</legend>
          {options.filter((o) => o.hidden !== true).map((o) => (
            <label key={o.id} className="app-check">
              <input type="radio" name="team-start" checked={start === o.id} onChange={() => setStart(o.id)} />
              {o.label}
            </label>
          ))}
          {start === "node" && userTypes.length > 1 ? (
            <select aria-label={t.create.startUserType} value={userTypeId} onChange={(e) => setUserTypeId(e.target.value)}>
              {userTypes.map((x) => (
                <option key={x.id} value={x.id}>{x.title}</option>
              ))}
            </select>
          ) : null}
          {start === "clone" ? (
            <select aria-label={t.create.cloneFrom} value={cloneId} onChange={(e) => setCloneId(e.target.value)}>
              {graphs.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          ) : null}
        </fieldset>
        {start === "clone" ? null : scope.field}
        </>
      }
    />
  );
}

export interface RenameTeamDialogProps {
  graph: GraphSummary;
  onClose: () => void;
  onDone: () => void;
}

/** 이름·설명 바꾸기(목록에서). 서버의 최신 문서를 읽어 이름·설명만 바꿔 저장한다(`If-Match`). */
export function RenameTeamDialog({ graph, onClose, onDone }: RenameTeamDialogProps) {
  const { rest } = useApi();
  const invalidate = useInvalidateLists();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (v: NewDefinitionValues) => {
    setBusy(true);
    setError(null);
    try {
      const got = await rest.getGraph(graph.id);
      const next = { ...got.graph, name: v.name } as typeof got.graph;
      if (v.description === "") delete (next as { description?: unknown }).description;
      else next.description = v.description;
      await rest.updateGraph(graph.id, next, got.version_hash);
      await invalidate();
      onDone();
    } catch (e) {
      setError(describeError(e, t.rename.failed).message);
      setBusy(false);
    }
  };
  return (
    <NewDefinitionDialog
      open
      hideId
      title={t.rename.title}
      submitLabel={t.rename.submit}
      existingIds={new Set()}
      fallbackId={graph.id}
      initialName={graph.name}
      initialDescription={graph.description ?? ""}
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={(v) => void submit(v)}
    />
  );
}

export interface DuplicateTeamDialogProps {
  sourceId: string;
  sourceName: string;
  existingIds: ReadonlySet<string>;
  onClose: () => void;
  onCreated: (id: string) => void;
}

/** 복제: 새 이름·id를 받아 `POST /graphs/{id}/duplicate`. */
export function DuplicateTeamDialog({ sourceId, sourceName, existingIds, onClose, onCreated }: DuplicateTeamDialogProps) {
  const { rest } = useApi();
  const invalidate = useInvalidateLists();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (v: NewDefinitionValues) => {
    setBusy(true);
    setError(null);
    try {
      await rest.duplicateGraph(sourceId, { id: v.id, name: v.name });
      await invalidate();
      onCreated(v.id);
    } catch (e) {
      setError(describeError(e, t.duplicate.failed).message);
      setBusy(false);
    }
  };
  return (
    <NewDefinitionDialog
      open
      title={t.duplicate.title}
      submitLabel={t.duplicate.submit}
      existingIds={existingIds}
      fallbackId={`${sourceId}-copy`}
      initialName={`${sourceName} 2`}
      showDescription={false}
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={(v) => void submit(v)}
    />
  );
}

/** 새 대화 시작: 팀 구성으로 대화를 만들고 그 대화 화면으로 간다(대화 화면 경로는 라우트 설정에서). */
export function useStartChat(onOpenChat: (conversationId: string) => void): { start: (graphId: string) => Promise<string | null>; busy: boolean; error: string | null } {
  const { rest } = useApi();
  const projectId = useProjectId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async (graphId: string) => {
    setBusy(true);
    setError(null);
    try {
      const conv = await rest.createConversation({ graph_id: graphId, ...projectBody(projectId) });
      onOpenChat(conv.id);
      return conv.id;
    } catch (e) {
      setError(describeError(e, t.chat.createFailed).message);
      return null;
    } finally {
      setBusy(false);
    }
  };
  return { start, busy, error };
}
