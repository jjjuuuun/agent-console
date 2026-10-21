import { useCallback, useLayoutEffect, useRef, useState, type RefCallback, type RefObject } from "react";
import { computeVisible } from "./fit";

export interface UseOverflowFitOptions {
  /** 항목 키(원래 순서). */
  keys: readonly string[];
  /** 반드시 보여야 하는 키. */
  priorityKeys?: readonly string[];
  /** 항목 사이 간격(px). */
  gap?: number;
  /** 측정 전 "더 보기" 버튼 폭 추정(px). */
  fallbackMoreWidth?: number;
}

export interface UseOverflowFit {
  /** 줄 전체(항목 트랙 + 더 보기 버튼)를 감싼 요소에 건다. */
  rootRef: RefObject<HTMLDivElement | null>;
  /** 더 보기 버튼 래퍼에 건다(폭 측정). */
  moreRef: RefObject<HTMLElement | null>;
  /** 항목 요소 ref. 숨긴 항목도 DOM에 남겨(보이지 않게) 폭을 계속 잰다. */
  itemRef: (key: string) => RefCallback<HTMLElement>;
  /** 숨겨진 키. */
  hidden: ReadonlySet<string>;
}

/** `ResizeObserver`로 줄 폭을 보고 넘치는 항목을 숨긴다. Tabs·ChipRow가 같이 쓴다. */
export function useOverflowFit({ keys, priorityKeys = [], gap = 0, fallbackMoreWidth = 72 }: UseOverflowFitOptions): UseOverflowFit {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const moreRef = useRef<HTMLElement | null>(null);
  const items = useRef(new Map<string, HTMLElement>());
  const moreWidth = useRef(fallbackMoreWidth);
  const [hiddenKey, setHiddenKey] = useState("");
  const inputs = useRef({ keys, priorityKeys, gap });
  useLayoutEffect(() => {
    inputs.current = { keys, priorityKeys, gap };
  });

  const measure = useCallback(() => {
    const root = rootRef.current;
    if (root === null) return;
    const { keys: ks, priorityKeys: pk, gap: g } = inputs.current;
    const mw = moreRef.current?.offsetWidth;
    if (mw !== undefined && mw > 0) moreWidth.current = mw;
    const widths = ks.map((k) => items.current.get(k)?.offsetWidth ?? 0);
    const priority = pk.map((k) => ks.indexOf(k)).filter((i) => i >= 0);
    const visible = computeVisible(widths, g, root.clientWidth, moreWidth.current, priority);
    const next = ks.filter((_, i) => !visible.has(i)).join("\u0000");
    setHiddenKey((prev) => (prev === next ? prev : next));
  }, []);

  useLayoutEffect(() => {
    measure();
  });

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (root === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(root);
    return () => observer.disconnect();
  }, [measure]);

  const refs = useRef(new Map<string, RefCallback<HTMLElement>>());
  const itemRef = useCallback((key: string): RefCallback<HTMLElement> => {
    let cb = refs.current.get(key);
    if (cb === undefined) {
      cb = (el) => {
        if (el === null) items.current.delete(key);
        else items.current.set(key, el);
      };
      refs.current.set(key, cb);
    }
    return cb;
  }, []);

  const hidden: ReadonlySet<string> = hiddenKey === "" ? new Set() : new Set(hiddenKey.split("\u0000"));
  return { rootRef, moreRef, itemRef, hidden };
}
