/**
 * 편집 중 저장 전 시험(`preview`): 본문이 멈춘 뒤(600ms 디바운스, IME 조합 중에는 보류) 서버에 보내 링크 범위·이슈·쓰기 규칙 시험 결과를 받는다.
 * 쓰지 않고 기록·색인·알림을 건드리지 않는다. 앞 요청은 취소하고, 응답이 올 때 본문이 바뀌었으면 버린다(다음 시험이 온다).
 * 서버에 시험이 없으면(404 등) `available=false`로 두고 이후 요청하지 않는다 — 규칙 칩을 그리지 않고 저장 후 응답으로만 알린다.
 */
import { useEffect, useRef, useState } from "react";
import type { WikiPagePreview } from "@agent-console/contracts/wiki";
import { ApiError } from "@agent-console/api-client";
import { WIKI_LIMITS } from "./wikiConfig";
import { useWikiSpace } from "./useWikiApi";

export interface PreviewState {
  /** 시험이 쓸 수 있는가(한 번이라도 거절되면 false) */
  available: boolean;
  /** 마지막으로 받은 결과와 그것이 나온 본문(링크 범위는 이 본문 기준이다) */
  result: { content: string; preview: WikiPagePreview } | null;
  pending: boolean;
}

/** 전역 IME 조합 상태(편집기 안 조합을 안에서 알 수 없어 문서 수준 이벤트로 본다). */
function useComposing(): { readonly current: boolean } {
  const composing = useRef(false);
  useEffect(() => {
    const start = () => {
      composing.current = true;
    };
    const end = () => {
      composing.current = false;
    };
    document.addEventListener("compositionstart", start, true);
    document.addEventListener("compositionend", end, true);
    return () => {
      document.removeEventListener("compositionstart", start, true);
      document.removeEventListener("compositionend", end, true);
    };
  }, []);
  return composing;
}

export function usePagePreview(wikiId: string, path: string | null, content: string, enabled: boolean): PreviewState {
  const space = useWikiSpace();
  const composing = useComposing();
  const [state, setState] = useState<PreviewState>({ available: true, result: null, pending: false });
  const latest = useRef(content);
  useEffect(() => {
    latest.current = content;
  });
  useEffect(() => {
    if (!enabled || path === null || !state.available) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const run = () => {
      if (composing.current) {
        timer = setTimeout(run, WIKI_LIMITS.previewDebounceMs);
        return;
      }
      setState((s) => ({ ...s, pending: true }));
      space.client.previewWikiPage(wikiId, path, content, controller.signal).then(
        (preview) => {
          if (cancelled) return;
          // 응답이 올 때 본문이 이미 바뀌었으면 버린다(링크 범위가 어긋난다)
          setState((s) => (latest.current === content ? { ...s, pending: false, result: { content, preview } } : { ...s, pending: false }));
        },
        (e: unknown) => {
          if (cancelled) return;
          const gone = e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501);
          setState((s) => ({ ...s, pending: false, available: gone ? false : s.available }));
        },
      );
    };
    timer = setTimeout(run, WIKI_LIMITS.previewDebounceMs);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, wikiId, path, content, space, composing, state.available]);
  return state;
}
