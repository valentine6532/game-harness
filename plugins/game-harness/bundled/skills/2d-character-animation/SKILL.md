---
name: 2d-character-animation
description: Turn one 2D character image (attachment, local path, or URL) into a working Unity skeletal animation, or plan, migrate, and debug Unity 2D rigs, Sprite Skin, IK, and sprite swaps. Use for animated characters and props; not unrelated sprite import or atlas work.
---

## 프로젝트 오버라이드와 전역 원본 보호

이 스킬은 game-harness가 관리하는 전역 원본이다. 실행 전에 `~/.agents/game-harness/global_runtime.py`로 다음을 실행한다(사용 가능한 Python 실행 파일을 사용한다).

```text
python <사용자 홈>/.agents/game-harness/global_runtime.py prepare skill 2d-character-animation --project <현재 프로젝트 또는 작업 폴더>
```

명령이 반환한 `project`를 프로젝트 루트로 사용하고 `instructions`를 읽는다. 파일이 없으면 `.game-harness/overrides/skills/2d-character-animation/override.md`에 빈 템플릿만 만들어진다. 사용자 요청을 우선하고, 로컬에서 명시한 항목만 기본 지침에 덮어 적용한다. 빈 템플릿은 동작을 바꾸지 않는다. 지정되지 않은 항목과 관련 자료는 기본 지침을 유지한다. 지침 변경은 실행 코드 자체를 변경하지 않는다.

전역의 문서·스크립트·설정·에이전트를 수정하거나 삭제하지 않는다. 새 발견·실험 기록·프로젝트 설정은 프로젝트 폴더에 남긴다. 다른 에이전트를 호출할 때 `project`의 절대 경로와 적용한 오버라이드 경로를 전달하고, 그 에이전트도 자신의 오버라이드를 준비하게 한다. 명령 실패 시 원인을 알리고 준비가 되기 전 작업을 진행하지 않는다. 공통 원본 개선은 설치본 대신 원본 저장소에서 한다.

# Unity 2D character animation

Help the user choose and implement the least complex animation method that produces the required motion. Follow project instructions and preserve existing art, gameplay behavior, and UI technology unless the requested animation needs a change.

## One-image execution mode

When the user supplies one image or image address and asks to run this skill, treat the request as an **end-to-end asset task**. Read [references/single-image-to-rig.md](references/single-image-to-rig.md) and deliver actual Unity source sprites, a bone rig with working Sprite Skin deformation, animation clips, an Animator Controller, a prefab, and a scene or equivalent preview in the target project. An explanation, sample import, static cutout, or unbound bone hierarchy does not finish this request. If motions are unspecified, make a small looping idle and one clear joint-motion demonstration suitable for the subject; say which motions were chosen.

