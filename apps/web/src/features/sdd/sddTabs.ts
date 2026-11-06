import type { ComponentType, MutableRefObject } from "react";
import type { SpecView } from "@agent-console/contracts/sdd";
import type { SddContext } from "./useSddContext";

/** 상세 탭 본문이 받는 값. 탭마다 같은 모양이라 새 탭은 컴포넌트 하나를 등록하면 된다(`SddTabPanels`). */
export interface SddTabProps {
  specId: string;
  /** 스펙 보기(정의·파싱 결과·풀린 라벨). 서버 값 그대로 */
  view: SpecView;
  /** 스펙 정의 버전(`ETag`). 저장·삭제의 `If-Match` */
  versionHash: string;
  ctx: SddContext;
  /** 주소 인자(탭 안 선택·거르기는 주소가 진실이다) */
  params: URLSearchParams;
  /** 주소 인자를 바꾼다(`replace` = 기록을 쌓지 않음) */
  setParams: (next: URLSearchParams, options?: { replace?: boolean }) => void;
  /** 다른 탭으로 가며 인자를 건다(예: 문서 탭 `doc`·`line`) */
  goTab: (tab: string, query?: Readonly<Record<string, string | null | undefined>>) => void;
  /** 자기가 방금 저장해 서버가 알리는 `sdd.changed`를 다시 읽지 않을 버전들 */
  ownHashes: MutableRefObject<Set<string>>;
  /** 스펙 보기를 다시 읽는다 */
  refresh: () => Promise<void>;
  /** 이 탭에 저장하지 않은 변경이 있는지 알린다(화면 이동·탭 닫기 확인). `key`는 탭마다 하나 */
  reportDirty: (key: string, dirty: boolean) => void;
}

/** 탭 id → 본문. 등록되지 않은 탭은 탭 줄에 나오지 않는다. 앱 조립 층이 더 등록할 수 있다. */
export type SddTabPanels = Readonly<Record<string, ComponentType<SddTabProps>>>;
