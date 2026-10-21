import { useState } from "react";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import { Button, Dialog } from "@agent-console/ui";
import { ResourceTypeGrid } from "./ResourceTypeGrid";
import { DEFINITION_KINDS, DescriptorIcon, NewDefinitionDialog, type NewDefinitionValues, libraryMessages as lm } from "../library";
import { useNewScope } from "../projects";
import { resourceMessages as t } from "./messages";

export interface CreateResourceDialogProps {
  types: readonly ResourceTypeDescriptor[];
  existingIds: ReadonlySet<string>;
  /** 미리 고른 종류(종류 칩이 선택된 상태에서 만들기) */
  initialTypeId?: string | undefined;
  busy: boolean;
  error: string | null;
  onCreate: (typeId: string, values: NewDefinitionValues, scope: { project?: string }) => void;
  onClose: () => void;
}

/** 새 리소스: ① 종류 고르기(카드 격자, 디스크립터) ② 이름·id·설명. 종류가 많으면 검색한다. */
export function CreateResourceDialog({ types, existingIds, initialTypeId, busy, error, onCreate, onClose }: CreateResourceDialogProps) {
  const [typeId, setTypeId] = useState<string | null>(initialTypeId ?? (types.length === 1 ? (types[0]?.id ?? null) : null));
  const chosen = types.find((x) => x.id === typeId);
  const scope = useNewScope(DEFINITION_KINDS.resource ?? "");

  if (chosen === undefined) {
    return (
      <Dialog open title={t.create.typeStep} onClose={onClose} wide actions={<Button onClick={onClose}>{lm.cancel}</Button>}>
        <ResourceTypeGrid types={types} onPick={setTypeId} />
      </Dialog>
    );
  }
  return (
    <NewDefinitionDialog
      open
      title={t.create.title}
      submitLabel={t.create.submit}
      existingIds={existingIds}
      fallbackId={t.create.fallbackId}
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={(v) => onCreate(chosen.id, v, scope.patch)}
      extra={
        <>
        <p className="ac-text lib-row-main">
          <DescriptorIcon hint={chosen.ui_hints?.icon} title={chosen.title} size={16} />
          <span>{t.create.chosen(chosen.title)}</span>
          {types.length > 1 ? (
            <button type="button" className="app-link-btn" onClick={() => setTypeId(null)}>
              {t.create.change}
            </button>
          ) : null}
        </p>
        {scope.field}
        </>
      }
    />
  );
}