For painted characters, default to the **visibility-map method** in [references/visibility-map-rig.md](references/visibility-map-rig.md): make a per-part map of one finished full-body illustration; where a part is visible at rest its pixels are the illustration, and only what is hidden is generated (colouring-book templates at the guide proportions, then continued from the part's own visible art); body parts are one-bone segments split with an overlap band. Worked pipeline: [examples/estelle-v012](examples/estelle-v012/README.md). The weight, cloth and animation rules of the earlier hand-cut method ([references/layered-illustration-rig.md](references/layered-illustration-rig.md), `scripts/rig_layers.py`, `scripts/cloth_bake.py`, `scripts/unity/LayeredRigBuild.cs`) still apply. Stacking separately generated parts drifts in proportion and design; do not use it as the result.

**Build → review → fix loop (mandatory).** After every build, run the review in [references/review-protocol.md](references/review-protocol.md): `scripts/review/review_asset.py <review.json>` writes a sheet for every region (reference | rest | motion frames, Python and Unity) and a zoom for every automatic finding. An independent reviewer opens every sheet and returns findings with a verdict (instructions `reviewer/2d-rig-reviewer.md`: the `2d-rig-reviewer` agent in Claude Code, a separate `codex exec` run in Codex). Map each finding to its fix in the protocol, rebuild, and review again, up to three rounds. Report the reviewer's verdict, the open findings and what was not checked; never call a region fine without its sheet.

Accept an attached image, local file path, or direct image URL. Discover the active or nearby Unity project before asking for its path. If there is no project and a compatible Editor is available, create an isolated Unity 2D demo project for the deliverable; otherwise ask only for the missing project or Editor access. Preserve the exact input image and keep generated parts and Unity assets separately identifiable. Continue through visual and runtime checks, then give the user the asset and scene paths and describe any pose limits caused by the source art.

## Working principles (apply on every machine)

- **Default to the visibility-map method** for painted characters (above). History: [examples/estelle-v007](examples/estelle-v007/README.md) (hand-cut layers), [examples/estelle-v012](examples/estelle-v012/README.md) (current).
- **Automated checks are not completion.** Bindings, bind delta, deformation, Play mode and even a 0.95 silhouette IoU passed on rejected attempts. Every region is compared with the reference by eye, at rest and in motion, through the review loop above. Report automated checks, the visual review and what was not checked separately.
- **Proportion comes from a drawn shape, not from numbers in a prompt.** Generated parts are painted inside grey templates at the guide proportions, in place on the reference canvas.
- **An asset's zones, polygons, part names and thresholds are never another asset's defaults.** The Estelle scripts are a record; rebuild the map and templates for each new image.
- **Contact must be structural.** A held prop shares the wrist bone with the hand, limbs emerge from the cloth that covers them, and neighbouring layers share one weight field.
- **Anatomy stays rigid where it must not squash.** Give the bust, the face and the hands a single bone, and keep spine bends below the underbust. Pin cloth on the body only in a narrow band near the body.
- **Under cloth, move the part that comes out of it.** Keep covered shoulders nearly still and reach with the elbow and wrist. The base layer never follows limb bones. Check `scripts/stretch_check.py` before rendering.
- **Secondary motion is simulated, not hand-keyed**, with a natural period and damping ratio per chain. Skirt columns differ so a wave travels across the hem.
- **State the choices you made.** When the user leaves a motion open (for example the attack concept), pick one that suits the character, say which, and offer alternatives. When hidden art must be invented, say where refills show and when.
- **Iterate on user feedback with a new version folder** (`8_results/vNNN`), keeping earlier versions.

## Environment

- Python 3.10+ with `scripts/requirements.txt` (numpy, opencv-python, Pillow, imageio-ffmpeg).
- A Unity Editor with `com.unity.2d.animation` (verified with Unity 6000.3.6f1 and 2D Animation 13.0.2). Run the Editor in batch mode with `-executeMethod LayeredRigBuild.Build|Verify|Capture -rigRoot Assets/<Name>`.
- Image generation (Codex CLI `codex exec -i ...` or `imagegen`) for the part map and the template paint; LaMa inpainting (`scripts/lama_fill.py`, setup inside) to continue visible art into hidden bands. Record machine paths (LaMa venv, Unity executable, generator command) in the project's own handoff notes, not in this skill.
- Without LaMa or a generator, use the structured refill methods in [references/layered-illustration-rig.md](references/layered-illustration-rig.md). Segmentation is done by gridded-zoom reading plus colour rules; Segment Anything was tested and is not recommended for ornate props.

## Choose the method from the motion

- **Transform or cutout motion:** Rotate, translate, or scale separate rigid parts around deliberate pivots. Use for simple head turns, blinking overlays, props, and other motion that does not need the image to bend. Existing UI Toolkit images can use element transforms; SpriteRenderer parts can use Transform animation. Do not add a bone package for this alone.
- **Frame animation or sprite swap:** Use when silhouettes, expressions, or perspective change substantially, or deformation would distort painted details. Keep the number and dimensions of frames appropriate to the target device.
- **Secondary motion (hair, capes, skirts, tails):** Bake it with `scripts/cloth_bake.py` (verlet chains with natural period, damping ratio and parent follow) instead of hand-keying; hand-keyed cloth reads as one rigid block.
- **Skeletal deformation:** Use when body parts must bend organically, several poses or actions reuse the same art, IK is useful, or multiple characters can share a rig. Check whether source art provides clean, separable layers and enough hidden overlap at joints; otherwise plan the art changes before rigging.
- A mix is valid: rig the parts that need bending and swap sprites for faces or extreme poses. Explain the choice in terms of visible motion, authoring cost, reuse, and measured performance where relevant.

## Package gate

Before using package APIs or changing project dependencies, read `Packages/manifest.json`, `Packages/packages-lock.json`, and the Editor version; check the connected Editor or Package Manager when the files do not establish the resolved state. Verify compatible package versions against current Unity package documentation or the registry instead of copying a version from the source guide.

| Intended feature | Package to check |
| --- | --- |
| Bone authoring, Sprite Skin deformation, Sprite Library/Resolver, or 2D IK | `com.unity.2d.animation` |
| Layered `.psb` import, or `.psd` import through the PSD Importer override | `com.unity.2d.psdimporter` |
| A measured need to optimize many animated characters with Burst | `com.unity.burst` (optional) |

Do not require URP, a 2D Renderer, PSD Importer, or Burst solely because the character uses bones. Ask for an optional package only when the selected implementation actually needs it.

An explicit request to create a working Unity skeletal asset authorizes adding the required 2D Animation package to the target project unless the user or project instructions restrict dependency changes. Name the packages and purpose in a progress update before adding them. For other requests without that authorization, ask before installing a missing required package; continue package-independent work while waiting. Do not install optional packages without a demonstrated need.

For authorized package changes, apply the official `unity-package-management` skill and verify resolution in the Editor; do not hand-edit the manifest as an installation shortcut. If using a running Editor or its CLI, apply `unity-cli` as well.

## Official guide and runnable samples

For a bone-animation how-to, teaching request, or implementation based on Unity's examples, read [references/official-rigging.md](references/official-rigging.md). It gives a version-aware path from importing art through creating bones, geometry, weights, Sprite Skin bindings, animation clips, and checking the official sample scenes. Keep version-specific UI details tied to the project's installed Editor and package; do not assume the linked 13.0 documentation matches every project.

## Skeletal workflow

1. **Prepare source art.** Preserve the original layered source. Separate body parts along useful joints; paint hidden overlap so rotations do not reveal holes. Decide facing directions and whether reflection would incorrectly swap asymmetric features. Keep consistent canvas placement, scale, and naming across skins that will share a rig. Allow enough source resolution for the largest displayed size and rotation.
2. **Import deliberately.** For layered PSB or PSD, use the supported PSD Importer and confirm the actual import mode and generated hierarchy. `.psd` may use the ordinary Texture Importer until its importer is overridden. For separate PNG parts, keep their pivots and relative positions consistent. Preserve existing runtime references during a migration.
3. **Rig and deform.** In the Skinning Editor, create the smallest useful bone hierarchy; generate mesh geometry; bind only relevant bones; then tune weights at joints. Inspect several extreme poses for stretched outlines, exposed seams, and face distortion. Use Sprite Skin only for parts whose mesh should deform. Use IK when an endpoint must track a target, such as a foot or hand; it is not mandatory for ordinary idle loops.
4. **Animate and reuse.** Create clips and transitions for the requested states. Use Sprite Library/Resolver for discrete face or part variants when appropriate. Share a skeleton, clips, and prefab base across skins only after checking equivalent part hierarchy and deformation quality.
5. **Integrate and verify.** Check the actual target scene and UI render path, including sorting, occlusion, scale, and aspect ratios. Run focused Editor checks and visually review idle, transitions, extreme poses, and at least one representative interaction on target device settings. Automated checks (bindings, bind delta, deformation, Play mode) do not catch wrong proportions, a prop the hand no longer holds, detached limbs, refill smears or cloth moving as one block; do the human review checklist in [references/layered-illustration-rig.md](references/layered-illustration-rig.md#8-human-visual-review-automated-checks-are-not-enough), including an overlay of a Unity render on the reference art. Profile the implemented approach before adding optional performance packages or changing culling and batching settings. Report automated checks and visual review separately.

When the project draws characters inside UI Toolkit, do not assume a SpriteRenderer prefab can be dropped into its visual tree. Identify the existing presentation path and choose an integration compatible with it, or explicitly plan a rendering bridge and verify it in the actual UI.

## Sources and adjacent skills

This workflow is distilled from Unity Technologies, *아티스트를 위한 2D 게임 아트, 애니메이션 및 조명 (Unity 6.3 LTS 에디션)*, especially pp. 67–86 and 136. The source PDF (`2D_Game_Art_260205-en_us-ko_kr.pdf`) is not bundled; the skill does not depend on it. Check version-specific details in the [Unity 2D Animation documentation](https://docs.unity3d.com/Packages/com.unity.2d.animation@latest/) and [PSD Importer documentation](https://docs.unity3d.com/Packages/com.unity.2d.psdimporter@latest/).

Use `sprite-editor` for importer pivot, slicing, and outline changes, and `manage-sprite-atlas` for atlas authoring when those are part of the chosen implementation. Those skills do not replace the animation method decision or rigging workflow.
