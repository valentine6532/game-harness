# game-harness

여러 게임 프로젝트에서 같은 제작 절차를 쓰기 위한 공통 하네스다. Claude Code와 Codex용 플러그인 하나로 배포하며, 플러그인은 하네스를 게임 폴더에 복사해 설치하고 버전을 관리한다.

게임 작업은 플러그인이 아니라 게임 폴더에 복사된 하네스를 보고 진행한다. 그래서 플러그인이 새 버전이 되어도, 업데이트를 요청하지 않은 게임은 기존 버전 그대로 동작한다.

## 필요한 것

- Python 3.9 이상 (`python` 명령으로 실행되어야 한다)
- git (게임 프로젝트가 git 저장소여야 업데이트를 되돌릴 수 있다)

## 설치

Claude Code:

```
claude plugin marketplace add valentine6532/game-harness
claude plugin install game-harness@game-harness
```

Codex용 설정(`plugins/game-harness/plugin.json`, `.agents/plugins/marketplace.json`)도 들어 있지만 실제 설치는 아직 시험하지 않았다.

## 사용

게임 프로젝트 폴더에서 요청한다.

| 요청 | 스킬 | 하는 일 |
| --- | --- | --- |
| 이 프로젝트에 게임 하네스 적용해줘 | `harness-apply` | 프로젝트를 조사해 기능을 고르고, 하네스를 복사하고, 입구 파일과 설정을 만든다 |
| 하네스 상태 확인해줘 | `harness-status` | 적용 버전, 고른 기능, 누락되거나 손으로 고쳐진 파일, 새 버전 여부를 보고한다 |
| 이 프로젝트 하네스 업데이트해줘 | `harness-update` | 차이를 보여주고, 확인을 받은 뒤 하네스를 새 버전으로 바꾼다 |
| 이전 하네스 버전으로 복구해줘 | `harness-rollback` | 게임 프로젝트의 git에서 업데이트를 되돌린다 |
| 이 문제를 공통 하네스에도 반영해줘 | `harness-promote` | 원본 저장소를 고쳐 새 버전을 준비하거나, 권한이 없으면 개선 제안을 작성한다 |

Claude Code에서는 `/game-harness:harness-apply`처럼 직접 부를 수도 있다.

## 게임 폴더에 생기는 것

```text
내게임/
├─ AGENTS.md                 Codex 입구. 기존 내용은 두고 하네스 안내 구역만 덧붙인다
├─ CLAUDE.md                 Claude 입구. 없을 때만 만든다 (@AGENTS.md)
└─ .game-harness/
   ├─ harness/               복사된 하네스. 고치지 않는다
   │  ├─ CHANGELOG.md
   │  ├─ core/               모든 게임 공통 절차
   │  └─ modules/unity/      고른 기능만
   ├─ manifest.json          복사한 버전, 고른 기능, 파일별 해시
   ├─ project.yaml           이 게임의 설정
   └─ overrides/             이 게임만의 예외와 추가 검증
```

| 위치 | 주인 | 업데이트할 때 |
| --- | --- | --- |
| `harness/`, `manifest.json`, `AGENTS.md`의 하네스 구역 | 하네스 | 통째로 바뀐다 |
| `project.yaml`, `overrides/`, `AGENTS.md`의 나머지, `CLAUDE.md` | 게임 | 바뀌지 않는다 |

게임마다 다른 점은 `project.yaml`과 `overrides/`에 적는다. `harness/` 안을 직접 고치면 다음 업데이트 때 덮어써진다.

## 들어 있는 내용

| 위치 | 내용 |
| --- | --- |
| `core/workflow.md` | 계획·실행·검증·보고 순서, 원본과 생성 파일 구분, 요청 없이는 하지 않는 작업 |
| `core/verification.md` | 필요한 범위만 검증, 요약부터 읽기, 자동 검사와 눈으로 본 검토를 따로 보고 |
| `core/cleanup.md` | 시험 뒤 임시 파일 정리 |
| `modules/unity/` | 공식 스킬 우선, 플레이 중 에디터 작업 대기, 창 없는 백그라운드 실행, 시간 초과 뒤 재시도 전 확인 |

