import { Disclosure } from "@agent-console/ui";
import { LIMIT_ORDER } from "./memorySettingsConfig";
import { memorySettingsMessages as t } from "./messages";

type Obj = Record<string, unknown>;

export interface LimitsBlockProps {
  /** 모듈 옵션 값(서버가 준 그대로). undefined = 못 읽음 */
  values: Obj | undefined;
  /** 옵션 스키마의 속성(키 → 제목). 제목이 있으면 키 옆 툴팁 */
  titles?: Readonly<Record<string, string>>;
}

const show = (v: unknown): string => (v === null || v === undefined || v === "" ? t.limits.unknown : typeof v === "object" ? JSON.stringify(v) : String(v));

/** 설치자 한도(읽기 전용 접힘 블록). 값은 서버가 준 그대로이고 화면에 기본값을 두지 않는다. */
export function LimitsBlock({ values, titles = {} }: LimitsBlockProps) {
  const keys = Object.keys(values ?? {});
  const ordered = [...LIMIT_ORDER.filter((k) => keys.includes(k)), ...keys.filter((k) => !LIMIT_ORDER.includes(k))];
  return (
    <Disclosure className="memset-limits" summary={t.limits.title}>
      <p className="memset-note app-muted">{t.limits.note}</p>
      {ordered.length === 0 ? (
        <p className="memset-note app-muted">{t.limits.empty}</p>
      ) : (
        <dl className="memset-kv">
          {ordered.map((k) => (
            <div key={k} className="memset-kv-row">
              <dt className="memset-mono app-muted" title={titles[k]}>{k}</dt>
              <dd className="memset-mono">{show(values?.[k])}</dd>
            </div>
          ))}
        </dl>
      )}
    </Disclosure>
  );
}
