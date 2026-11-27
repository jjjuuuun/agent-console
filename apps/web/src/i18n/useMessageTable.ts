import { useMemo, useSyncExternalStore } from "react";
import { useT, type Console18n, type Translate } from "@agent-console/i18n";
import { useOptionalI18n } from "./AppI18n";

const versions = new WeakMap<Console18n, number>();

function subscribe(i18n: Console18n, onChange: () => void): () => void {
  const bump = () => {
    versions.set(i18n, (versions.get(i18n) ?? 0) + 1);
    onChange();
  };
  i18n.store.on("added", bump);
  i18n.store.on("removed", bump);
  i18n.on("languageChanged", bump);
  return () => {
    i18n.store.off("added", bump);
    i18n.store.off("removed", bump);
    i18n.off("languageChanged", bump);
  };
}

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
    (onChange) => (i18n ? subscribe(i18n, onChange) : () => undefined),
    () => (i18n ? (versions.get(i18n) ?? 0) : 0),
  );
  // eslint-disable-next-line react-hooks/exhaustive-deps -- version은 묶음이 늦게 들어올 때 다시 만들기 위한 키
  return useMemo(() => factory(t), [factory, t, version]);
}
