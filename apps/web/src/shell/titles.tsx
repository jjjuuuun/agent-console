import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface TitleValue {
  override: string | null;
  setOverride: (title: string | null) => void;
  /** 문서 제목 끝에 붙는 보조 글(예: 사용량 한 줄). 없으면 제목은 이전과 같다 */
  suffix: string | null;
  setSuffix: (suffix: string | null) => void;
}

const TitleContext = createContext<TitleValue>({ override: null, setOverride: () => {}, suffix: null, setSuffix: () => {} });

/** 화면이 문서 제목의 화면 이름을 직접 정할 수 있게 한다(셸이 `(n) … · Agent Console` 형태로 마무리). */
export function PageTitleProvider({ children }: { children: ReactNode }) {
  const [override, setOverride] = useState<string | null>(null);
  const [suffix, setSuffix] = useState<string | null>(null);
  const value = useMemo(() => ({ override, setOverride, suffix, setSuffix }), [override, suffix]);
  return <TitleContext.Provider value={value}>{children}</TitleContext.Provider>;
}

export function usePageTitleOverride(): string | null {
  return useContext(TitleContext).override;
}

/** 이 화면이 열려 있는 동안 화면 제목을 `title`로 한다(언마운트하면 원래대로). */
export function usePageTitle(title: string | null): void {
  const { setOverride } = useContext(TitleContext);
  useEffect(() => {
    setOverride(title);
    return () => setOverride(null);
  }, [title, setOverride]);
}

/** 문서 제목 끝 보조 글. 호출한 컴포넌트가 마운트된 동안만 붙는다(언마운트하면 제거). */
export function usePageTitleSuffix(): string | null {
  return useContext(TitleContext).suffix;
}

/** 이 컴포넌트가 마운트된 동안 문서 제목 끝에 `suffix`를 붙인다. */
export function useSetTitleSuffix(suffix: string | null): void {
  const { setSuffix } = useContext(TitleContext);
  useEffect(() => {
    setSuffix(suffix);
    return () => setSuffix(null);
  }, [suffix, setSuffix]);
}

/** 문서 제목 문자열. 응답 대기가 있으면 `(n)`을 붙이고, 보조 글이 있으면 끝에 ` · 보조`를 붙인다(어느 화면에서든). */
export function composeDocumentTitle(args: { screen: string; app: string; pending: number; suffix?: string | null }): string {
  const base = `${args.pending > 0 ? `(${args.pending}) ` : ""}${args.screen} · ${args.app}`;
  return args.suffix ? `${base} · ${args.suffix}` : base;
}
