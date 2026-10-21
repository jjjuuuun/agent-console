import type { ReactNode } from "react";
import { Icon } from "./Icon";
import { ProvenanceBadge, type ProvenanceLayer } from "./Provenance";
import { joinClass } from "./Status";

/** 첨부 한 줄. 종류(리소스 종류 등)를 모르며 표시에 필요한 값만 가진다. */
export interface Attachment {
  key: string;
  title: string;
  /** 아이콘 레지스트리 이름. 없거나 모르면 제목 첫 글자 아바타. */
  iconName?: string;
  /** 첨부 방식(열린 문자열). 선택지는 `modeOptions`. */
  mode: string;
  /** 이 첨부가 속한 층의 id(표시용 보조). */
  layer?: string;
}

export interface AttachmentGroup {
  layer: ProvenanceLayer;
  items: readonly Attachment[];
  /** false면 이 층의 첨부는 읽기 전용(상속받은 것 등). */
  editable: boolean;
}

export interface AttachmentListMessages {
  /** 접근성 이름 접두어. 항목 제목이 뒤에 붙는다: "위로 이동: 제목" */
  moveUp: string;
  moveDown: string;
  remove: string;
  modeLabel: string;
  add: string;
  empty: string;
  readOnly: string;
}

export interface AttachmentListProps {
  groups: readonly AttachmentGroup[];
  /** 방식 선택지(데이터). 없으면 방식은 텍스트로만 보인다. */
  modeOptions?: readonly { value: string; label: string }[];
  /** 행 내용 대체 슬롯. 기본은 아이콘 + 제목. */
  renderRow?: (attachment: Attachment, group: AttachmentGroup) => ReactNode;
  /** 새 순서(key 배열). 위/아래 버튼으로 호출된다. */
  onReorder?: (layerId: string, orderedKeys: string[]) => void;
  onRemove?: (layerId: string, key: string) => void;
  onModeChange?: (layerId: string, key: string, mode: string) => void;
  onAdd?: (layerId: string) => void;
  messages: AttachmentListMessages;
  className?: string;
}

/**
 * 층별 첨부 목록(에이전트·팀·노드 공용). 제어형이며 변경은 콜백으로만 알린다.
 * 순서 변경은 버튼(키보드 가능)이다. 편집 불가 층은 읽기 전용으로 보인다.
 */
export function AttachmentList({ groups, modeOptions, renderRow, onReorder, onRemove, onModeChange, onAdd, messages, className }: AttachmentListProps) {
  return (
    <div className={joinClass("ac-attach", className)}>
      {groups.map((group) => {
        const layerId = group.layer.id;
        const keys = group.items.map((i) => i.key);
        const move = (index: number, delta: number) => {
          const to = index + delta;
          if (to < 0 || to >= keys.length) return;
          const next = [...keys];
          const [moved] = next.splice(index, 1);
          next.splice(to, 0, moved!);
          onReorder?.(layerId, next);
        };
        return (
          <section key={layerId} className="ac-attach-group" aria-label={group.layer.label} data-layer={layerId} data-editable={group.editable ? "true" : "false"}>
            <header className="ac-attach-head">
              <ProvenanceBadge layer={group.layer} variant="set" />
              {group.editable ? null : <span className="ac-attach-ro">{messages.readOnly}</span>}
              {group.editable && onAdd !== undefined ? (
                <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" onClick={() => onAdd(layerId)}>
                  {messages.add}
                </button>
              ) : null}
            </header>
            {group.items.length === 0 ? (
              <p className="ac-attach-empty">{messages.empty}</p>
            ) : (
              <ul className="ac-attach-items">
                {group.items.map((item, index) => (
                  <li key={item.key} className="ac-attach-row" data-key={item.key}>
                    <div className="ac-attach-main">
                      {renderRow?.(item, group) ?? (
                        <>
                          <Icon name={item.iconName} fallbackText={item.title} />
                          <span className="ac-ellipsis" title={item.title}>{item.title}</span>
                        </>
                      )}
                    </div>
                    {modeOptions !== undefined && group.editable && onModeChange !== undefined ? (
                      <select
                        className="ac-input ac-attach-mode"
                        aria-label={`${messages.modeLabel}: ${item.title}`}
                        value={item.mode}
                        onChange={(e) => onModeChange(layerId, item.key, e.target.value)}
                      >
                        {modeOptions.some((o) => o.value === item.mode) ? null : <option value={item.mode}>{item.mode}</option>}
                        {modeOptions.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="ac-tag ac-attach-modetext">{modeOptions?.find((o) => o.value === item.mode)?.label ?? item.mode}</span>
                    )}
                    {group.editable ? (
                      <div className="ac-attach-actions">
                        {onReorder === undefined ? null : (
                          <>
                            <button type="button" className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" aria-label={`${messages.moveUp}: ${item.title}`} disabled={index === 0} onClick={() => move(index, -1)}>
                              <span aria-hidden="true">↑</span>
                            </button>
                            <button type="button" className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" aria-label={`${messages.moveDown}: ${item.title}`} disabled={index === group.items.length - 1} onClick={() => move(index, 1)}>
                              <span aria-hidden="true">↓</span>
                            </button>
                          </>
                        )}
                        {onRemove === undefined ? null : (
                          <button type="button" className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" aria-label={`${messages.remove}: ${item.title}`} onClick={() => onRemove(layerId, item.key)}>
                            <span aria-hidden="true">×</span>
                          </button>
                        )}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