선택 기능은 현재 `unity` 하나다. 기획·아트·배포 절차와 다른 엔진 기능은 아직 없다.

## 업데이트가 전달되는 순서

1. 원본 저장소에 새 버전이 올라간다.
2. 각 PC에서 플러그인을 갱신하면 새 버전이 그 PC에 들어온다.

   ```
   claude plugin marketplace update game-harness
   claude plugin update game-harness@game-harness
   ```

3. 게임 폴더에서 "하네스 업데이트해줘"를 요청하면 그 게임에 적용된다.

2번을 잊어도 된다. 게임 폴더에서 "하네스 상태 확인해줘"나 "업데이트해줘"를 하면 GitHub에 올라온 최신 버전을 확인해서, 설치된 플러그인이 예전 버전이면 먼저 갱신하라고 알려준다.

3번에서는 바꾸기 전에 다음을 보여주고 진행할지 묻는다.

- 현재 버전과 새 버전
- 두 버전 사이의 변경 내용
- 추가·삭제·변경되는 파일
- 손으로 고쳐져서 덮어써질 파일
- 경고 (git 저장소가 아님, 커밋되지 않은 변경이 있음 등)

## 관리 도구

스킬은 `plugins/game-harness/scripts/harness.py`를 실행한다. 직접 실행할 수도 있다.

```
python harness.py status --project <게임 폴더>
python harness.py diff   --project <게임 폴더> [--modules unity]
python harness.py apply  --project <게임 폴더> [--modules unity]
python harness.py update --project <게임 폴더> [--modules unity] --yes
python harness.py check
python harness.py source
```

`update`는 `--yes`가 없으면 차이만 출력하고 아무것도 바꾸지 않는다. `apply`는 이미 적용된 프로젝트에서는 아무것도 바꾸지 않는다.

## 저장소 구조

```text
game-harness/
├─ .claude-plugin/marketplace.json    Claude Code용 배포 목록
├─ .agents/plugins/marketplace.json   Codex용 배포 목록
├─ plugins/game-harness/
│  ├─ .claude-plugin/plugin.json      Claude Code용 설정
│  ├─ plugin.json                     Codex용 설정 (버전의 기준)
│  ├─ skills/                         관리 스킬 5개
│  ├─ scripts/harness.py              관리 도구
│  └─ payload/                        게임 폴더로 복사될 내용
│     ├─ CHANGELOG.md
│     ├─ core/
│     ├─ modules/
│     └─ templates/
└─ tests/test_harness.py
```

## 하네스 고치기

게임 폴더의 `harness/`나 설치된 플러그인 사본이 아니라 이 저장소의 `payload/`를 고친다.

1. `plugins/game-harness/payload/`를 고친다. 모든 게임에 해당하면 `core/`, 특정 엔진에만 해당하면 `modules/<이름>/`이다.
2. 버전을 세 곳에서 함께 올린다: `plugin.json`, `.claude-plugin/plugin.json`, `payload/CHANGELOG.md` 맨 위의 `## <버전> - <날짜>` 항목.
3. 시험한다.

   ```
   python plugins/game-harness/scripts/harness.py check
   python -m unittest discover -s tests
   ```

4. 커밋한다. 수정이 여러 번이면 커밋만 쌓아 둔다.
5. GitHub에 올릴 때 `v<버전>` 태그를 붙여 함께 올린다.

저장소 폴더를 로컬 배포 목록으로 등록해 두면(`claude plugin marketplace add <폴더 경로>`) Claude Code가 이 폴더를 직접 읽으므로 고친 내용이 바로 반영된다. 이때 `harness.py`는 플러그인 폴더에 커밋되지 않은 변경이 있거나, 현재 버전의 태그를 붙인 뒤 플러그인 내용이 바뀌었으면 경고한다.

## 아직 확인하지 않은 것

- Codex에서의 설치와, 스킬이 `harness.py`를 찾는 방식
- GitHub 저장소를 통한 Claude Code 설치
- Windows 외의 환경
- 내용물이 Unity 퍼즐 게임 하나의 경험에서 나왔으므로, 다른 종류의 게임에서도 맞는지
