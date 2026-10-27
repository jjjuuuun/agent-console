# 변경 기록

## 0.1.0

- 처음 만듦(5.7R.9, design §5.7R.2): 저장소 프로토콜 `MemoryStore`(X31)·`InMemoryMemoryStore`(버전·`if_version` 충돌·동시 쓰기 순서·표시 삭제·완전 삭제·되돌리기·보관·옮기기·검색), 쓰기 정책(키 규칙·한도·비밀 검사 주입 `reject`·`redact`), 범위 종류(X29: 패키지 기본 데이터 `data/default_scope_kinds.yaml`, 병합·출처·끄기, id 틀 해석, entry point 로더), 접근 판단 `allowed`, 도구 묶음 `MemoryToolkit`(도구 4개, 사유 코드, 본문·검색어 없는 이벤트 payload), `testing`(가짜 시계·표본·저장소 계약 묶음).
