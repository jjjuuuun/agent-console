import type { ComponentType, MutableRefObject } from "react";
import type { WikiDisplay } from "@agent-console/wiki-view";
import type { WikiSummary, WikiView } from "@agent-console/contracts/wiki";
import type { OwnWrites } from "./useWikiApi";
import type { WikiContext } from "./useWikiContext";

/** 새 페이지 대화상자를 열 때 미리 채울 값(끊긴 링크·메모리에서 올 때). 전부 선택이다. */
export interface NewPagePrefill {
  path?: string;
  title?: string;
  content?: string;
}

/** 위키 화면 탭 본문이 받는 값. 탭마다 같은 모양이라 새 탭은 컴포넌트 하나를 등록하면 된다(`WikiTabPanels`). */
export interface WikiTabProps {
  wikiId: string;
  /** 위키 정의 + 합친 규칙 요약 + 이슈. 서버 값 그대로 */
  view: WikiView;
  /** 위키 정의 버전(`ETag`). 저장·삭제의 `If-Match` */
  versionHash: string;
  /** 목록 카드와 같은 요약(페이지 수·끊긴 링크·최근 변경). 아직 모르면 undefined */
  summary: WikiSummary | undefined;
  ctx: WikiContext;
  display: WikiDisplay;
  /** 주소 인자(탭 안 선택·거르기는 주소가 진실이다) */
  params: URLSearchParams;
  /** 주소 인자를 바꾼다(`replace` = 기록을 쌓지 않음) */
  setParams: (next: URLSearchParams, options?: { replace?: boolean }) => void;
  /** 다른 탭으로 가며 인자를 건다(예: 페이지 탭 `path`·`line`) */
  goTab: (tab: string, query?: Readonly<Record<string, string | null | undefined>>) => void;
  /** 자기가 방금 쓴 페이지(`wiki.changed`를 다시 읽지 않을 것들) */
  ownWrites: MutableRefObject<OwnWrites>;
  /** 위키 질의를 다시 읽는다 */
  refresh: () => Promise<void>;
  /** 이 탭에 저장하지 않은 변경이 있는지 알린다(화면 이동·탭 닫기 확인). `key`는 탭마다 하나 */
  reportDirty: (key: string, dirty: boolean) => void;
  /** 새 페이지 대화상자 열기(머리 [새 페이지…]와 같은 것) */
  openNewPage: (prefill?: NewPagePrefill) => void;
  /** 이 위키에 규칙 탭이 등록돼 있는가(규칙 열기 버튼의 조건) */
  hasTab: (tab: string) => boolean;
}

/** 탭 id → 본문. 등록되지 않은 탭은 탭 줄에 나오지 않는다. 앱 조립 층이 더 등록할 수 있다. */
export type WikiTabPanels = Readonly<Record<string, ComponentType<WikiTabProps>>>;
