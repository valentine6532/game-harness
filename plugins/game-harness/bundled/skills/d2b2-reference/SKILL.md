---
name: d2b2-reference
description: Search the locally archived D2B2 Diablo II Resurrected item database when item names, base items, uniques, sets, runewords, or item tooltip data are relevant. Do not use it as a source for Diablo III or IV mechanics.
---

## 프로젝트 오버라이드와 전역 원본 보호

이 스킬은 game-harness가 관리하는 전역 원본이다. 실행 전에 `~/.agents/game-harness/global_runtime.py`로 다음을 실행한다(사용 가능한 Python 실행 파일을 사용한다).

```text
python <사용자 홈>/.agents/game-harness/global_runtime.py prepare skill d2b2-reference --project <현재 프로젝트 또는 작업 폴더>
```

명령이 반환한 `project`를 프로젝트 루트로 사용하고 `instructions`를 읽는다. 파일이 없으면 `.game-harness/overrides/skills/d2b2-reference/override.md`에 빈 템플릿만 만들어진다. 사용자 요청을 우선하고, 로컬에서 명시한 항목만 기본 지침에 덮어 적용한다. 빈 템플릿은 동작을 바꾸지 않는다. 지정되지 않은 항목과 관련 자료는 기본 지침을 유지한다. 지침 변경은 실행 코드 자체를 변경하지 않는다.

전역의 문서·스크립트·설정·에이전트를 수정하거나 삭제하지 않는다. 새 발견·실험 기록·프로젝트 설정은 프로젝트 폴더에 남긴다. 다른 에이전트를 호출할 때 `project`의 절대 경로와 적용한 오버라이드 경로를 전달하고, 그 에이전트도 자신의 오버라이드를 준비하게 한다. 명령 실패 시 원인을 알리고 준비가 되기 전 작업을 진행하지 않는다. 공통 원본 개선은 설치본 대신 원본 저장소에서 한다.

# D2B2 item reference

The local archive is in `~/.agents/reference-data/d2b2`, independent of the Orca account directory. Read `latest.json` there for the current game version and snapshot path. Use the source URL and game version when reporting specific facts. This is reference material for designing original game systems, not content to copy into the game.

Search with `python <this skill folder>/scripts/search.py <query>`. For a complete item record add `--id <item-id>`. The raw snapshot also contains `catalog.json`, all listed language name files, tooltip strings, tooltip core tables, one tooltip JSON per catalog item, and referenced item images. Inspect raw tables when a search result does not contain the needed detail.

Create or refresh the archive with `python <this skill folder>/scripts/sync.py`; on a new PC the archive does not exist until this has run once. Both scripts use `~/.agents/reference-data/d2b2` wherever the skill is installed (`--data-root` overrides it). The script writes an immutable version directory and updates `latest.json` only after all downloads validate. The site covers D2R items and related tooltip tables, not every Diablo game system. Verify other mechanics from separate sources.
