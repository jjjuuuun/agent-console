/** 자동 경로(라우터) 결과를 캔버스의 연결선에 내려 주는 연결 고리. 값이 없으면(Provider 밖) 연결선은 모양의 `build`로 그려진다. */
import { createContext } from "react";
import type { RoutedEdge } from "../logic/route";
import type { SpreadInput } from "../logic/labelSpread";

export const EdgeRouteContext = createContext<ReadonlyMap<string, RoutedEdge> | null>(null);

/**
 * 라벨 겹침 풀기 연결 고리. 연결선이 자기 경로를 `report`로 알리면 편집기가 겹침을 풀어 `spread`(연결선 id → 경로 비율)로 돌려준다.
 * 연결선에 사용자 지정 위치가 없을 때만 `spread` 값을 쓴다. Provider 밖이면 기본 위치(0.5)다.
 */
export interface EdgeLabelSpread {
  spread: ReadonlyMap<string, number>;
  /** 연결선의 라벨 경로를 알린다. `null`이면 뺀다. 같은 내용을 되풀이해 알려도 된다(`key`가 같으면 무시). */
  report(id: string, input: SpreadInput | null, key: string): void;
}
export const EdgeLabelSpreadContext = createContext<EdgeLabelSpread | null>(null);
