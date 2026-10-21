import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

/** 빠른 이동의 "동작" 그룹 항목. 화면이 등록하는 데이터이며 팔레트는 이름을 모른다. */
export interface CommandDef {
  id: string;
  /** `messages`의 점 표기 키 */
  titleKey: string;
  run: () => void;
  /** 표시용 단축키(선택) */
  shortcut?: string;
}

interface Registry {
  commands: readonly CommandDef[];
  register(owner: string, defs: readonly CommandDef[]): () => void;
}

const CommandsContext = createContext<Registry>({ commands: [], register: () => () => {} });

export function CommandsProvider({ children }: { children: ReactNode }) {
  const [byOwner, setByOwner] = useState<ReadonlyMap<string, readonly CommandDef[]>>(new Map());
  const register = useCallback((owner: string, defs: readonly CommandDef[]) => {
    setByOwner((cur) => new Map(cur).set(owner, defs));
    return () =>
      setByOwner((cur) => {
        const next = new Map(cur);
        next.delete(owner);
        return next;
      });
  }, []);
  const value = useMemo<Registry>(() => {
    const merged = new Map<string, CommandDef>();
    for (const defs of byOwner.values()) for (const d of defs) merged.set(d.id, d);
    return { commands: [...merged.values()], register };
  }, [byOwner, register]);
  return <CommandsContext.Provider value={value}>{children}</CommandsContext.Provider>;
}

/** 등록된 모든 명령(빠른 이동의 "동작" 그룹 원천). */
export function useCommands(): readonly CommandDef[] {
  return useContext(CommandsContext).commands;
}

/** 화면이 자기 명령을 등록(마운트)·해제(언마운트)한다. 핸들러는 항상 최신 함수가 불린다. */
export function useRegisterCommands(defs: readonly CommandDef[]): void {
  const { register } = useContext(CommandsContext);
  const owner = useId();
  const ref = useRef(defs);
  useEffect(() => {
    ref.current = defs;
  });
  const signature = JSON.stringify(defs.map((d) => [d.id, d.titleKey, d.shortcut ?? null]));
  useEffect(() => {
    const wrapped = (JSON.parse(signature) as [string, string, string | null][]).map(([id, titleKey, shortcut]): CommandDef => ({
      id,
      titleKey,
      ...(shortcut === null ? {} : { shortcut }),
      run: () => ref.current.find((d) => d.id === id)?.run(),
    }));
    return register(owner, wrapped);
  }, [signature, register, owner]);
}
