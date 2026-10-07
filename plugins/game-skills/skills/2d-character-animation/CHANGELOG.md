# Changelog

## 2026-10-07 (moved into the game-harness repository)
- The skill now ships in the `game-skills` plugin (`plugins/game-skills/skills/2d-character-animation`). The plugin carries a copy of `reviewer/2d-rig-reviewer.md` in its `agents/` folder (keep the two identical), so the `~/.claude/agents/2d-character-animation` junction is only needed when the skill is used without the plugin.
- Removed paths that only worked on one PC: the reviewer takes the skill folder from the caller (or searches for it) instead of a fixed path under one user's home folder; `scripts/make_lama_plate.py` falls back to its own skill folder when `ANIM2D_SKILL` is not set; the note about the source PDF no longer names a local Downloads path.

## 2026-09-29
- Default method is now the visibility-map method (`references/visibility-map-rig.md`), from Estelle v012: a per-part map of the reference decides the cuts; visible pixels are the illustration; generated paint (colouring-book templates at guide proportions, then LaMa continuation) fills only hidden areas; limbs are one-bone segments split with overlap.
- New build → review → fix loop (`references/review-protocol.md`) with `scripts/review/review_asset.py` (region sheets from the part map, hotspot zooms, findings.json) and an independent reviewer (`reviewer/2d-rig-reviewer.md`, linked for Claude Code by the junction `~/.claude/agents/2d-character-animation` → `reviewer/`, read-only tools).
- New worked example `examples/estelle-v012/`. Previous skill state backed up in the asset-maker project at `workspace/2d_animation_test/joblog/skill-backup-2026-09-29/`.

## 2026-09-30 (Estelle v013, review round 4 → rebuild)
- Round 4 on v012 (FAIL, 4 high / 7 medium): a user thread reported that the invented lower body faced the viewer while the torso turned three-quarters. New rule in `single-image-to-rig.md` step 3: invented parts keep the source's viewing angle and stance; composite the source back and measure the kept region.
- Torso-side hole that survived rounds 1–4: caused by `plate_fill` giving hair pixels to the rigid chest (60 px reach). Fix: `REACH_OF` for rigid anatomy; protocol row added; the old "cap the shoulder" row was the wrong remedy for this case.
- Unity dotted outlines (rounds 3–4): first tried trilinear mipmaps — it made the 0.65x view soft and washed out and was reverted. Cause: review sheets compared a 0.65x Unity capture (enlarged) with a 1x Python render. Review captures are now 1:1.
- Painted template sheets can come back shifted 20–30 px: new `scripts/register_sheet.py` (ECC affine to the template alpha); regenerate when the fit needs shear.
- Generator output refused by its sandbox: recover from `$CODEX_HOME/generated_images`.
- Review loop: the three-round cap is a default the user can lift; stop when a round does not reduce high + medium; record each round's lessons here.

## 2026-09-30 (Estelle v013, review round 5 → fixes)
- Round 5 (FAIL, 4 high / 8 medium): lower body now reads turned with the torso and the waist seam is joined (reviewer). New defect classes and fixes added to the protocol table: torso-rigid backing plate under a lifted arm (`chest_back.py`); never-visible hidden limb limited to opaque cloth; repainted plate not used where it is not pixel-identical; joint fade/extension never touches visible pixels; prop tip cone in layer and owner map; straight extension past the wrist; rim alpha ownership.
- A layer-ID tool (`layer_at.py` in the Estelle v013 folder) answers "which layer shows at this frame pixel"; use it before choosing a fix row.

## 2026-09-30 (Estelle v013, review round 6 → fixes)
- Round 6 (FAIL, 3 high / 7 medium; down from 4 / 8). Unity-only dotted outlines gone with 1:1 captures; torso hole 1173 → 348 px.
- New `scripts/make_lama_plate.py`: a clean plate made by LaMa from the reference itself (pixel-identical outside the removed area). Replaces generator plates where those are repaints, and row interpolation across a prop (stair-stepped bands). Used for the staff below the waist and the swaying left arm.
- Hidden back shin limited like the back thigh (pale band through the chiffon); ChestBack area widened.

## 2026-09-30 (Estelle v013, review round 7 → fixes)
- Round 7 (FAIL, 3 high / 6 medium; 10 → 9). The three highs had one cause: the staff strip below the waist. Two previous fixes had not reached the cited spots; new protocol rule: verify each fix at the finding's frame/pixel before the next review round.
- `plate_fill.py`: `--mask` (only where that plate removed something), `--rowwise` (thin prop strip takes the bordering part per row), `--edge N` (replace the prop's anti-aliased edge baked into the cloth beside it). One LaMa plate for the whole staff. Pale staff-rim pixels touching cloth go to the cloth in the owner map. Feet keep hidden paint only inside the shoe and at the ankle overlap.
- Unity: the cast flash sorted behind the parts (order 70) read as a muddy olive disc in the orb; draw it above every part.

## 2026-09-30 (Estelle v013, review round 8 — loop stopped)
- Round 8 FAIL 3 high / 6 medium, same count as round 7; the stopping bar (no highs, fewer high+medium) was not met, so the loop stopped and the decision went to the user. High+medium per round: 11 → 12 → 10 → 9 → 9.
- Lesson: after the structural fixes (torso backing plate, LaMa plates, 1:1 captures) the remaining class is hidden paint shown at motion extremes; each round fixed some and exposed others. Set the stopping bar before the loop and hand the "is this acceptable at game distance / reduce the motion instead?" question to the user rather than looping silently.

## 2026-09-30 (Estelle v014, user feedback after round 8)
- Feedback: the strike reaches too little; the back leg copies the front leg's bend. Causes: the covered shoulder was capped at 8° since v012 round 1 (a correct fix for one defect that made the motion timid); the invented lower body had two identical legs.
- New method "swap in a painted pose" (`references/visibility-map-rig.md` 6b; `scripts/arm_ext_guide.py`, `scripts/armext_parts.py`; `alpha`/`hide` channels in `review/pose_render.py` and the Unity builder).
- Lower-body prompts now state which leg bears the weight: straight, mostly hidden back leg; only the front leg bends.
- Lesson: a motion limit added to hide an art defect must be revisited once the defect is fixed another way (here the torso backing plate); otherwise the animation stays timid and the user sees it first.

## 2026-09-30 (Estelle v014, review loop stopped at the user's 10-round limit)
- 10 rounds on v014: user feedback items (straight back leg, far reach) fixed and accepted from round 1; the painted-limb swap method stabilised by round 4 (lock inner joints, snap swaps, fist in one piece). High+medium stayed between 4 and 11 per round.
- Lessons: (1) every motion extreme reveals what the rest pose hides — the remaining defects cluster at a prop's rest place (staff over shawl edge and hem) and behind swinging hair/cloth; (2) damping secondary motion in the strike (hair, right shawl, right skirt ×0.35–0.5) and keeping a long prop's angle in Idle removed more defects than per-pixel fixes; (3) LaMa plates of the reference beat generator plates wherever the plate must meet visible art; (4) reviewer runs sample different frames, so counts vary ±3 — judge the trend over rounds and fix the review frame set first (include wind-up, after-snap and several idle frames from round 1).
- Next time: plan the rest pose so a long prop does not lie across cloth edges it will leave (or paint the covered cloth as its own clean layer up front) before the review loop starts.
