## 게임 하네스

이 프로젝트는 공통 게임 하네스 {{version}}을 쓴다. 게임을 바꾸는 작업을 시작하기 전에 `.game-harness/harness/core/README.md`를 읽고 그 안내를 따른다.

- `.game-harness/harness/core/README.md`: 공통 작업 절차와 규칙의 우선순위.
{{modules}}
- `.game-harness/project.yaml`: 이 게임의 설정(작업 대상, 검증 실행 방법, 요청 없이는 하지 않는 작업).
- `.game-harness/overrides/`: 이 게임만의 예외와 추가 검증. 공통 절차보다 우선한다.

`.game-harness/harness/` 안의 파일과 이 구역은 고치지 않는다. 업데이트할 때 덮어써진다.
