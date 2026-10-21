import { useMemo, type ReactNode } from "react";
import { useNavigate } from "react-router";
import type { Agent, EffectiveSettings } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { Banner, Disclosure } from "@agent-console/ui";
import { HintBanner } from "../../app/hints";
import { useWorkspaceSettings } from "../../app/queries";
import { Skeleton } from "../settings";
import { Field, AgentSettingsForm, editLayerOf, inheritedProvenance, inheritedValue, toFormLayers, Avatar, AVATAR_COLOR_TOKENS, readAvatarUi, resolveAvatarColor, withAvatarUi, layerSourcePath } from "../library";
import { settingsOf, withSettings } from "./agentLogic";
import { agentMessages as t } from "./messages";

/** 설정 탭에서 폼 밖(리소스 탭)에서 편집하는 필드. */
const HIDDEN_IN_SETTINGS: readonly string[] = ["resources"];

/** 에이전트 편집 콜백: 값 또는 "현재 초안 → 다음 초안" 함수. 함수 형태는 늦게 도착한 폼 이벤트가 낡은 초안을 되살리지 못하게 한다. */
export type AgentUpdate = Agent | ((current: Agent) => Agent);

export interface AgentEditorFormProps {
  /** `edit` = 저장된 에이전트(상속 값은 서버 유효 설정), `create` = 아직 없는 에이전트(상속 값은 공통 기본값, 안내·층 이동 없음) */
  mode?: "edit" | "create";
  agent: Agent;
  onChange: (next: AgentUpdate) => void;
  /** 서버 유효 설정(`edit`에서만 의미). 없으면 공통 기본값만 상속으로 본다 */
  effective?: EffectiveSettings | undefined;
  effectiveError?: Error | null;
  /** 유효 설정을 읽는 중(출처 값이 정해지기 전에는 폼을 그리지 않는다) */
  effectiveLoading?: boolean;
  errors: FormError[];
  disabled: boolean;
  /** 이름 입력 바로 아래에 끼울 칸(`create`의 id 입력 등) */
  afterName?: ReactNode;
  /** 정체성 묶음 끝에 끼울 칸(프로젝트 선택 등) */
  identityExtra?: ReactNode;
}

/**
 * 에이전트 편집 폼: 정체성(이름·역할·설명) + 표시(고급) + 설정 출처 표시 폼.
 * 에이전트 화면의 [설정] 탭과 팀 편집기의 `CreateDefinitionDrawer`가 같은 컴포넌트를 쓴다(필드 복제 없음).
 * 정체성은 설정 계층에 참여하지 않아 배지가 없다.
 */
