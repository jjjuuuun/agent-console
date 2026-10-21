import { useMemo, useState } from "react";
import type { Resource, ResourceTypeDescriptor } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { DEFINITION_KINDS, DefinitionIdField, DescriptorIcon, Field, libraryMessages as lm, useDefinitionId, type DefinitionId } from "../library";
import { useNewScope } from "../projects";
import { ResourceEditorForm, type ResourceDocUpdate } from "./ResourceEditorForm";
import { ResourceTypeGrid } from "./ResourceTypeGrid";
import { resourceMessages as t } from "./messages";
import { defaultContentRef, newResourceDoc, type ResourceDoc } from "./resourceLogic";

/** 새 리소스 초안 상태: 종류 + 문서(정의·본문) + id 제안 + 프로젝트 범위. */
export interface ResourceCreateDraft {
  types: readonly ResourceTypeDescriptor[];
  /** 고른 종류 id(아직 안 골랐으면 null) */
  typeId: string | null;
  descriptor: ResourceTypeDescriptor | undefined;
  /** 종류를 고르면(또는 바꾸면) 이름·설명을 지키고 본문을 새로 시작한다. null이면 다시 고르기 */
  setTypeId: (next: string | null) => void;
  /** 종류를 고르기 전에는 null */
  doc: ResourceDoc | null;
  setDoc: (next: ResourceDocUpdate) => void;
  id: DefinitionId;
  scope: ReturnType<typeof useNewScope>;
  canSubmit: boolean;
  dirty: boolean;
  /** 서버에 보낼 문서(id·이름·범위·본문 참조 포함). 종류를 고르기 전에는 undefined */
  build: () => ResourceDoc | undefined;
}

/**
 * 새 리소스 초안. 본문·설정 편집기는 종류 디스크립터가 정하며(`ResourceEditorForm`) 리소스 화면과 같다.
 * 호출자가 서랍을 열 때마다 새로 마운트한다.
 */
export function useResourceCreateDraft(types: readonly ResourceTypeDescriptor[], existingIds: ReadonlySet<string>, fallbackId: string, initialTypeId?: string): ResourceCreateDraft {
  const only = types.length === 1 ? types[0] : undefined;
  const start = initialTypeId ?? only?.id ?? null;
  const [typeId, setTypeIdState] = useState<string | null>(start);
  const [doc, setDocState] = useState<ResourceDoc | null>(() => (start === null ? null : newResourceDoc(types.find((x) => x.id === start), { id: "", name: "" })));
  const descriptor = types.find((x) => x.id === typeId);
  const name = doc?.resource.name ?? "";
  const id = useDefinitionId(name, existingIds, fallbackId);
  const scope = useNewScope(DEFINITION_KINDS.resource ?? "");
  const setTypeId = (next: string | null) => {
    setTypeIdState(next);
    if (next === null) {
      setDocState(null);
      return;
    }
    const keep = doc?.resource;
    setDocState(newResourceDoc(types.find((x) => x.id === next), { id: "", name: keep?.name ?? "", ...(keep?.description ? { description: keep.description } : {}) }));
  };
  const setDoc = (next: ResourceDocUpdate) => setDocState((cur) => (cur === null ? cur : typeof next === "function" ? next(cur) : next));
  return useMemo(
    () => ({
      types,
      typeId,
      descriptor,
      setTypeId,
      doc,
      setDoc,
      id,
      scope,
      canSubmit: doc !== null && name.trim() !== "" && !id.invalid,
      dirty: doc !== null && (name !== "" || (doc.resource.description ?? "") !== "" || (doc.text ?? "") !== "" || (doc.files ?? []).length > 0 || Object.keys(doc.resource.config ?? {}).length > 0),
      build: () => {
        if (doc === null) return undefined;
        const ref = defaultContentRef(descriptor, id.id);
        const resource = {
          ...doc.resource,
          id: id.id,
          name: doc.resource.name.trim(),
          ...(ref ? { content: { file: ref.file, media_type: doc.resource.content?.media_type ?? ref.media_type } } : {}),
          ...scope.patch,
        } as Resource;
        return { ...doc, resource, origin: { ...doc.origin, resource } };
      },
    }),
    // setTypeId·setDoc은 useState 갱신자와 types에만 기대므로 doc/typeId 변화에 맞춰 다시 만든다
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [types, typeId, doc, id, scope, descriptor, name],
  );
}

export interface ResourceCreateFormProps {
  draft: ResourceCreateDraft;
  errors?: FormError[];
  disabled?: boolean;
}

/** 새 리소스 전체 폼: ① 종류 고르기 ② 이름·id·설명·프로젝트 + `ResourceEditorForm`(리소스 화면과 같은 편집기). */
export function ResourceCreateForm({ draft, errors = [], disabled = false }: ResourceCreateFormProps) {
  const { doc, descriptor } = draft;
  if (doc === null || descriptor === undefined) return <ResourceTypeGrid types={draft.types} onPick={draft.setTypeId} />;
  const patch = (p: Partial<Resource>) =>
    draft.setDoc((cur) => {
      const next = { ...cur.resource, ...p } as Record<string, unknown>;
      for (const k of Object.keys(next)) if (next[k] === undefined) delete next[k];
      return { ...cur, resource: next as unknown as Resource };
    });
  return (
    <div className="lib-form">
      <p className="ac-text lib-row-main">
        <DescriptorIcon hint={descriptor.ui_hints?.icon} title={descriptor.title} size={16} />
        <span>{t.create.chosen(descriptor.title)}</span>
        {draft.types.length > 1 ? (
          <button type="button" className="app-link-btn" onClick={() => draft.setTypeId(null)}>
            {t.create.change}
          </button>
        ) : null}
      </p>
      <fieldset className="lib-fieldset" disabled={disabled}>
        <Field label={lm.newDialog.name}>
          {(a) => <input {...a} className="ac-input" value={doc.resource.name} onChange={(e) => patch({ name: e.target.value })} maxLength={120} />}
        </Field>
        <DefinitionIdField id={draft.id.id} problem={draft.id.problem} onChange={draft.id.setId} />
        <Field label={lm.newDialog.description}>
          {(a) => <textarea {...a} className="ac-input" rows={2} value={doc.resource.description ?? ""} onChange={(e) => patch({ description: e.target.value === "" ? undefined : e.target.value })} />}
        </Field>
        {draft.scope.field}
      </fieldset>
      <ResourceEditorForm part="all" descriptor={descriptor} doc={doc} onChange={draft.setDoc} errors={errors} disabled={disabled} contentHeading={t.create.contentHeading} configHeading={t.create.configHeading} />
    </div>
  );
}
