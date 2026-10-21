import type { EventAlias } from "./core";

/**
 * 전역 `interactions` 토픽은 `interaction.updated`(대기 상태)로 온다. 실행 토픽을 구독하지 않은 실행의
 * "요청됨" 이벤트도 알림 후보가 되도록, 대기 상태 메시지를 설정 이벤트 이름 하나의 별칭으로 본다.
 * 설정 `events`에 어떤 이름을 넣을지는 사용자 데이터이고, 이 표는 메시지 모양 -> 이름 변환 데이터다.
 */
export const DEFAULT_EVENT_ALIASES: readonly EventAlias[] = [{ type: "interaction.updated", when: { path: "interaction.status", equals: "pending" }, as: "interaction.requested" }];

/** 제안 목록에 남기는 수신 이벤트 이름 종류의 최대 개수 */
export const OBSERVED_NAMES_MAX = 50;