export function AgentEditorForm({ mode = "edit", agent, onChange, effective, effectiveError = null, effectiveLoading = false, errors, disabled, afterName, identityExtra }: AgentEditorFormProps) {
  const navigate = useNavigate();
  const create = mode === "create";
  const common = useWorkspaceSettings();
  const layers = useMemo(() => toFormLayers(effective), [effective]);
  const editLayerId = editLayerOf(effective) ?? "";
  const sourceByLayer = useMemo(() => new Map((effective?.layers ?? []).map((l) => [l.id, l.source])), [effective]);
  // 만들기: 저장 전이라 서버 유효 설정이 없다. 공통 기본값(리소스 제외)을 상속 값으로 보여 준다.
  const createBase = useMemo(() => {
    const { resources: _own, ...rest } = (common.data?.value.agent_defaults ?? {}) as Record<string, unknown>;
    void _own;
    return rest;
  }, [common.data]);
  const effBackend = typeof effective?.value.backend === "string" ? effective.value.backend : create && typeof createBase["backend"] === "string" ? createBase["backend"] : null;
  const backendId = typeof agent.backend === "string" ? agent.backend : effBackend;
  const nameEmpty = agent.name.trim() === "";
  const set = (patch: Partial<Agent>) => onChange((cur) => ({ ...cur, ...patch }));
  const setText = (key: "role" | "description", v: string) => {
    onChange((cur) => {
      const next = { ...cur };
      if (v === "") delete (next as Record<string, unknown>)[key];
      else (next as Record<string, unknown>)[key] = v;
      return next;
    });
  };
  return (
    <div className="lib-form">
      {create ? null : <HintBanner id="agents">{t.settings.hint}</HintBanner>}
      <fieldset className="lib-fieldset" disabled={disabled}>
        <legend>{t.identity.title}</legend>
        <Field label={t.identity.name} error={nameEmpty && !create ? t.identity.nameRequired : undefined}>
          {(a) => <input {...a} data-agent-name="" className="ac-input" value={agent.name} onChange={(e) => set({ name: e.target.value })} maxLength={120} />}
        </Field>
        {afterName}
        <Field label={t.identity.role}>
          {(a) => <input {...a} className="ac-input" value={agent.role ?? ""} onChange={(e) => setText("role", e.target.value)} />}
        </Field>
        <Field label={t.identity.description} hint={t.identity.descriptionHint}>
          {(a) => <textarea {...a} className="ac-input" rows={2} value={agent.description ?? ""} onChange={(e) => setText("description", e.target.value)} />}
        </Field>
        {identityExtra}
      </fieldset>
      <AgentDisplayFields agent={agent} onChange={onChange} disabled={disabled} />
      {effectiveError ? <Banner tone="warning">{t.settings.effectiveFailed}</Banner> : null}
      {effectiveLoading ? <Skeleton rows={6} /> : <AgentSettingsForm
        value={settingsOf(agent, HIDDEN_IN_SETTINGS)}
        onChange={(next) => onChange((cur) => withSettings(cur, next, HIDDEN_IN_SETTINGS))}
        layers={layers.length > 0 ? layers : [{ id: "layer-own", label: t.resources.layerFallback }]}
        editLayerId={layers.length > 0 ? editLayerId : "layer-own"}
        baseValue={create ? createBase : inheritedValue(effective, editLayerId)}
        provenance={inheritedProvenance(effective, editLayerId)}
        backendId={backendId}
        hideKeys={HIDDEN_IN_SETTINGS}
        errors={errors}
        disabled={disabled}
        idPrefix="agent-settings"
        onOpenLayer={(layerId) => {
          if (create) return;
          const to = layerSourcePath(sourceByLayer.get(layerId));
          if (to !== undefined && layerId !== editLayerId) void navigate(to);
        }}
      />}
    </div>
  );
}

/** 고급 "표시": `attributes.ui.icon`·`color`. 비우면 이름 첫 글자 + id 해시 색(기본). */
function AgentDisplayFields({ agent, onChange, disabled }: { agent: Agent; onChange: (next: AgentUpdate) => void; disabled: boolean }) {
  const ui = readAvatarUi(agent.attributes);
  const listId = `agent-color-${agent.id}`;
  const apply = (patch: Partial<{ icon: string; color: string }>) => {
    onChange((cur) => {
      const attributes = withAvatarUi(cur.attributes, patch);
      const next = { ...cur } as Record<string, unknown>;
      if (attributes === undefined) delete next["attributes"];
      else next["attributes"] = attributes;
      return next as unknown as Agent;
    });
  };
  const iconBad = ui.icon !== "" && Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(ui.icon)).length > 2;
  const colorBad = ui.color !== "" && resolveAvatarColor(ui.color) === undefined;
  return (
    <Disclosure summary={t.display.title} className="lib-display">
      <fieldset className="lib-fieldset" disabled={disabled}>
        <Field label={t.display.icon} hint={t.display.iconHint} error={iconBad ? t.display.iconInvalid : undefined}>
          {(a) => <input {...a} className="ac-input" value={ui.icon} onChange={(e) => apply({ icon: e.target.value })} maxLength={8} />}
        </Field>
        <Field label={t.display.color} hint={t.display.colorHint} error={colorBad ? t.display.colorInvalid : undefined}>
          {(a) => (
            <>
              <input {...a} className="ac-input" list={listId} value={ui.color} onChange={(e) => apply({ color: e.target.value })} />
              <datalist id={listId}>
                {AVATAR_COLOR_TOKENS.map((n) => (
                  <option key={n} value={n} label={t.display.colorOption(n)} />
                ))}
              </datalist>
            </>
          )}
        </Field>
        <div className="lib-row-main" aria-label={t.display.preview}>
          <Avatar id={agent.id} name={agent.name} attributes={agent.attributes} size={28} />
          <span className="app-muted">{agent.name}</span>
        </div>
      </fieldset>
    </Disclosure>
  );
}

