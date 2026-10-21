import { useState } from "react";
import type { ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { AttachmentList, Button, type Attachment } from "@agent-console/ui";
import { newAttachment } from "../../../lib/serialize";
import { messages as m } from "../../../app/messages";
import { AttachmentProblems } from "../../../definition/AttachmentProblems";
export const ATTACHMENTS_FIELD = "attachments";

export interface AttachmentsOptions {
  /** 붙일 수 있는 리소스(서버 목록) */
  resources?: readonly ResourceSummary[];
  /** 아이콘 힌트용 리소스 종류 디스크립터 */
  types?: readonly ResourceTypeDescriptor[];
  /** 첨부 방식 선택지(계약 enum) */
  modes?: readonly string[];
  /** 이 층의 라벨(그룹 제목) */
  layerLabel: string;
  /** 목록 아래 경고 문구 */
  warning?: string;
  /** 첨부 번호 -> 서버 오류 메시지(저장 거부 사유) */
  errors?: Readonly<Record<number, readonly string[]>>;
}

interface Row {
  ref: string;
  mode?: string;
  [k: string]: unknown;
}

/** 첨부(`ResourceAttachment[]`) 편집: `AttachmentList` 위의 얇은 필드. 리소스 종류 이름은 코드에 없다(디스크립터 힌트). */
export function AttachmentsField({ value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as unknown as AttachmentsOptions;
  const rows: Row[] = Array.isArray(value) ? (value as Row[]) : [];
  const [pick, setPick] = useState("");
  const locked = disabled || readonly;
  const byId = new Map((opts.resources ?? []).map((r) => [r.id, r]));
  const typeOf = new Map((opts.types ?? []).map((t) => [t.id, t]));
  const items: Attachment[] = rows.map((r, i) => {
    const res = byId.get(r.ref);
    const hints = res === undefined ? undefined : typeOf.get(res.type)?.ui_hints;
    return { key: `${i}:${r.ref}`, title: res?.name ?? r.ref, mode: r.mode ?? "add", ...(typeof hints?.icon === "string" ? { iconName: hints.icon } : {}) };
  });
  const indexOf = (key: string) => Number(key.split(":", 1)[0]);
  const available = (opts.resources ?? []).filter((r) => !rows.some((x) => x.ref === r.id));

  return (
    <div role="group" aria-label={label}>
      <AttachmentList
        groups={[{ layer: { id: "layer", label: opts.layerLabel, index: 0 }, items, editable: !locked }]}
        modeOptions={(opts.modes ?? []).map((v) => ({ value: v, label: v }))}
        onReorder={(_layer, keys) => onChange(keys.map((k) => rows[indexOf(k)]))}
        onRemove={(_layer, key) => onChange(rows.filter((_, i) => i !== indexOf(key)))}
        onModeChange={(_layer, key, mode) => onChange(rows.map((r, i) => (i === indexOf(key) ? { ...r, mode } : r)))}
        messages={{ moveUp: m.settings.attach.moveUp, moveDown: m.settings.attach.moveDown, remove: m.settings.attach.remove, modeLabel: m.settings.attach.mode, add: "", empty: m.settings.attach.empty, readOnly: m.settings.attach.readOnly }}
      />
      <AttachmentProblems attachments={rows as never} {...(opts.errors ? { errors: opts.errors } : {})} titleOf={(a) => byId.get(a.ref)?.name ?? a.ref} />
      {locked ? null : (
        <div className="app-attach-add">
          <select aria-label={m.settings.attach.pick} value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">{available.length === 0 ? m.settings.attach.pickEmpty : m.settings.attach.pickPlaceholder}</option>
            {available.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={pick === ""}
            onClick={() => {
              onChange([...rows, newAttachment(pick, opts.modes?.[0])]);
              setPick("");
            }}
          >
            {m.settings.keyValue.add}
          </Button>
        </div>
      )}
      {opts.warning === undefined ? null : (
        <p className="app-muted app-attach-warning" role="note">
          ▲ {opts.warning}
        </p>
      )}
    </div>
  );
}
