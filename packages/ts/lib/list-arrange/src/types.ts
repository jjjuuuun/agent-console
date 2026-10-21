/** 묶는 기준 하나. 화면이 데이터로 주입한다(필드명·메시지 분기는 이 패키지에 없다). */
export interface GroupByDef<T> {
  /** 저장·선택에 쓰는 안정 id. */
  id: string;
  /** 메뉴 문구를 찾는 메시지 키(문구 자체는 호출자가 가진다). */
  titleKey: string;
  /** 항목의 값들. 빈 배열이면 "없음" 묶음. */
  read: (item: T) => readonly string[];
  /** true면 값마다 한 번씩(여러 묶음에) 보인다. 아니면 첫 값만 쓴다. */
  multi?: boolean;
  /** true면 값을 `/`로 나눠 계층으로 만든다. */
  tree?: boolean;
  /** 이 기준으로 묶을 수 있는지. 없으면 항상 가능. */
  usable?: (items: readonly T[]) => Usable;
}

export interface Usable {
  ok: boolean;
  /** `ok:false`일 때 사유(문구 키 또는 문장; 호출자가 해석). */
  reason?: string;
}

/** 정렬 기준 하나. */
export interface SortDef<T> {
  id: string;
  titleKey: string;
  compare: (a: T, b: T) => number;
  /** 이 정렬을 쓸 수 있는지(예: 수정 시각 필드가 있을 때만). 없으면 항상 가능. */
  available?: (items: readonly T[]) => boolean;
}

/** `groupItems`가 돌려주는 묶음 하나(트리면 깊이 우선 순서의 평평한 목록). */
export interface GroupNode<T> {
  /** 전체 경로(`/` 연결). 같은 기준 안에서 유일. "없음" 묶음은 `NONE_KEY`. */
  key: string;
  /** 머리에 보일 이름(마지막 조각; 너무 깊으면 남은 조각을 `/`로 이어 붙임). */
  name: string;
  depth: number;
  parentKey: string | undefined;
  /** 이 묶음에 직접 속한 항목(하위 묶음 항목은 제외). */
  items: T[];
  count: number;
  none: boolean;
}

export interface GroupOptions<T> {
  /** 묶음 이름 정렬 로케일. 기본 `ko`. */
  locale?: string;
  /** 묶음 안 항목 정렬. 없으면 입력 순서. */
  compare?: (a: T, b: T) => number;
  /** 트리 깊이 상한(이 깊이부터는 남은 조각을 한 이름으로 합침). 기본 3. */
  maxDepth?: number;
}
