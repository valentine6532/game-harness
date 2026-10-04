---
name: harness-rollback
description: 게임 프로젝트의 게임 하네스를 업데이트 이전 상태로 되돌린다. "이전 하네스 버전으로 복구해줘", "하네스 업데이트 되돌려줘" 요청에 사용한다.
---

# 하네스 복구

복구는 게임 프로젝트의 git으로 한다. 하네스 업데이트는 커밋 하나로 남기므로, 그 커밋을 되돌리면 `.game-harness/harness/`, `manifest.json`, `AGENTS.md`의 하네스 구역이 함께 돌아간다.

## 도구 위치

관리 도구는 `${CLAUDE_PLUGIN_ROOT}/scripts/harness.py`다. 이 경로에 `${...}`가 글자 그대로 남아 있으면, 이 `SKILL.md`가 있는 폴더에서 `../../scripts/harness.py`를 찾아 쓴다.

## 절차

### 1. 되돌릴 대상을 찾는다

```
git log --oneline -- .game-harness/manifest.json
```

`manifest.json`을 바꾼 커밋이 하네스 적용과 업데이트 기록이다. `.game-harness/manifest.json`의 `history`에도 버전이 바뀐 순서가 있다.

### 2. 업데이트가 아직 커밋되지 않았을 때

업데이트 직후 검증에서 문제가 생긴 경우다. 하네스가 관리하는 파일만 되돌린다.

```
git status --porcelain
```

출력을 보고 하네스 업데이트로 바뀐 것(`.game-harness/harness/`, `.game-harness/manifest.json`, `AGENTS.md`)과 사용자의 다른 작업을 구분한다. 사용자에게 되돌릴 파일 목록을 보여주고 확인을 받은 뒤 그 파일만 되돌린다.

```
git restore --source=HEAD --staged --worktree -- .game-harness/harness .game-harness/manifest.json AGENTS.md
git clean -fd -- .game-harness/harness
```

`AGENTS.md`에 사용자가 따로 고친 내용이 섞여 있으면 `AGENTS.md`는 되돌리지 말고, 하네스 구역의 버전 표기만 문제가 된다는 점을 알린다.

### 3. 업데이트가 커밋되어 있을 때

되돌릴 커밋과 그 커밋이 바꾼 파일을 사용자에게 보여주고 확인을 받는다.

```
git show --stat <커밋>
```

커밋이 하네스 파일만 바꿨다면 그대로 되돌린다.

```
git revert <커밋>
```

커밋에 다른 작업이 섞여 있으면 `git revert`를 쓰지 않는다. 하네스 파일만 그 이전 상태로 가져온 뒤 새 커밋을 만든다.

```
git restore --source=<커밋>~1 --staged --worktree -- .game-harness/harness .game-harness/manifest.json
```

### 4. 확인한다

```
python "<도구 경로>" status --project .
```

- 적용 버전이 이전 버전으로 돌아왔는지 본다.
- 설치된 플러그인이 더 새 버전이므로 "새 버전 있음"으로 나오는 것은 정상이다. 손으로 고쳐진 파일이나 없어진 파일이 없어야 한다.
- 업데이트 이후에 한 게임 작업이 그대로 남아 있는지 확인한다.

### 5. 보고한다

되돌린 버전, 되돌린 커밋, 업데이트가 실패했던 원인을 알린다. 원인이 공통 하네스의 문제라면 `harness-promote`로 고칠 수 있다고 안내한다.

## 지킬 것

- `git reset --hard`나 강제 푸시를 쓰지 않는다. 업데이트 이후의 사용자 작업이 사라질 수 있다.
- 되돌리기 전에 대상 파일과 커밋을 사용자에게 확인받는다.
- git 저장소가 아닌 프로젝트는 이 방법으로 복구할 수 없다. 그렇다고 알리고, 원하는 버전의 플러그인으로 `harness-update`를 다시 실행하는 방법만 있다고 안내한다.
