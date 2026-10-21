import { useMemo } from "react";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph, NodeSpec } from "@agent-console/contracts";
import { SchemaForm } from "@agent-console/schema-form";
import { Disclosure } from "@agent-console/ui";
import { getAt, setAt, unsetAt } from "../../lib/jsonPointer";
import { DEFAULT_TEAM_CONVENTIONS, type TeamConventions } from "./conventions";
import { effectiveStrategyId } from "./edgeChips";
import { delegationMessages as t } from "./messages";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 위임자 노드에서 나가는 위임 연결이 쓰는 방식 중 설정 스키마(속성이 있는 것)를 가진 방식. 연결 종류의 `invocation` 속성으로 알아본다. */
export function delegatorStrategies(
  node: Pick<NodeSpec, "id">,
  graph: Pick<Graph, "edges">,
  edgeTypes: readonly EdgeTypeDescriptor[],
  strategies: readonly DelegationStrategyDescriptor[],
  conventions: TeamConventions = DEFAULT_TEAM_CONVENTIONS,
): DelegationStrategyDescriptor[] {
  const kinds = new Map(edgeTypes.map((e) => [e.id, e]));
  const ids = new Set<string>();
  for (const edge of graph.edges ?? []) {
    if (edge.source.node !== node.id) continue;
    const id = effectiveStrategyId(edge, kinds.get(edge.kind), conventions);
    if (id !== undefined) ids.add(id);
  }
  return strategies.filter((s) => ids.has(s.id) && isObj(s.config_schema?.["properties"]) && Object.keys(s.config_schema!["properties"] as Obj).length > 0);
}

export interface DelegationSettingsProps {
  node: NodeSpec;
  graph: Pick<Graph, "edges">;
  edgeTypes: readonly EdgeTypeDescriptor[];
  strategies: readonly DelegationStrategyDescriptor[];
  /** 노드 config를 바꾼다(비운 방식 설정은 키를 지운다) */
  onChange(config: Record<string, unknown>): void;
  disabled?: boolean | undefined;
  conventions?: TeamConventions;
}

/**
 * 위임 방식 설정 폼(screen-delegation.md 의존 5R.9): 이 노드가 위임자로 쓰는 방식 중 `config_schema`가 있는 방식마다 접힘 블록.
 * 값은 노드 config의 `TeamConventions.nodeDelegation` 아래 `{방식 id: 설정}`이다. 방식 이름·설정 키는 코드에 없고 디스크립터가 그린다.
 * 해당 방식이 없으면 아무것도 그리지 않는다.
 */
export function DelegationSettings({ node, graph, edgeTypes, strategies, onChange, disabled, conventions = DEFAULT_TEAM_CONVENTIONS }: DelegationSettingsProps) {
  const list = useMemo(() => delegatorStrategies(node, graph, edgeTypes, strategies, conventions), [node, graph, edgeTypes, strategies, conventions]);
  if (list.length === 0) return null;
  const config = (node.config ?? {}) as Obj;
  return (
    <section className="lib-fieldset" aria-label={t.settings.title}>
      <span className="lib-field-label">{t.settings.title}</span>
      {list.map((s) => {
        const pointer = `${conventions.nodeDelegation}/${s.id.replace(/~/g, "~0").replace(/\//g, "~1")}`;
        const value = getAt(config, pointer);
        return (
          <Disclosure key={s.id} summary={<strong>{s.title}</strong>}>
            <div className="lib-form">
              {s.description ? <p className="app-muted lib-field-note">{s.description}</p> : null}
              <SchemaForm
                schema={s.config_schema as Obj}
                value={isObj(value) ? value : {}}
                onChange={(next) => {
                  // 폼이 비운 칸은 값이 undefined인 키로 오므로 JSON으로 한 번 걸러 희소하게 저장한다
                  const sparse: unknown = isObj(next) ? JSON.parse(JSON.stringify(next)) : undefined;
                  const empty = !isObj(sparse) || Object.keys(sparse).length === 0;
                  onChange((empty ? unsetAt(config, pointer) : setAt(config, pointer, sparse)) as Record<string, unknown>);
                }}
                rawJsonToggle={false}
                {...(disabled === undefined ? {} : { disabled })}
                idPrefix={`delegation-${node.id}-${s.id}`}
                advancedStorageKey={`delegation:${s.id}`}
              />
            </div>
          </Disclosure>
        );
      })}
    </section>
  );
}
