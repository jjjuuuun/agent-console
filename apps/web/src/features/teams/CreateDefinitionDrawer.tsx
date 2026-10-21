import { useState } from "react";
import { ApiError } from "@agent-console/api-client";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { issuesToFormErrors } from "../../definition/useDefinitionEditor";
import { AgentCreateForm, useAgentCreateDraft } from "../agents";
import { DEFINITION_KINDS, useInvalidateLists } from "../library";
import { ResourceCreateForm, createResourceDoc, useResourceCreateDraft } from "../resources";
import { DrawerFrame } from "./DrawerFrame";
import { teamMessages as t } from "./messages";

/** 만들기 폼이 있는 정의 종류. 정의 화면(에이전트·리소스)의 폼을 쓰는 종류만 서랍으로 만들 수 있다. */
export const CREATABLE_KINDS: readonly string[] = [DEFINITION_KINDS.agent, DEFINITION_KINDS.resource].filter((k): k is string => k !== undefined);

/** 리소스를 어디에 붙일지. 에이전트는 항상 팀에 노드로 추가된다. */
export type AttachTarget = "node" | "shared" | "none";

export interface CreatedDefinition {
  kind: string;
  id: string;
  name: string;
  attach: AttachTarget;
  /** 정의는 만들었지만 본문 저장에 실패했다(리소스) */
  bodyFailed?: boolean;
}

export interface CreateDefinitionDrawerProps {
  kind: string;
  /** 노드 타입이 정한 이 종류의 이름(예: 에이전트). 제목·안내에 쓴다 */
  kindTitle: string;
  /** 이미 있는 id(중복 즉시 표시) */
  existingIds: ReadonlySet<string>;
  /** 리소스 종류 디스크립터(리소스 서랍) */
  resourceTypes: readonly ResourceTypeDescriptor[];
  /** 리소스를 붙일 수 있는 선택 노드(없으면 [선택한 노드에 붙이기]를 숨긴다) */
  attachNode?: { id: string; label: string } | undefined;
  /** 만들기에 성공했을 때. 서랍을 닫는 것도 호출자 몫이다(캔버스에 추가한 뒤 닫는다) */
  onCreated: (created: CreatedDefinition) => void;
  onClose: () => void;
}

/**
 * 팀 편집기 안에서 에이전트·리소스를 만드는 오른쪽 서랍. 에이전트 화면·리소스 화면과 같은 폼(`AgentCreateForm`·`ResourceCreateForm`)을
 * 그대로 쓴다. 정의를 만들 뿐 팀 초안은 건드리지 않는다(팀에 넣는 일은 `onCreated`를 받은 호출자가 한다).
 * 정의 생성이 실패하면 서랍을 닫지 않고 원인을 위쪽 배너로 보인다. 열 때마다 새로 마운트한다.
 */
export function CreateDefinitionDrawer(props: CreateDefinitionDrawerProps) {
  if (props.kind === DEFINITION_KINDS.agent) return <AgentDrawer {...props} />;
  if (props.kind === DEFINITION_KINDS.resource) return <ResourceDrawer {...props} />;
  return null;
}

function AgentDrawer({ kind, kindTitle, existingIds, onCreated, onClose }: CreateDefinitionDrawerProps) {
  const { rest } = useApi();
  const invalidate = useInvalidateLists();
  const draft = useAgentCreateDraft(existingIds, t.palette.createAgentFallbackId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FormError[]>([]);
  const submit = async () => {
    setBusy(true);
    setError(null);
    setFieldErrors([]);
    try {
      const body = draft.toBody();
      await rest.createAgent(body);
      await invalidate();
      onCreated({ kind, id: body.id, name: body.name, attach: "none" });
    } catch (e) {
      setError(describeError(e, t.drawer.failed).message);
      setFieldErrors(e instanceof ApiError && e.status === 422 ? issuesToFormErrors(e.details["issues"]) : []);
      setBusy(false);
    }
  };
  return (
    <DrawerFrame
      title={t.drawer.title(kindTitle)}
      note={t.drawer.note(kindTitle)}
      dirty={draft.dirty}
      canSubmit={draft.canSubmit}
      busy={busy}
      error={error}
      submitLabel={t.drawer.submitAgent}
      onSubmit={() => void submit()}
      onClose={onClose}
      testId="create-definition-drawer"
    >
      <AgentCreateForm draft={draft} errors={fieldErrors} disabled={busy} />
    </DrawerFrame>
  );
}

function ResourceDrawer({ kind, kindTitle, existingIds, resourceTypes, attachNode, onCreated, onClose }: CreateDefinitionDrawerProps) {
  const { rest } = useApi();
  const invalidate = useInvalidateLists();
  const draft = useResourceCreateDraft(resourceTypes, existingIds, t.drawer.resourceFallbackId);
  const [attach, setAttach] = useState<AttachTarget>(attachNode === undefined ? "shared" : "node");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FormError[]>([]);
  const target: AttachTarget = attach === "node" && attachNode === undefined ? "shared" : attach;
  const submit = async () => {
    const doc = draft.build();
    if (doc === undefined) return;
    setBusy(true);
    setError(null);
    setFieldErrors([]);
    try {
      const outcome = await createResourceDoc(rest, doc, resourceTypes);
      await invalidate();
      onCreated({ kind, id: outcome.resource.id, name: outcome.resource.name, attach: target, ...(outcome.bodyError === undefined ? {} : { bodyFailed: true }) });
    } catch (e) {
      setError(describeError(e, t.drawer.failed).message);
      setFieldErrors(e instanceof ApiError && e.status === 422 ? issuesToFormErrors(e.details["issues"]) : []);
      setBusy(false);
    }
  };
  const name = (attachNode?.label ?? "").trim();
  return (
    <DrawerFrame
      title={t.drawer.title(kindTitle)}
      note={t.drawer.note(kindTitle)}
      dirty={draft.dirty}
      canSubmit={draft.canSubmit}
      busy={busy}
      error={error}
      submitLabel={target === "none" ? t.drawer.submitResourceOnly : t.drawer.submitResource}
      onSubmit={() => void submit()}
      onClose={onClose}
      testId="create-definition-drawer"
      footerExtra={
        draft.doc === null ? null : (
          <fieldset className="team-drawer-attach" disabled={busy}>
            <legend className="app-muted">{t.add.attachTo}</legend>
            {attachNode === undefined ? null : (
              <label className="ac-choice">
                <input type="radio" name="attach-target" checked={target === "node"} onChange={() => setAttach("node")} />
                <span>{t.add.attachNode(name || attachNode.id)}</span>
              </label>
            )}
            <label className="ac-choice">
              <input type="radio" name="attach-target" checked={target === "shared"} onChange={() => setAttach("shared")} />
              <span>{t.add.attachTeam}</span>
            </label>
            <label className="ac-choice">
              <input type="radio" name="attach-target" checked={target === "none"} onChange={() => setAttach("none")} />
              <span>{t.add.attachNone}</span>
            </label>
          </fieldset>
        )
      }
    >
      <ResourceCreateForm draft={draft} errors={fieldErrors} disabled={busy} />
    </DrawerFrame>
  );
}
