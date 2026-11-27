import { useMemo, useSyncExternalStore } from "react";
import { useT, type Console18n, type Translate } from "@agent-console/i18n";
import { useOptionalI18n } from "./AppI18n";

const versions = new WeakMap<Console18n, Map<string, number>>();

function versionOf(i18n: Console18n, namespace: string): number {
  return versions.get(i18n)?.get(namespace) ?? 0;
}

function bumpVersion(i18n: Console18n, namespace: string): void {
  let map = versions.get(i18n);
  if (!map) versions.set(i18n, (map = new Map()));
  map.set(namespace, (map.get(namespace) ?? 0) + 1);
}

/**
 * 자기 네임스페이스의 묶음이 들어오거나 언어가 바뀔 때만 알린다. 다른 네임스페이스 묶음(부팅 때 수십 개가 차례로 들어온다)마다
 * 모든 표를 다시 만들면 화면 하나를 그리는 데 수백 번의 표 만들기가 돌아 테스트·저사양에서 느려진다.
 */
function subscribe(i18n: Console18n, namespace: string, onChange: () => void): () => void {
  const bump = () => {
    bumpVersion(i18n, namespace);
    onChange();
  };
  // 같은 네임스페이스를 쓰는 표가 여럿이면 알림마다 버전이 여러 번 오르지만, 값이 달라지기만 하면 되므로 상관없다.
  const onStore = (_language?: string, ns?: string) => {
    if (ns === undefined || ns === namespace) bump();
  };
  i18n.store.on("added", onStore);
  i18n.store.on("removed", onStore);
  i18n.on("languageChanged", bump);
  return () => {
    i18n.store.off("added", onStore);
    i18n.store.off("removed", onStore);
    i18n.off("languageChanged", bump);
  };
}

interface CachedTable {
  i18n: Console18n;
  namespace: string;
  language: string;
  version: number;
  value: unknown;
}

/**
 * 표 만들기 함수(모듈 최상위, identity 고정)마다 마지막 결과 하나를 나눠 쓴다. 같은 표를 쓰는 컴포넌트가 수십 개여도
 * 언어·묶음이 같으면 표 만들기(번역 함수 수백 번 호출)는 한 번만 돈다.
 */
const tableCache = new WeakMap<(t: Translate) => unknown, CachedTable>();

/**
 * 한 네임스페이스의 문구 표(같은 모양의 객체: 글자·`(값) => 글자` 함수)를 현재 언어로 만든다.
 * 표 만들기는 `(t) => ({ ... })` 순수 함수이고, 언어나 묶음이 바뀔 때만 다시 만든다.
 * @param namespace 앱 묶음 네임스페이스(`locales/<언어>/<namespace>.json`).
 * @param factory 번역 함수를 받아 표를 돌려주는 함수(모듈 최상위에 두어 identity를 고정한다).
 */
export function useMessageTable<M>(namespace: string, factory: (t: Translate) => M): M {
  const t = useT(namespace);
  const i18n = useOptionalI18n();
  const version = useSyncExternalStore(
    (onChange) => (i18n ? subscribe(i18n, namespace, onChange) : () => undefined),
    () => (i18n ? versionOf(i18n, namespace) : 0),
  );
  return useMemo(() => {
    if (!i18n) return factory(t);
    const hit = tableCache.get(factory);
    if (hit && hit.i18n === i18n && hit.namespace === namespace && hit.language === t.language && hit.version === version) return hit.value as M;
    const value = factory(t);
    tableCache.set(factory, { i18n, namespace, language: t.language, version, value });
    return value;
  }, [factory, t, version, i18n, namespace]);
}
