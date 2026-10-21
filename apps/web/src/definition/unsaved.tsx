import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useBlocker } from "react-router";
import { Button, Dialog } from "@agent-console/ui";
import { messages as m } from "../app/messages";

interface UnsavedRegistry {
  /** 저장하지 않은 변경이 있는 화면 수 */
  count: number;
  report: (owner: symbol, dirty: boolean) => void;
}

const UnsavedContext = createContext<UnsavedRegistry>({ count: 0, report: () => {} });

/** 저장하지 않은 변경이 있는 화면을 모은다(앱 새 버전 적용 전 확인 등에 쓴다). */
export function UnsavedProvider({ children }: { children: ReactNode }) {
  const [owners, setOwners] = useState<ReadonlySet<symbol>>(new Set());
  const report = useCallback((owner: symbol, dirty: boolean) => {
    setOwners((cur) => {
      if (cur.has(owner) === dirty) return cur;
      const next = new Set(cur);
      if (dirty) next.add(owner);
      else next.delete(owner);
      return next;
    });
  }, []);
  const value = useMemo(() => ({ count: owners.size, report }), [owners, report]);
  return <UnsavedContext.Provider value={value}>{children}</UnsavedContext.Provider>;
}

/** 저장하지 않은 변경이 있는 화면이 하나라도 있는가. */
export function useHasUnsaved(): boolean {
  return useContext(UnsavedContext).count > 0;
}

/**
 * 저장하지 않은 변경이 있으면 라우트 이동·탭 닫기를 확인한다(데이터 라우터 필요).
 * 렌더 결과는 이탈 확인 다이얼로그이며, 화면 어디에든 한 번 둔다.
 */
export function UnsavedGuard({ dirty }: { dirty: boolean }) {
  const { report } = useContext(UnsavedContext);
  const owner = useRef(Symbol("unsaved"));
  useEffect(() => {
    const id = owner.current;
    report(id, dirty);
    return () => report(id, false);
  }, [dirty, report]);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const blocker = useBlocker(dirty);
  return (
    <Dialog
      open={blocker.state === "blocked"}
      title={m.definition.unsaved.title}
      onClose={() => blocker.state === "blocked" && blocker.reset()}
      actions={
        <>
          <Button onClick={() => blocker.state === "blocked" && blocker.reset()}>{m.definition.unsaved.stay}</Button>
          <Button variant="danger" onClick={() => blocker.state === "blocked" && blocker.proceed()}>
            {m.definition.unsaved.leave}
          </Button>
        </>
      }
    >
      <p className="ac-text">{m.definition.unsaved.body}</p>
    </Dialog>
  );
}
