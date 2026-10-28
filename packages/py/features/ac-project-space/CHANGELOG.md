# 변경 기록

## 0.1.0

- 5.7R.33w: 처음 만듦. `open_space`·`init_space`(매니페스트·`.gitignore` 틀을 없을 때만 만들고 있으면 채택,
  쓸 수 없으면 `config_writable=false`), `read_manifest`·`write_manifest`(If-Match, 모르는 키·주석 보존)·`reset_manifest`,
  비밀 저장 거부(`secret://` 참조만), 파일 시스템 주입(`SpaceFiles`).
