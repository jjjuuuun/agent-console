import { useId, useState } from "react";
import type { GraphEditorMessages } from "../messages";
import { defaultMessages } from "../messages";
import type { ToggleInfo, ToggleOptions } from "../logic/team";

export interface RoleToggleRowProps {
  info: ToggleInfo;
  /** 토글 라벨(예: "입구"). 호출자가 messages에서 고른다 */
  label: string;
  /** 켜기/끄기. 켤 때 종류·상대 노드를 골랐다면 options에 담긴다 */
  onToggle: (on: boolean, options?: ToggleOptions) => void;
  messages?: GraphEditorMessages;
}

/**
 * 노드 패널용 토글 한 줄(입구/답변/묻기). 상태는 `getRoleToggleInfo`가 준 `info`로만 그린다.
 * 켤 수 없으면 비활성 + 이유를 보인다. 종류·상대 노드 후보가 둘 이상이면 고르는 선택 상자를 보인다.
 */
export function RoleToggleRow(props: RoleToggleRowProps) {
  const m = props.messages ?? defaultMessages;
  const uid = useId();
  const { info } = props;
  const [kindId, setKindId] = useState<string | undefined>(undefined);
  const [userNodeId, setUserNodeId] = useState<string | undefined>(undefined);
  const usableKinds = info.kinds.filter((k) => k.counterpartIds.length > 0);
  const kind = usableKinds.find((k) => k.id === kindId) ?? usableKinds[0];
  const nodes = info.userNodes.filter((u) => kind === undefined || kind.counterpartIds.includes(u.id));
  const disabled = !info.available;
  const reason = info.reasonIfUnavailable !== undefined ? m.toggleUnavailable[info.reasonIfUnavailable] ?? info.reasonIfUnavailable : undefined;
  const choose = !info.on && !disabled && (usableKinds.length > 1 || nodes.length > 1);
  return (
    <div className="ac-ge-toggle-row">
      <label className="ac-ge-toggle-label">
        <input
          type="checkbox"
          role="switch"
          checked={info.on}
          disabled={disabled && !info.on}
          aria-describedby={reason !== undefined ? `${uid}-why` : undefined}
          onChange={(e) => {
            const on = e.target.checked;
            const options: ToggleOptions = {};
            // 후보가 여럿이면 화면에 보이는 선택값을 명시적으로 넘긴다(편집기는 첫 후보를 대신 고르지 않는다)
            if (on && usableKinds.length > 1 && kind !== undefined) options.kindId = kind.id;
            if (on && nodes.length > 1) options.userNodeId = nodes.some((n) => n.id === userNodeId) ? userNodeId : nodes[0]?.id;
            props.onToggle(on, Object.keys(options).length > 0 ? options : undefined);
          }}
        />
        <span>{props.label}</span>
        {info.count > 0 && <span className="ac-ge-toggle-count">{info.count}</span>}
      </label>
      {reason !== undefined && (
        <span id={`${uid}-why`} className="ac-ge-toggle-why">
          {reason}
        </span>
      )}
      {choose && usableKinds.length > 1 && (
        <select aria-label={m.toggleKind} value={kind?.id} onChange={(e) => setKindId(e.target.value)} className="ac-ge-select">
          {usableKinds.map((k) => (
            <option key={k.id} value={k.id}>
              {k.title}
            </option>
          ))}
        </select>
      )}
      {choose && nodes.length > 1 && (
        <select aria-label={m.toggleUserNode} value={userNodeId ?? nodes[0]?.id} onChange={(e) => setUserNodeId(e.target.value)} className="ac-ge-select">
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
