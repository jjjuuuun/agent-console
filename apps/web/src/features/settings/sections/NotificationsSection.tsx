import { useEffect, useMemo, useRef, useState } from "react";
import { getDefaultValue, SchemaForm, type JsonSchema, type UiSchema } from "@agent-console/schema-form";
import { getContractSchema, type NotificationSettings, type WorkspaceSettings } from "@agent-console/contracts";
import { Banner, Button } from "@agent-console/ui";
import { messages as m } from "../../../app/messages";
import { resolveNotifySettings, useNotifications, type PermissionState } from "../../notifications";
import { STRING_TAGS_FIELD, StringTagsField } from "../widgets/StringTagsField";
import type { SectionEditProps } from "./FormSections";

const FIELDS = { [STRING_TAGS_FIELD]: StringTagsField };
const TONES = { unsupported: "info", default: "warning", granted: "success", denied: "danger" } as const;

/** 권한 상태 -> 표시 문구. */
function permissionText(p: PermissionState): string {
  return m.notifications.permission[p];
}

/**
 * 생략 = 상속: 저장 값에는 이미 있던 키와 이번에 사용자가 바꾼 키만 둔다(건드리지 않은 기본값은 쓰지 않는다).
 * 한 번 저장된 키는 기본값과 같아져도 남는다(삭제는 되돌리기 동작만).
 */
export function changedKeysOnly<T extends object>(stored: T | undefined, shown: T, next: T): T {
  const out: Record<string, unknown> = { ...(stored ?? {}) };
  for (const [k, v] of Object.entries(next)) {
    if (k in out || JSON.stringify(v) !== JSON.stringify((shown as Record<string, unknown>)[k])) out[k] = v;
  }
  return out as T;
}

export interface NotificationsEditorProps {
  /** 저장 전 초안 값(없으면 기본값) */
  value: NotificationSettings | undefined;
  onChange: (next: NotificationSettings) => void;
  errors?: SectionEditProps["errors"];
  disabled?: boolean;
}

/**
 * ⑦ 알림(`ui.notifications`) 폼. 필드는 스키마에서 그리고 이벤트 목록 위젯만 주입한다.
 * 권한 상태 줄은 설정이 아니라 이 브라우저의 상태이며, 권한 요청·테스트 알림·소리 듣기는 클릭에서만 일어난다.
 */
export function NotificationsEditor({ value, onChange, errors, disabled }: NotificationsEditorProps) {
  const api = useNotifications();
  // 알려지지 않은 키를 더하는 입력은 숨긴다(계약의 확장 허용은 저장 값 보존용). 제목·설명은 섹션 머리가 맡는다.
  const schema = useMemo(() => {
    const copy: Record<string, unknown> = { ...(getContractSchema("NotificationSettings") as Record<string, unknown>), additionalProperties: false };
    delete copy["title"];
    delete copy["description"];
    return copy as JsonSchema;
  }, []);
  const effective = useMemo(() => ({ ...(getDefaultValue(schema) as NotificationSettings), ...(value ?? {}) }), [schema, value]);
  const settings = resolveNotifySettings(effective);
  const [live, setLive] = useState("");
  const requestRef = useRef<HTMLButtonElement>(null);
  const prevEnabled = useRef(settings.enabled);

  // 켜는 순간 권한이 없으면 요청 버튼으로 포커스만 보낸다(자동 요청 없음)
  useEffect(() => {
    if (!prevEnabled.current && settings.enabled && api.permission === "default") {
      requestRef.current?.focus();
      setLive(m.notifications.needPermission);
    }
    prevEnabled.current = settings.enabled;
  }, [settings.enabled, api.permission]);

  const suggestions = useMemo(() => {
    const examples = ((schema as { properties?: { events?: { examples?: unknown } } }).properties?.events?.examples ?? []) as unknown[];
    const defaults = ((getDefaultValue(schema) as NotificationSettings).events ?? []) as string[];
    return [...new Set([...examples.filter((x): x is string => typeof x === "string"), ...api.observedEvents, ...defaults])];
  }, [schema, api.observedEvents]);
  const uiSchema = useMemo<UiSchema>(
    () => ({ events: { "ui:field": STRING_TAGS_FIELD, "ui:options": { suggestions, emptyNote: m.notifications.eventsEmpty } } }),
    [suggestions],
  );

  const p = api.permission;
  return (
    <div className="app-notifications" data-enabled={settings.enabled ? "true" : "false"}>
      <div className="app-notify-status" role="status" aria-label={m.notifications.permission.label}>
        <Banner
          tone={TONES[p]}
          role="status"
          actions={
            p === "default" ? (
              <Button ref={requestRef} size="sm" onClick={() => void api.requestPermission().then((next) => setLive(m.notifications.live.permissionChanged(permissionText(next))))}>
                {m.notifications.request}
              </Button>
            ) : p === "granted" ? (
              <Button size="sm" onClick={() => api.sendTest({ sound: settings.sound })}>
                {m.notifications.sendTest}
              </Button>
            ) : undefined
          }
        >
          {permissionText(p)}
          {p === "unsupported" && api.insecureContext ? <span className="app-muted"> {m.notifications.permission.insecure}</span> : null}
          {p === "denied" ? <span className="app-muted"> {m.notifications.permission.deniedHelp}</span> : null}
        </Banner>
      </div>
      <span className="ac-sr-only" role="status" aria-live="polite">{live}</span>
      <SchemaForm
        schema={schema}
        uiSchema={uiSchema}
        value={effective}
        onChange={(next) => onChange(changedKeysOnly(value, effective, next as NotificationSettings))}
        customFields={FIELDS}
        rawJsonToggle={false}
        idPrefix="notifications"
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
      />
      <div className="app-notify-sound">
        <Button size="sm" onClick={() => void api.playSound()} disabled={disabled}>
          {m.notifications.hearSound}
        </Button>
        {settings.sound && !api.soundUnlocked ? <p className="app-muted">{m.notifications.soundLocked}</p> : null}
      </div>
    </div>
  );
}

/** 설정 화면 섹션: `ui.notifications`만 편집하고 `ui`의 다른 키(단축키)는 그대로 둔다. */
export function NotificationsSection({ value, onChange, errors, disabled }: SectionEditProps) {
  return (
    <NotificationsEditor
      value={value.ui?.notifications}
      onChange={(next) => onChange({ ...value, ui: { ...(value.ui ?? {}), notifications: next } as WorkspaceSettings["ui"] })}
      {...(errors ? { errors } : {})}
      {...(disabled === undefined ? {} : { disabled })}
    />
  );
}
