/**
 * 실행 라벨 → 머리 칩 모델(순수 함수, screen-sdd §12.1). 표시 규칙(`LabelDisplay`)은 서버 모듈이 선언한 데이터이고
 * 웹은 라벨 키를 모른 채 규칙의 `key`만 비교한다. 눌렀을 때 열 화면은 `target.role`(웹 라우트 역할)을 `pathOfRole`로 경로로 푼다.
 */
import type { LabelDisplay } from "@agent-console/contracts";

export interface LabelSegment {
  /** 칩 앞에 붙는 이름(사용자 언어, 규칙 `title`) */
  title: string;
  value: string;
  /** 눌렀을 때 열 경로. 역할을 맡은 화면이 없거나 id 라벨이 없으면 undefined(링크 없는 칩) */
  href: string | undefined;
}

export interface LabelChipModel {
  /** 같은 `group`이면 한 칩 안에 `·`로 이어진다 */
  id: string;
  segments: LabelSegment[];
}

export interface LabelChips {
  chips: LabelChipModel[];
  /** 규칙에 없는 라벨(키 → 값). 비어 있지 않으면 `라벨 n` 한 칩으로 묶인다 */
  unmatched: Record<string, string>;
}

/** 질의 틀의 `{value}`·`{labels.<키>}`만 치환한다(값은 URL 인코딩). 알 수 없는 자리는 그대로 둔다. */
export function fillQuery(template: string, value: string, labels: Readonly<Record<string, string>>): string {
  return template.replace(/\{(value|labels\.[^}]+)\}/g, (whole, name: string) => {
    if (name === "value") return encodeURIComponent(value);
    const key = name.slice("labels.".length);
    const v = labels[key];
    return v === undefined ? whole : encodeURIComponent(v);
  });
}

export function resolveLabelChips(labels: Readonly<Record<string, string>> | undefined, display: readonly LabelDisplay[], pathOfRole: (role: string) => string | undefined): LabelChips {
  const all = labels ?? {};
  const rules = [...display].sort((a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER));
  const known = new Set<string>();
  const chips: LabelChipModel[] = [];
  const byGroup = new Map<string, LabelChipModel>();
  for (const rule of rules) {
    const value = all[rule.key];
    if (value === undefined || known.has(rule.key)) continue;
    known.add(rule.key);
    let href: string | undefined;
    const target = rule.target ?? null;
    if (target !== null) {
      const base = pathOfRole(target.role);
      const id = all[target.id_from];
      if (base !== undefined && id !== undefined) {
        const q = target.query == null || target.query === "" ? "" : `?${fillQuery(target.query, value, all)}`;
        href = `${base}/${encodeURIComponent(id)}${q}`;
      }
    }
    const segment: LabelSegment = { title: rule.title, value, href };
    const group = rule.group ?? null;
    const existing = group === null ? undefined : byGroup.get(group);
    if (existing !== undefined) existing.segments.push(segment);
    else {
      const chip: LabelChipModel = { id: group ?? rule.key, segments: [segment] };
      chips.push(chip);
      if (group !== null) byGroup.set(group, chip);
    }
  }
  const unmatched = Object.fromEntries(Object.entries(all).filter(([k]) => !known.has(k)));
  return { chips, unmatched };
}
