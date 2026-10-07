---
name: respawn-lab-unity-splash
description: Unity 프로젝트에서 "우리회사 로고 인트로 추가해줘", "리스폰랩 스플래시 넣어줘", or "Respawn Lab studio splash" 요청이 있을 때 승인된 회사 로고 애니메이션을 게임 시작 전에 구현한다. 다른 회사 로고나 스토리 인트로에는 사용하지 않는다.
---

# Respawn Lab Unity splash

Implement the approved studio logo animation in the current Unity project. Use the bundled [logo source](assets/respawn-lab-wordmark.png) and [motion specification](references/motion-spec.md); they travel with this skill, so do not depend on the company homepage repository or a localhost preview. Explicit user direction about timing, visuals, or placement takes precedence.

1. Inspect the Unity version, project instructions, existing startup scene and scene-loading flow, UI system, build profiles, and target aspect ratios. Find any existing studio splash before adding another. Identify the first game or title screen that should follow it.
2. Copy the logo into the target project's own assets. Preserve the supplied letterforms and alpha. Build clean `RESPAWN`, `L`, `A`, and `B` renderables from this art, with no slivers from adjacent letters. Display the logo in white on the specified dark background. Recreate the motion natively in Unity using the project's established UI and animation approach; do not rely on a web page, localhost server, or external video stream.
3. Make the splash a reusable scene or prefab with a single completion path. Insert it into the actual startup flow before the game/title screen without skipping existing initialization or creating a load loop. A native Unity splash shown before the engine starts is a separate stage; this studio animation begins when the first game scene runs.
4. Match the timing and visual sequence in the motion specification. Keep the logo centered and legible in portrait and landscape layouts. Respect existing skip and accessibility conventions if the project has them. Avoid adding a third-party package solely for this effect.
5. Verify the animation and handoff in the Unity Editor and the project's relevant build target when available. Check both a first launch and a repeat launch, make sure the next scene loads once, and visually inspect letter edges during motion. Report the scenes/assets changed and any build or device verification that was unavailable.
