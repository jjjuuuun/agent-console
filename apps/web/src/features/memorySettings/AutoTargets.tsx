import { Switch } from "@agent-console/ui";
import { AUTO_KEYS } from "./memorySettingsConfig";
import { memorySettingsMessages as t } from "./messages";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

export interface AutoTargetsProps {
  /** `memory.retention.auto` 값(없으면 빈 객체). 생략한 키는 스키마 기본값으로 보여 주고 원문에 넣지 않는다 */
  value: Obj;
  /** 계약 `MemoryRetentionAuto` 스키마(제목·설명·기본값의 출처) */
  schema: Obj;
  /** 등록한 프로젝트. null이면 프로젝트 기능이 꺼진 것이라 프로젝트 칸을 그리지 않는다 */
  projects: readonly { id: string; name: string }[] | null;
  onChange: (next: Obj) => void;
  disabled?: boolean;
}

const prop = (schema: Obj, key: string): Obj => (isObj(schema["properties"]) && isObj(schema["properties"][key]) ? (schema["properties"][key] as Obj) : {});
const text = (node: Obj, key: string): string => (typeof node[key] === "string" ? (node[key] as string) : "");

/** 읽은 값(생략 = 스키마 기본값). 요약 문구도 같은 계산을 쓴다 */
export function readAuto(value: Obj, schema: Obj): { library: boolean; projects: boolean; exclude: string[] } {
  const flag = (key: string) => (typeof value[key] === "boolean" ? (value[key] as boolean) : prop(schema, key)["default"] !== false);
  const raw = value[AUTO_KEYS.exclude];
  return {
    library: flag(AUTO_KEYS.library),
    projects: flag(AUTO_KEYS.projects),
    exclude: Array.isArray(raw) ? raw.filter((v): v is string => typeof v === "string") : [],
  };
}

/** 정리 규칙을 자동으로 돌릴 저장소 세 칸(공용 켬·프로젝트 켬·뺄 프로젝트). 문구는 계약 스키마의 제목·설명이다. */
export function AutoTargets({ value, schema, projects, onChange, disabled }: AutoTargetsProps) {
  const cur = readAuto(value, schema);
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const registered = new Set((projects ?? []).map((p) => p.id));
  const unknown = cur.exclude.filter((id) => !registered.has(id));
  const toggleExclude = (id: string, on: boolean) => set(AUTO_KEYS.exclude, on ? [...cur.exclude.filter((x) => x !== id), id] : cur.exclude.filter((x) => x !== id));
  const libNode = prop(schema, AUTO_KEYS.library);
  const prjNode = prop(schema, AUTO_KEYS.projects);
  const excNode = prop(schema, AUTO_KEYS.exclude);
  return (
    <fieldset className="memset-auto" data-testid="memset-auto" disabled={disabled === true}>
      <legend className="memset-strong">{t.retention.auto.title}</legend>
      <div className="memset-auto-row">
        <span className="memset-auto-label"><span id="memset-auto-lib">{text(libNode, "title")}</span><span className="memset-note app-muted">{text(libNode, "description")}</span></span>
        <Switch checked={cur.library} onChange={(v) => set(AUTO_KEYS.library, v)} ariaLabel={text(libNode, "title")} onText={t.retention.auto.on} offText={t.retention.auto.off} disabled={disabled === true} />
      </div>
      {projects === null ? null : (
        <>
          <div className="memset-auto-row">
            <span className="memset-auto-label"><span>{text(prjNode, "title")}</span><span className="memset-note app-muted">{text(prjNode, "description")}</span></span>
            <Switch checked={cur.projects} onChange={(v) => set(AUTO_KEYS.projects, v)} ariaLabel={text(prjNode, "title")} onText={t.retention.auto.on} offText={t.retention.auto.off} disabled={disabled === true} />
          </div>
          <div role="group" aria-label={text(excNode, "title")} className="memset-auto-exclude">
            <span className="memset-strong">{text(excNode, "title")}</span>
            <span className="memset-note app-muted">{text(excNode, "description")}</span>
            {projects.length === 0 && unknown.length === 0 ? <span className="memset-note app-muted">{t.retention.auto.noProjects}</span> : null}
            <ul className="memset-auto-list">
              {projects.map((p) => (
                <li key={p.id}>
                  <label><input type="checkbox" checked={cur.exclude.includes(p.id)} disabled={disabled === true || !cur.projects} onChange={(e) => toggleExclude(p.id, e.target.checked)} /> <span className="ac-ellipsis" title={p.id}>{p.name}</span></label>
                </li>
              ))}
              {unknown.map((id) => (
                <li key={id}>
                  <label><input type="checkbox" checked disabled={disabled === true || !cur.projects} onChange={(e) => toggleExclude(id, e.target.checked)} /> <span className="ac-ellipsis memset-mono" title={id}>{id}</span> <span className="memset-warn-inline">{t.retention.auto.notRegistered}</span></label>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </fieldset>
  );
}
