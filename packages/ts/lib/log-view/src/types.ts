import type { ReactNode } from "react";
import type { LogEvent } from "@agent-console/contracts/logs";

/** 이벤트 표의 행. 계약 `LogEvent`(`duration_ms`는 서버가 짝 이벤트에 채움). */
export type LogEventRow = LogEvent;

/** 색 슬롯 계산(0~7). 앱이 기존 노드 카테고리 해시를 주입한다(패키지에 해시를 복사하지 않는다). */
export type SlotFor = (key: string) => number;

/** 열 정의. `render`가 없으면 열 id에 맞는 기본 셀(필드 이름 기준)을 그린다. */
export interface ColumnSpec<Row> {
  id: string;
  header: ReactNode;
  /** px 숫자 또는 CSS 길이/`fr`. */
  width: number | string;
  align?: "start" | "end";
  render?: (row: Row) => ReactNode;
}

/** 분류 체계의 화면용 항목. 계약 `LogTaxonomy`를 `toTaxonomyView`로 바꾼 것. */
export interface TaxonomyEntry {
  id: string;
  name: string;
  color?: string;
  visible: boolean;
  tone?: string;
  description?: string;
}

export interface LogTaxonomyView {
  /** 분류 체계 순서(필터 칩 순서). */
  order: readonly string[];
  /** 항목 조회. 분류 체계에 없는 id도 이름 = id인 항목을 돌려준다. */
  get(id: string): TaxonomyEntry;
  has(id: string): boolean;
}

/** 시각 표기 주입(앱이 기존 포맷터를 쓰고 싶을 때). 모두 선택. */
export interface Formatters {
  /** 상대 시각: ms 간격 -> "+1:23.456". */
  relativeTime(ms: number): string;
  /** 절대 시각: epoch 초 -> 로컬 "HH:mm:ss.SSS". */
  absoluteTime(epochSeconds: number): string;
  /** 소요 시간(ms) -> "842ms" "12.3초" "2분 05초". */
  duration(ms: number): string;
  /** 토큰 약식 -> "4.1k". */
  tokens(n: number): string;
  /** 숫자 천 단위. */
  number(n: number): string;
}

/** 재생 시계(주입). 테스트에서 가짜 시간으로 돌린다. */
export interface PlaybackClock {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

/** 필터 값: 이름 -> 값 하나 또는 여러 개(반복 키). */
export type LogFilterValue = Record<string, string | string[]>;

export type FilterInput = "text" | "select" | "multiselect" | "time-range";

/** 필터 필드 정의(앱 데이터 한 곳). 필터 이름·입력 방식은 이 목록만 본다. */
export interface FilterFieldSpec {
  name: string;
  label: string;
  input: FilterInput;
  placeholder?: string;
  /** 항상 보이는 검색 입력으로 쓰는 필드인지(기본: 첫 text가 아니라 `searchField` prop으로 지정). */
  options?: readonly { value: string; label?: string }[];
}

/** 즐겨찾는 필터 한 건. */
export interface SavedFilter {
  name: string;
  value: LogFilterValue;
  /** 화면 전용 상태(오류만·레인 등)를 함께 저장하고 싶을 때. */
  extra?: Record<string, unknown>;
}

/** 즐겨찾는 필터 저장소(주입). 기본 구현은 `createLocalStorageSavedFilters`. */
export interface SavedFilterStore {
  list(): SavedFilter[];
  save(filter: SavedFilter): void;
  remove(name: string): void;
}

/** 목록 공통 슬롯. */
export interface ListSlots {
  loading?: boolean | undefined;
  error?: { message: string; detail?: string } | null;
  onRetry?: () => void;
  renderLoading?: () => ReactNode;
  renderEmpty?: () => ReactNode;
  renderError?: (error: { message: string; detail?: string }, retry?: () => void) => ReactNode;
}
