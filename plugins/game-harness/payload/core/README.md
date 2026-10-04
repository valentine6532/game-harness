# 게임 하네스 공통 절차

이 폴더는 공통 하네스에서 복사한 것이다. 여기 있는 파일은 고치지 않는다. 이 게임에만 필요한 규칙은 `.game-harness/overrides/`에 적는다.

## 언제 무엇을 읽는가

| 상황 | 읽을 파일 |
| --- | --- |
| 작업을 시작하기 전, 멈출 때, 끝났을 때, 진행 상황을 물었을 때 | `handoff.md` |
| 게임을 바꾸는 작업을 시작할 때 | `workflow.md` |
| 바꾼 것을 확인하거나 결과를 보고할 때 | `verification.md` |
| 시험과 검토가 끝났을 때 | `cleanup.md` |

## 규칙이 겹칠 때의 순서

1. 사용자가 이번 대화에서 직접 말한 것
2. `.game-harness/overrides/`와 프로젝트 `AGENTS.md`의 게임 규칙
3. `.game-harness/project.yaml`의 설정
4. `.game-harness/harness/modules/`의 기능별 지침
5. 이 폴더의 공통 절차

위에 있는 것이 아래 것보다 우선한다.
