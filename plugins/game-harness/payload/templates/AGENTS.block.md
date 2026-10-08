## 게임 하네스

이 프로젝트는 공통 게임 하네스 {{version}}을 쓴다. 게임을 바꾸는 작업을 시작하기 전에 `.game-harness/harness/core/README.md`를 읽고 그 안내를 따른다.

파일을 고치거나 검증·조사를 시작하기 전, 그리고 "어디까지 했어?", "이어서 해줘" 같은 요청에 답하기 전에 `.game-harness/work/now/`의 파일을 모두 읽는다. 다른 세션이 잡고 있는 곳과 겹치면 진행하지 말고 사용자에게 묻는다. 파일을 고치기 전에 `.game-harness/harness/core/handoff.md`의 방식으로 그 폴더에 자신의 작업 파일을 만들고 `건드리는 곳`을 적는다. 이것을 어기면 파일 수정이 `[game-harness]` 메시지와 함께 거부된다. 거부되면 우회하지 말고 메시지대로 한다.

- `.game-harness/harness/core/README.md`: 공통 작업 절차와 규칙의 우선순위.
- `.game-harness/harness/core/handoff.md`: 작업 인계 기록과 세션 간 겹침 판단.
{{modules}}
- `.game-harness/project.yaml`: 이 게임의 설정(작업 대상, 검증 실행 방법, 요청 없이는 하지 않는 작업).
- `.game-harness/overrides/`: 이 게임만의 예외와 추가 검증. 공통 절차보다 우선한다.

전역 제작 스킬·에이전트를 사용할 때는 각 시작 절차의 `global_runtime.py prepare`를 실행한다. 명령이 프로젝트 루트를 찾아 `overrides/skills/<이름>/override.md` 또는 `overrides/agents/<이름>/override.md`를 읽고, 없으면 빈 템플릿만 만든다. 명시된 변경만 적용하며 나머지는 전역 기본 지침을 따른다. 에이전트 호출 시 프로젝트의 절대 경로를 전달한다. 전역 설치본은 수정·삭제하지 않는다.

`.game-harness/harness/` 안의 파일과 이 구역은 고치지 않는다. 업데이트할 때 덮어써진다.
