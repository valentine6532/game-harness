---
name: respawn-lab-unity-splash
description: Unity 프로젝트에서 "우리회사 로고 인트로 추가해줘", "리스폰랩 스플래시 넣어줘", or "Respawn Lab studio splash" 요청이 있을 때 승인된 회사 로고 애니메이션을 게임 시작 전에 구현한다. 다른 회사 로고나 스토리 인트로에는 사용하지 않는다.
---

## 프로젝트 오버라이드와 전역 원본 보호

이 스킬은 game-harness가 관리하는 전역 원본이다. 실행 전에 `~/.agents/game-harness/global_runtime.py`로 다음을 실행한다(사용 가능한 Python 실행 파일을 사용한다).

```text
python <사용자 홈>/.agents/game-harness/global_runtime.py prepare skill respawn-lab-unity-splash --project <현재 프로젝트 또는 작업 폴더>
```

명령이 반환한 `project`를 프로젝트 루트로 사용하고 `instructions`를 읽는다. 파일이 없으면 `.game-harness/overrides/skills/respawn-lab-unity-splash/override.md`에 빈 템플릿만 만들어진다. 사용자 요청을 우선하고, 로컬에서 명시한 항목만 기본 지침에 덮어 적용한다. 빈 템플릿은 동작을 바꾸지 않는다. 지정되지 않은 항목과 관련 자료는 기본 지침을 유지한다. 지침 변경은 실행 코드 자체를 변경하지 않는다.

전역의 문서·스크립트·설정·에이전트를 수정하거나 삭제하지 않는다. 새 발견·실험 기록·프로젝트 설정은 프로젝트 폴더에 남긴다. 다른 에이전트를 호출할 때 `project`의 절대 경로와 적용한 오버라이드 경로를 전달하고, 그 에이전트도 자신의 오버라이드를 준비하게 한다. 명령 실패 시 원인을 알리고 준비가 되기 전 작업을 진행하지 않는다. 공통 원본 개선은 설치본 대신 원본 저장소에서 한다.

# Respawn Lab Unity splash

Implement the approved studio logo animation in the current Unity project. Use the bundled [logo source](assets/respawn-lab-wordmark.png) and [motion specification](references/motion-spec.md); they travel with this skill, so do not depend on the company homepage repository or a localhost preview. Explicit user direction about timing, visuals, or placement takes precedence.

1. Inspect the Unity version, project instructions, existing startup scene and scene-loading flow, UI system, build profiles, and target aspect ratios. Find any existing studio splash before adding another. Identify the first game or title screen that should follow it.
2. Copy the logo into the target project's own assets. Preserve the supplied letterforms and alpha. Build clean `RESPAWN`, `L`, `A`, and `B` renderables from this art, with no slivers from adjacent letters. Display the logo in white on the specified dark background. Recreate the motion natively in Unity using the project's established UI and animation approach; do not rely on a web page, localhost server, or external video stream.
3. Make the splash a reusable scene or prefab with a single completion path. Insert it into the actual startup flow before the game/title screen without skipping existing initialization or creating a load loop. A native Unity splash shown before the engine starts is a separate stage; this studio animation begins when the first game scene runs.
4. Match the timing and visual sequence in the motion specification. Keep the logo centered and legible in portrait and landscape layouts. Respect existing skip and accessibility conventions if the project has them. Avoid adding a third-party package solely for this effect.
5. Verify the animation and handoff in the Unity Editor and the project's relevant build target when available. Check both a first launch and a repeat launch, make sure the next scene loads once, and visually inspect letter edges during motion. Report the scenes/assets changed and any build or device verification that was unavailable.
