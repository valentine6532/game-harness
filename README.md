# game-harness

여러 게임 프로젝트에서 같은 제작 절차를 쓰기 위한 공통 하네스다. `game-harness` 플러그인 하나가 프로젝트 하네스와 전역 제작 스킬 8개·검수 에이전트 1개를 관리한다. Claude Code와 Codex를 지원한다.

게임 폴더에 복사된 하네스 절차는 프로젝트별 업데이트를 요청할 때 갱신된다. 전역 제작 스킬·에이전트는 플러그인 버전을 따르며, 플러그인을 업데이트한 뒤 다음 세션 시작 때 함께 갱신된다. 각 게임의 로컬 오버라이드는 그대로 보존된다.

`game-skills`는 0.2.0부터 하네스에 통합됐다. 별도로 설치하지 않는다. Unity·Firebase·Unreal 공식 스킬 등 기존 외부 스킬은 이 플러그인의 관리 대상이 아니다.

## 필요한 것

- Python 3.10 이상과 Node.js. 훅은 Node 런처가 실제 Python을 찾아 실행한다. Windows Store 별칭은 건너뛰며, 필요하면 `GAME_HARNESS_PYTHON`에 Python 실행 파일 경로를 지정한다. 관리 명령 예제의 `python`도 실제 실행 파일로 바꿔 쓸 수 있다.
- git (게임 프로젝트가 git 저장소여야 업데이트를 되돌릴 수 있다)

## 설치

Claude Code:

```
claude plugin marketplace add valentine6532/game-harness
claude plugin install game-harness@game-harness
```

Codex용 설정(`plugins/game-harness/plugin.json`, `.agents/plugins/marketplace.json`)도 들어 있다. 플러그인 훅을 사용할 수 있고 신뢰된 환경에서 다음 세션의 `SessionStart`가 전역 동기화를 실행한다. 실제 Codex 설치·훅 로딩은 아직 실세션에서 검증하지 않았다.

전역 설치를 먼저 준비하거나 훅을 사용할 수 없으면 원본 저장소 또는 설치된 플러그인에서 한 번 실행한다.

```text
python plugins/game-harness/scripts/harness.py global-sync
```

새 스킬·에이전트 등록이 현재 세션의 목록에 보이지 않으면 세션을 다시 열거나 도구의 새로고침을 사용한다. 기존 `game-skills` 플러그인을 설치했다면 중복 실행을 피하도록 해당 플러그인만 제거하고 `game-harness`를 사용한다. 같은 이름의 비관리 전역 파일이 이미 있으면 동기화가 중단되고 충돌 경로가 표시된다. 기존 파일을 임의로 덮어쓰거나 삭제하지 않는다.

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
   ├─ overrides/             이 게임만의 예외와 추가 검증
   └─ work/                  작업 인계 기록
      ├─ now/                아직 끝나지 않은 작업. 작업 하나에 파일 하나
      └─ done/<연-월>/<일>/  끝난 작업의 보관함
