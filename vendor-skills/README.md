# 다시 설치하는 전역 스킬의 기록

직접 만들지 않은 전역 스킬은 저장소에 담지 않는다. 새 PC에서는 아래 출처에서 다시 설치한다. 이 폴더에는 어느 버전을 썼는지 알 수 있는 기록 파일만 있다(2026-10-07 기준).

| 묶음 | 개수 | 출처 | 버전 | 기록 파일 |
| --- | --- | --- | --- | --- |
| Unity 공식 | 31 | `Unity-Technologies/skills` | 커밋 `8d851729` | `unity-skills-installation.json` |
| Firebase 공식 | 13 | `firebase/agent-skills` | 스킬별 해시 | `skill-lock.json` |
| `find-skills` | 1 | `vercel-labs/skills` | 스킬별 해시 | `skill-lock.json` |
| Unreal 공식 (`create-toolset`, `unreal-mcp`, `unreal-skill`) | 3 | Claude Code 플러그인 `unreal-engine-skills-for-claude-code@claude-plugins-official` | 3.1.1 | 없음 |
| `ue-niagara-effects` | 1 | `quodsoler/unreal-engine-skills` | 커밋 `f3742d7b` | `ue-niagara-effects.source.json` |

알아둘 것:

- `skill-lock.json`은 `~/.agents/.skill-lock.json`의 사본이다. skills CLI(`npx skills add <저장소>`)가 만든 파일이다. 설치 명령은 이 저장소를 만들면서 다시 실행해 보지 않았다.
- Unity 스킬은 고정한 커밋에서 받은 뒤 `SKILL.md` 4개의 description에 따옴표만 붙였다. 어느 파일인지는 기록 파일의 `local_compatibility_fixes`에 있다.
- Unreal 3개는 이전 PC에서 설명과 본문 첫 문단을 짧게 고쳐 `~/.agents/skills`에 따로 두고 썼다. 플러그인으로 다시 설치하면 고치기 전 원본이 된다.
- `ue-niagara-effects`는 설치 도구 없이 파일 3개를 검수한 뒤 `~/.claude/skills/ue-niagara-effects`에 직접 복사했다. 기록 파일에 파일별 해시가 있다.
