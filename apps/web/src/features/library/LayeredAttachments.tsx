import { useState } from "react";
import type { ResourceAttachment, ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import { AttachmentList, type Attachment, type ProvenanceLayer } from "@agent-console/ui";
import { newAttachment } from "../../lib/serialize";
import { libraryMessages as t, modeLabel } from "./messages";
import { AttachmentProblems } from "../../definition/AttachmentProblems";
import { DescriptorIcon } from "./DescriptorIcon";
import { ResourcePicker } from "./ResourcePicker";

/** 첨부가 속한 층 하나. `editable`이 아닌 층은 읽기 전용(상속) 목록이다. */
export interface AttachmentLayerData {
  layer: ProvenanceLayer;
  attachments: readonly ResourceAttachment[];
  editable: boolean;
  /** 첨부 번호 -> 서버 오류 메시지(저장 거부 사유) */
  errors?: Readonly<Record<number, readonly string[]>>;
}

export interface LayeredAttachmentsProps {
  layers: readonly AttachmentLayerData[];
  resources: readonly ResourceSummary[];
  types: readonly ResourceTypeDescriptor[];
  /** 첨부 방식 선택지(계약 enum에서 읽은 값) */
  modes: readonly string[];
  /** 한 층의 첨부 목록이 바뀌었다 */
  onChange: (layerId: string, next: ResourceAttachment[]) => void;
  /** 선택 팝업 하단의 [새 리소스 만들기 →] */
  onCreateResource?: () => void;
  /** 목록 아래에 붙일 설명(예: 실행 때 합쳐지는 순서) */
  footer?: string;
  /** 읽기 전용 층의 행에 [제외] 버튼을 붙인다(누르면 `(layerId, index)`). 라벨은 `excludeLabel` */
  onExclude?: (layerId: string, index: number) => void;
  excludeLabel?: string;
}

const keyOf = (index: number, ref: string) => `${index}:${ref}`;
const indexOfKey = (key: string) => Number(key.split(":", 1)[0]);

/**
 * 층별 첨부 목록 편집(공통 읽기 전용 → … → 편집 가능한 층). `AttachmentList` 위에 리소스 고르기와 방식 선택을 얹은 표현 컴포넌트.
 * 팀 공용·에이전트·노드 층이 같은 컴포넌트를 쓴다. 서버·층 이름은 모른다.
 */
export function LayeredAttachments({ layers, resources, types, modes, onChange, onCreateResource, footer, onExclude, excludeLabel }: LayeredAttachmentsProps) {
  const [adding, setAdding] = useState<string | null>(null);
  const byId = new Map(resources.map((r) => [r.id, r]));
  const typeById = new Map(types.map((x) => [x.id, x]));
  const target = layers.find((l) => l.layer.id === adding);

  const groups = layers.map((l) => ({
    layer: l.layer,
    editable: l.editable,
    items: l.attachments.map((a, i): Attachment => {
      const res = byId.get(a.ref);
      const hint = res === undefined ? undefined : typeById.get(res.type)?.ui_hints?.icon;
      return { key: keyOf(i, a.ref), title: res?.name ?? `${a.ref} ${t.attach.missing}`, mode: a.mode ?? "add", ...(typeof hint === "string" ? { iconName: hint } : {}) };
    }),
  }));
  const layerOf = (id: string) => layers.find((l) => l.layer.id === id);

  return (
    <div className="lib-attachments">
      <AttachmentList
        groups={groups}
        modeOptions={modes.map((m) => ({ value: m, label: modeLabel(m) }))}
        onReorder={(id, keys) => {
          const cur = layerOf(id)?.attachments ?? [];
          onChange(id, keys.map((k) => cur[indexOfKey(k)]!).filter(Boolean));
        }}
        onRemove={(id, key) => onChange(id, (layerOf(id)?.attachments ?? []).filter((_, i) => i !== indexOfKey(key)))}
        onModeChange={(id, key, mode) => onChange(id, (layerOf(id)?.attachments ?? []).map((a, i) => (i === indexOfKey(key) ? { ...a, mode: mode as ResourceAttachment["mode"] } : a)))}
        onAdd={(id) => setAdding(id)}
        {...(onExclude === undefined
          ? {}
          : {
              renderRow: (att: Attachment, group: { layer: { id: string }; editable: boolean }) => {
                const base = (
                  <>
                    <DescriptorIcon hint={att.iconName} title={att.title} size={16} />
                    <span className="ac-ellipsis">{att.title}</span>
                  </>
                );
                if (group.editable) return base;
                return (
                  <>
                    {base}
                    <button type="button" className="app-link-btn" onClick={() => onExclude(group.layer.id, indexOfKey(att.key))}>
                      {excludeLabel}
                    </button>
                  </>
                );
              },
            })}
        messages={t.attach}
      />
      {layers.map((l) => (
        <AttachmentProblems key={l.layer.id} attachments={l.attachments} {...(l.errors ? { errors: l.errors } : {})} titleOf={(a) => byId.get(a.ref)?.name ?? a.ref} />
      ))}
      {footer ? <p className="app-muted lib-footnote">{footer}</p> : null}
      {target === undefined ? null : (
        <ResourcePicker
          open
          resources={resources}
          types={types}
          exclude={new Set(target.attachments.map((a) => a.ref))}
          onPick={(r) => {
            onChange(target.layer.id, [...target.attachments, newAttachment(r.id, modes[0])]);
            setAdding(null);
          }}
          {...(onCreateResource ? { onCreateNew: onCreateResource } : {})}
          onClose={() => setAdding(null)}
        />
      )}
    </div>
  );
}
