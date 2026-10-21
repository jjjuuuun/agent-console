# apps/web/src/links

두 기능 이상을 함께 쓰는 연결 층이다(`specs/agent-console/modularity-design.md` 3.5·3.7).

- `linkParts.ts`: 연동 부분 등록 데이터(부분 id, 필요한 모듈 id·역할, 숨김/비활성). 화면은 부분 id만 안다.
- 두 기능을 한 컴포넌트에서 쓰는 경우 `links/<a>-<b>/`에 둔다. 기능 폴더(`features/*`)는 이 폴더를 import하지 않고,
  앱 조립 층(`app/`, `shell/`)이 이 폴더를 가져다 쓴다.
- 부분이 켜졌는지 판정은 `modules/`의 `useLinkPart`·`LinkPart` 하나만 거친다.
