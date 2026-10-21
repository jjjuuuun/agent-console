"""팀 구성 데이터를 읽는 약속(config 키·정의 종류·층 이름).

엔진과 마찬가지로 이 패키지는 노드 타입·연결 종류 이름을 모른다. 노드가 어떤 정의에서 왔는지는
노드 타입 디스크립터 `binds{kind, field}`로, 연결의 의미는 엣지 디스크립터
(`scheduling`·`invocation`·`interaction`)로 판단한다. 남는 것은 노드·엣지 config 안의 키 이름뿐이며,
그 기본값(아래)은 기본 플러그인(`ac-nodes-core`) config 스키마와 맞춘 **데이터**다. 다른 플러그인이
다른 키를 쓰면 `TeamConventions(...)`를 만들어 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEFAULT_CONVENTIONS", "LayerName", "TeamConventions"]


@dataclass(frozen=True, slots=True)
class LayerName:
    """설정 층 하나의 id(출처 표시 키)와 화면 이름."""

    id: str
    label: str


@dataclass(frozen=True, slots=True)
class TeamConventions:
    """팀 구성 데이터에서 읽는 키 이름 묶음.

    Attributes:
        agent_kind: 에이전트 노드를 알아보는 `NodeTypeDescriptor.binds.kind`(정의 종류 이름).
            에이전트 정의 id는 `binds.field` config 키에서 읽는다.
        resource_kind: 리소스 노드를 알아보는 `binds.kind`. 리소스 id는 `binds.field`에서 읽는다.
        team_kind: 중첩 팀 노드를 알아보는 `binds.kind`(팀 구성 정의 종류 이름, design §5R.7).
            자식 팀 구성 id는 `binds.field`에서 읽는다.
        backend_capability: 노드 타입 디스크립터 `capabilities`에 이 문자열이 있으면 그 노드는 실행
            백엔드를 쓴다(에이전트 정의에 묶인 실행 가능 노드는 선언 없이도 쓴다, 사전 점검
            `resolve_backends`).
        node_version_key: 중첩 팀 노드가 자식 팀 구성 버전을 고정하는 노드 config 키(생략 = 최신).
        node_settings_key: 노드 층 설정(`AgentSettings` 모양)이 든 노드 config 키.
        node_role_key / node_delegate_when_key: 이 팀 안의 역할 이름 / 언제 맡길지(노드 config).
        node_delegation_key: 위임자 노드의 위임 방식별 config(`{방식 id: config}`, 노드 config).
        edge_kinds_key: 상호작용 연결에서 허용 종류를 좁히는 엣지 config 키(목록).
        edge_timeout_key / edge_on_timeout_key: 상호작용 연결의 대기 한도·초과 시 동작(엣지 config).
        edge_strategy_key: 위임 연결의 위임 방식 덮어쓰기(엣지 config).
        edge_mode_key / edge_override_key: 리소스 연결의 첨부 방식·config 덮어쓰기(엣지 config).
        review_decisions_pointer: 검토 결정 목록(`[{id, ...}]`, id = 출력 포트)의 노드 config 위치.
        common_layer / team_layer / agent_layer / node_layer: 설정 4층의 id·화면 이름.
        defaults_layer: 사용자 설정 묶음(채팅·위임 등)의 코드 기본값 층.
    """

    agent_kind: str = "agent"
    resource_kind: str = "resource"
    team_kind: str = "graph"
    backend_capability: str = "backend"
    node_version_key: str = "version"
    node_settings_key: str = "settings"
    node_role_key: str = "role"
    node_delegate_when_key: str = "delegate_when"
    node_delegation_key: str = "delegation"
    edge_kinds_key: str = "kinds"
    edge_timeout_key: str = "timeout_seconds"
    edge_on_timeout_key: str = "on_timeout"
    edge_strategy_key: str = "strategy"
    edge_mode_key: str = "mode"
    edge_override_key: str = "config_override"
    review_decisions_pointer: str = "/review/decisions"
    common_layer: LayerName = LayerName("common", "공통")
    team_layer: LayerName = LayerName("team", "팀 구성")
    agent_layer: LayerName = LayerName("agent", "에이전트")
    node_layer: LayerName = LayerName("node", "이 팀의 노드")
    defaults_layer: LayerName = LayerName("defaults", "기본값")


DEFAULT_CONVENTIONS = TeamConventions()
"""기본 플러그인(`ac-nodes-core`) config 스키마와 맞춘 약속."""