```

| 위치 | 주인 | 업데이트할 때 |
| --- | --- | --- |
| `harness/`, `manifest.json`, `AGENTS.md`의 하네스 구역 | 하네스 | 통째로 바뀐다 |
| `project.yaml`, `overrides/`, `work/`, `AGENTS.md`의 나머지, `CLAUDE.md` | 게임 | 바뀌지 않는다 |

게임마다 다른 점은 `project.yaml`과 `overrides/`에 적는다. `harness/` 안을 직접 고치면 다음 업데이트 때 덮어써진다.

## 여러 세션에서 동시에 작업하기

세션들은 서로의 대화를 보지 못한다. 대신 각 세션이 작업을 시작할 때 `.game-harness/work/now/`에 파일 하나를 만들어 무엇을 하는지, 어디를 건드리는지 적는다. 다른 세션은 작업 전에 이 폴더를 모두 읽고, 자신이 하려는 일과 겹치면 진행하지 않고 사용자에게 묻는다.

이 규칙은 훅으로 강제된다. 플러그인이 설치된 환경에서 파일을 고치려 하면 훅(`scripts/work_guard.py`)이 먼저 확인하고, 아래 경우에는 수정을 거부하며 해야 할 일을 알려준다.

| 거부되는 경우 | 해야 할 일 |
| --- | --- |
| 자신의 작업 파일 없이 프로젝트 파일을 고친다 | `now/`를 읽고 자신의 작업 파일을 만든다 |
| 다른 작업의 `건드리는 곳`에 속한 파일을 고친다 | 사용자에게 묻는다 |
| 적으려는 `건드리는 곳`이 다른 작업과 겹친다 | 사용자에게 묻거나 범위를 좁힌다 |
| 다른 세션이 진행 중인 작업 파일을 고친다 | 사용자에게 묻는다 |

사용자가 겹쳐도 진행하라고 하면 작업 파일에 `- 겹침 허용: <상대 작업 ID>`를 넣는다. 어느 세션이 어느 작업을 잡았는지는 훅이 `work/.local/`에 기록하며, 이 폴더는 커밋되지 않는다. 세션이 끝나면 그 세션의 담당 표시가 지워져 다음 세션이 넘겨받을 수 있다.

훅의 한계:

- 파일 수정 도구(Edit, Write, apply_patch 등)만 본다. 셸 명령으로 파일을 바꾸는 것은 막지 못한다.
- 하네스가 적용되지 않은 프로젝트에서는 아무것도 하지 않는다.
- 훅 자체에 오류가 나면 수정을 막지 않는다.
- 같은 폴더를 쓰는 세션끼리는 검증에 서로의 수정이 섞인다. 이것은 막지 못한다.

엔진 에디터나 검증 실행처럼 한 번에 한 세션만 쓸 수 있는 것은 `with_lock.py`로 감싸 차례대로 실행한다. 같은 이름으로 실행 중인 명령이 있으면 끝날 때까지 기다린다. 감싸지 않아도 되는 것은, 프로젝트의 검증 실행기가 겹친 요청을 실패시키지 않고 기다려 준다는 것을 코드에서 확인했을 때뿐이다.

```
python .game-harness/harness/core/tools/with_lock.py unity-editor -- <실행할 명령>
```

파일은 작업마다 따로라서 여러 세션이 한 파일을 함께 고치는 일이 없다. 끝난 작업의 파일은 `work/done/<연-월>/<일>/`로 옮겨진다. 이 폴더를 커밋해 두면 다른 PC나 다른 도구에서도 이어받을 수 있다.

## 들어 있는 내용

| 위치 | 내용 |
| --- | --- |
| `core/handoff.md` | 작업 인계 기록. 시작 전 `work/now/`를 읽고, 다른 세션과 겹치는지 판단하고, 자신의 작업 파일을 남긴다 |
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

## 전역 제작 스킬과 에이전트

제작 스킬 원본은 `plugins/game-harness/bundled/skills/`에 들어 있다. 하네스가 전역에 설치하며, 관리 스킬 5개는 플러그인에서 제공한다.

| 스킬 | 하는 일 |
| --- | --- |
| `session` | 프로젝트 진행 상태, 막힘, 다음 할 일을 Git·문서·산출물로 복원 |
| `game-juice` | 타격감·피드백·연출 점검과 개선 |
| `game-character-3d` | 설정화부터 Unreal 검증까지 3D 캐릭터·무기 제작 (Tripo, Blender, Unreal) |
| `2d-character-animation` | 그림 한 장으로 Unity 2D 스켈레탈 애니메이션 제작. 검수 에이전트 `2d-rig-reviewer` 포함 |
| `store-launch` | App Store·Google Play 출시 준비와 진행 관리 |
| `respawn-lab-unity-splash` | 회사 로고 인트로 (Unity) |
| `d2b2-reference` | 디아블로 II 레저렉션 아이템 자료 검색 |
| `blender-motion-state-inspection` | Blender에서 자세·접지·방향 검사. 직접 만든 것이 아니라 ECC에서 가져온 것이다 |

### 전역에 설치되는 위치

| 위치 | 내용 |
| --- | --- |
| `~/.agents/skills/<이름>/` | 공용 제작 스킬 본문·자료·도구 |
| `~/.agents/game-harness/` | 관리 도구, 설치 목록·버전·파일 해시, 에이전트 원본 |
| `~/.claude/skills/<이름>/SKILL.md` | 공용 원본을 읽는 Claude 발견용 입구 |
| `~/.claude/agents/<이름>.md` | Claude 검수 에이전트 |
| `~/.codex/agents/<이름>.toml` | Codex 검수 에이전트. `CODEX_HOME`을 지정하면 그 경로 사용 |

Orca 전용 경로는 사용하지 않는다. Claude에서 제작 스킬은 `/session`, 관리 스킬은 `/game-harness:harness-status`처럼 호출한다. 모델·사고 수준·OS 권한은 변경하지 않는다.

### 프로젝트별 오버라이드

스킬·에이전트의 시작 절차가 다음 명령으로 현재 프로젝트의 변경사항을 읽는다.

```text
python ~/.agents/game-harness/global_runtime.py prepare skill game-juice --project <게임 폴더 또는 하위 폴더>
python ~/.agents/game-harness/global_runtime.py prepare agent 2d-rig-reviewer --project <게임 폴더 또는 하위 폴더>
```

프로젝트 루트는 가장 가까운 `.game-harness/`가 있는 폴더, Git 저장소 루트, 전달한 작업 폴더 순서로 찾는다. 사용자가 의도한 프로젝트 경로를 전달한다. 원본 저장소 자체에서 스킬을 실행하면 그 저장소가 프로젝트가 된다.

```text
내게임/.game-harness/overrides/
├─ skills/game-juice/override.md
└─ agents/2d-rig-reviewer/override.md
```

- 실제로 실행한 항목의 파일만 없을 때 생성한다. 기본 지침을 복사하지 않고 빈 템플릿을 만든다.
- 사용자 요청을 우선하고, 로컬에서 명시한 항목만 바꾸며 나머지는 전역 기본 지침을 따른다.
- Markdown은 지침 변경용이며 실행 코드를 자동으로 바꾸지 않는다. 오버라이드가 비어 있으면 기본 동작을 유지한다.
- 에이전트를 호출할 때 프로젝트의 절대 경로와 적용한 오버라이드 경로를 전달한다. 에이전트도 자신의 템플릿을 준비한다.
- 전역 업데이트는 오버라이드를 변경하지 않는다. 활성 오버라이드의 기준 본문이 바뀌면 검토 안내가 나오고, 삭제된 항목의 오버라이드도 보존·보고한다. 검토 후 파일의 `game-harness-base` 주석을 prepare 결과의 `version`·`baseHash`로 갱신하면 된다.
- 버전 고정이나 의미상의 충돌을 자동 판정하는 기능은 없다. 변경 안내를 보고 프로젝트 예외를 검토한다.

### 전역 원본 보호와 업데이트

`SessionStart` 훅은 플러그인의 원본과 전역 설치 기록을 비교하고 추가·변경·삭제를 반영한다. 같은 버전의 내용 변경도 파일 해시로 감지한다. 전역 누락·수정·추가 파일은 보고하고 배포 원본으로 복구한다. 바꿀 파일을 먼저 준비하고 교체하며, 처리 중 오류가 나면 이전 파일과 설치 기록으로 되돌린다. 실패하거나 중단된 동기화의 `sync.lock`은 상태를 확인한 뒤 수동으로 정리한다.

```text
python plugins/game-harness/scripts/harness.py global-status
python plugins/game-harness/scripts/harness.py global-sync
python plugins/game-harness/scripts/harness.py global-repair
```

- 하네스가 설치 목록에 기록한 대상만 갱신한다. Unity 공식 스킬 등 다른 전역 스킬은 건드리지 않는다.
- 파일 수정·삭제·이동 도구와 `apply_patch`는 전역 스킬·에이전트·관리 설정을 변경할 수 없다. 연결 경로와 상위 폴더 삭제도 검사한다.
- 보호 오류는 차단하고 원인을 알린다. 전역 갱신은 관리 도구의 sync/repair로 한다. 훅을 끄거나 셸 명령으로 직접 파일을 바꾸는 행위까지 강제 차단하지는 않는다. OS 권한 설정은 하지 않는다.
- 설치된 플러그인 사본도 보호한다. 공통 원본을 개발하는 Git 체크아웃은 수정할 수 있다.
- `global-repair`는 설치 버전과 같은 원본으로 복구한다. 원본 버전이 바뀌었다면 `global-sync`를 사용한다.
- 최초 설치의 비관리 파일과의 충돌, 연결된 설치 경로, 손상된 관리 기록은 자동 덮어쓰기 없이 중단한다. 복구 전에 기존 파일과 관리 기록을 확인한다.

3D 도구 경로는 환경 변수 또는 프로젝트의 `overrides/skills/game-character-3d/config.env`에 둔다. 설치본 `config.env`와 전역 실험 기록은 수정하지 않는다. D2B2 자료는 `~/.agents/reference-data/d2b2`에 별도로 보관하고 필요할 때 해당 스킬의 sync.py를 실행한다.

제작 스킬의 공통 개선은 `plugins/game-harness/bundled/`에서 작업하고 하네스 버전을 올린다. 검수 에이전트 원본과 `skills/2d-character-animation/reviewer/2d-rig-reviewer.md`는 같은 내용을 유지한다.

## 저장소 구조

```text
game-harness/
├─ .claude-plugin/marketplace.json    Claude Code용 배포 목록
├─ .agents/plugins/marketplace.json   Codex용 배포 목록
├─ plugins/game-harness/
│  ├─ .claude-plugin/plugin.json      Claude Code용 설정
│  ├─ plugin.json                     Codex용 설정 (버전의 기준)
│  ├─ skills/                         관리 스킬 5개
│  ├─ hooks/                          훅 설정 (claude.json, codex.json)
│  ├─ scripts/harness.py              관리 도구
│  ├─ scripts/work_guard.py           파일 수정 직전에 실행되는 훅
│  ├─ payload/                        게임 폴더로 복사될 내용
│  │  ├─ CHANGELOG.md
│  │  ├─ core/
│  │  ├─ modules/
│  │  └─ templates/
│  ├─ bundled/
│  │  ├─ skills/                    제작 스킬 8개 원본
│  │  └─ agents/2d-rig-reviewer.md  검수 에이전트 원본
│  ├─ scripts/global_runtime.py     전역 동기화·검사·복구·오버라이드 준비
│  └─ scripts/hook_entry.mjs        Python 선택과 훅 실행
├─ vendor-skills/                     다시 설치하는 전역 스킬의 출처와 버전 기록
└─ tests/
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
- Codex에서의 훅 동작 (`hooks/codex.json`은 문서 기준으로 작성했다. Claude Code에서는 실제 세션으로 확인했다)
- 세션을 다시 열어 이어갈 때(resume)와 서브에이전트가 파일을 고칠 때 훅이 같은 세션으로 인식하는지
- GitHub 저장소를 통한 Claude Code 설치
- 플러그인 업데이트 후 실제 Claude/Codex 세션에서 SessionStart 동기화, 제작 스킬 자동 발견, 검수 에이전트 호출까지 이어지는 전체 흐름. 임시 홈·프로젝트에서 설치/보호/복구/오버라이드와 Node 훅 실행은 자동 시험했다.
- Windows 외의 환경
- 내용물이 Unity 퍼즐 게임 하나의 경험에서 나왔으므로, 다른 종류의 게임에서도 맞는지
