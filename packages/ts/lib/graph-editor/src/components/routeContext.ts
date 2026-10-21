/** 자동 경로(라우터) 결과를 캔버스의 연결선에 내려 주는 연결 고리. 값이 없으면(Provider 밖) 연결선은 모양의 `build`로 그려진다. */
import { createContext } from "react";
import type { RoutedEdge } from "../logic/route";

export const EdgeRouteContext = createContext<ReadonlyMap<string, RoutedEdge> | null>(null);
