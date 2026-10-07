# Rig a finished illustration in place (decomposition method, v1)

> Since 2026-09-29 the default is [visibility-map-rig.md](visibility-map-rig.md): a part map decides the cuts, visible pixels are the illustration and generated paint fills only what is hidden. Sections 5–7 below (weights, animation, Unity) still apply; the segmentation and refill sections are the fallback.

Prefer this method for painted characters: decompose one finished full-body illustration into layers where they sit, instead of generating body parts separately and assembling them. A finished illustration already has the proportions, costume design, overlaps and hand–prop contact right. Assembled parts drift in scale, style and joint placement. They produced every defect users reported in the first attempts: a lower body half as long as it should be, a head too large for the torso, boxy sleeves, arms detached at the shoulder, and a hand that did not hold the staff.

Use `../scripts/rig_layers.py` (layers, refills, shared weights, meshes, `rig.json`), `../scripts/cloth_bake.py` (physics-baked secondary motion) and `../scripts/unity/LayeredRigBuild.cs` (builds the prefab, clips, controller and preview scene from the JSON, plus a batch `Verify`). `../scripts/inspect_tools.py` gives the inspection steps: gridded zooms for reading coordinates, SIFT registration, segmentation overlays, the reference overlay, contact sheets and MP4 encoding. The complete worked example is `../examples/estelle-v007/`; with the same reference it reproduces the approved rig byte for byte. Install the Python requirements from `../scripts/requirements.txt`.

## 1. Choose the reference illustration

- It must show the whole character in a neutral, animatable pose. Pick a pose that is readable, keeps limbs slightly apart, holds props the way the animation needs, and does not use a T-pose.
- If the user's image is cropped (for example no lower body), first obtain a full-body version that preserves the design. Use image generation where the session has it. Then register it to the original to confirm the proportions: SIFT/ORB features plus RANSAC similarity, comparing head height, shoulder width, and crown-to-waist in head units.
- Keep the original and the chosen reference unchanged. All layer pixels come from the reference.
- Record the head count (crown to heel). Every later visual check compares against the reference.

## 2. Plan layers from the motion

Only parts that must move independently get their own layer. Put everything else in one base mesh.

| Layer kind | Typical members | Deformation |
| --- | --- | --- |
| Base body (one skinned mesh) | back hair, torso, hanging cloth panels, skirt columns, legs | many bone chains, one mesh |
| Head | face, fringe, front hair above a cut along the jaw/neck | skinned: head bone, blending to chest at the cut |
| Sleeves / wraps over a limb | cloth that covers an upper arm | skinned chest → shoulder → cloth panel root |
| Forearm + hand | glove, gripping hand | skinned elbow → wrist, or rigid |
| Held prop | staff, sword | rigid on the WRIST bone, sorted behind the gripping fingers |

Rules learned the hard way:
- **Hand and prop share the wrist bone.** A prop that rotates relative to a painted fist stops being held. Tilt props by bending the wrist and the arm.
- **Anchor hanging cloth to the chest or hips, not to the moving arm.** A panel parented to a shoulder whips 60–100° when the arm thrusts. Let only the sleeve over the arm follow the shoulder.
- **Cut layers where something occludes them.** The head cut runs along the jaw and neck. Glove tops sit inside sleeve cuffs. Keep the sort order consistent with the painting: sleeve in front of glove top, glove in front of hanging panel, fingers in front of prop.

## 3. Segment

How the boundaries are found: the agent reads them off the image.
1. Render gridded zooms: `inspect_tools.py grid <ref> x0 y0 x1 y1 2 out.png 20`, then step 10 near fine edges.
2. Look at each one and write polygon and joint coordinates in reference pixels.
3. Tighten each polygon with colour rules and connected components.
4. Render `mask_overlay` and fix anything that spills.

This takes judgement about what each pixel is, for example trim versus sleeve, or which layer is in front. It is not automatic unless a segmentation model is available. With one, such as Segment Anything, use point or box prompts to draft the masks, then apply the same colour rules and the same review. With OpenCV only, `cv2.grabCut` seeded from a rough polygon can snap the edges, but still review the result.

- Draw polygons in reference pixels, using zoomed crops with a 10–20 px grid, and refine them by colour: navy cloth, white glove, gold metal, skin, hair. Keep only the connected component that belongs to the part, dilate 2 px to include the ink outline, and drop specks under ~300 px from the base.
- Cut a long painted prop by shape: its top ornament polygon, a strip along the shaft (the centre line ± half width), and the bottom ornament polygon. Remove cloth and background colours inside those shapes. Do not reuse a separately drawn prop sprite if its length differs from the painted one.
- Render a segmentation overlay (a tinted mask per layer) and a re-composite of all layers. The re-composite must be indistinguishable from the reference.

## 4. Refill what moving layers will reveal

Nothing behind a moving layer is painted. Fill it before rigging, choosing the method by region:

| Region | Method (`rig_layers.py`) |
| --- | --- |
| General hole inside the base | `inpaint_holes` (TELEA + smoothed coverage for an anti-aliased silhouette) |
| Thin strip across cloth (prop shaft) | `mirror_fill_strip` (blend mirrored pixels from both sides; skip rows touching background) |
| A surface continuing under a sleeve (corset side) | `mirror_extend_rows` with a clean-texture mask (exclude gold trims and dark lines) |
| Cloth behind a lifted arm | `procedural_folds` with the cloth's median colour |
| Glove or limb top hidden in a cuff | `bleed` into the region under the sleeve |

Then check every refill at the frame where it is most exposed, zoomed in. Typical failures:
- Horizontal streaks from single-pixel row copies.
- A sleeve mask that swallowed neighbouring trim, which leaves a smear.
- A jagged coverage edge where a strip crossed a silhouette.

**LaMa option (`../scripts/lama_fill.py`).** If big-lama is installed (setup is in that file), use it only for cloth folds, trims and patterns, hair, and cloth where a prop crossed it. In the Estelle A/B it beat TELEA and mirror fills on four of five known-region tests (PSNR +2 to +6.5 dB, SSIM 0.57 → 0.85 on a shawl strip) and tied on a corset side. It needs about 0.2–3 s per hole on an RTX 2060.

When you use it:
- Grow the hole 4–6 px so no outline of the removed object stays.
- Keep prop fragments out of the context. It repainted a gold pommel onto the hem.
- Paste only the hole pixels back.
- Review the exposed frame.

Keep structured fills where anatomy or garment construction must continue, such as the bust contour or the corset side. Without LaMa, the methods above are the baseline. For comparison, Segment Anything (vit_b) was also tested for segmentation. It missed an ornate staff head and split the hand from the grip (IoU 0.18–0.87 against reviewed masks), so it is not recommended here.

## 5. One shared weight field

- Label every reference pixel with a weighting region (torso, head, hairL, sleeveL, panelL, dressL/C/R, legs …). Give each region a bone chain `[(bone, anchor), …]`.
- Build ONE field with `weight_field` (Gaussian σ ≈ 14 px) and sample it for every skinned layer. Layers that meet at a seam then carry identical weights there, so seams never open.
- Restrict each layer to its bones (`allowed`) so a sleeve does not pick up hair weights. The base layer may use a second field that ignores the arm labels. That way the base under an arm keeps its cloth weights instead of stretching with the arm.
- **Keep anatomy that must not squash rigid** (`rigid_region`). Give the bust, the face and the hands a single bone.
  - Put the torso chain's Chest anchor below the underbust, so the spine bends at the waist rather than through the bust.
  - Estelle v004 had the Spine/Chest blend across the bust, and the user saw the chest squash on the thrust.
- **Cloth lying on the body is pinned only near the body** (`pin_to_body`). Use a narrow band (~18 px) that fades out below the underbust.
  - A shawl edge over the bust then stays on the bust instead of lifting off with the arm and exposing a cut contour.
  - A wide pin, or pinning the lower drape, stretched the sleeve between the still body and the raised arm, visible as smeared trims.
- **The base layer never follows limb bones.** Exclude shoulder, elbow, wrist and prop bones from the base layer's allowed set; only sleeves and limb layers follow them. Otherwise the body image is dragged along with the arm and stretches (v005 reached ×3 at the shoulder).
- **Soft attachment for hanging cloth** (`soften_attachment`). A simulated panel hands its root weight to the chest near where it hangs, fading over about 170 px, so its swing does not shear a narrow seam next to the torso.
- **Hidden limb continuations run along the limb axis only.** A glove top extended under a sleeve should be a strip toward the shoulder, not a round dilation; a round one pokes out of the cuff as a flat block when the elbow bends.
- Every joint rests at local rotation 0 and all layers share one pixel space. Sprite bone data then matches the transforms exactly: bind delta 0.

## 6. Animate: key the body, simulate the cloth

- Key the body poses with easing: wind-up, strike, impact hold with a flash, follow-through, recovery.
- Solve props through the wrist: wrist = desired prop tilt − (hips + spine + chest + shoulder + elbow).
- Gravity-correct free limbs: shoulder = desired world angle − body lean.
- Keep the tested elbow range where the art has a baked bend. Glove tops must stay inside cuffs.
- **When cloth drapes over a limb, move the limb segment that comes out of the cloth, not the covered one.** Keep the covered shoulder within about 10°, and make reach and thrust with the elbow, wrist and a body lean ("only the hand moves"). The Estelle thrust dropped from 34° to 11° at the shoulder, and stretch next to the body fell from ×3 to ≤ ×1.8 (edges > 15 % off: SleeveR 86 → 55, arm layer 30 → 3), with the same prop tilt.
- **When the covered segment itself must move far, make its cloth rigid on that segment.** For a longer reach, give the sleeve over the upper arm to the shoulder bone as a rigid piece; it moves like a plate and never stretches. Then paint what it uncovers:
  - the body contour continuing under it (mirror each row's texture outward and ink the contour);
  - a back-cloth layer behind the body, shaped as the convex hull of the sleeve plus the tucked forearm, clipped to the original silhouette so it is invisible at rest.

  Estelle v007 got the full v004 reach (hand 253 px ahead of the chest versus 262) with zero sleeve stretch.
- Measure stretch after posing: `../scripts/stretch_check.py <rig.json> <anim.json> <clip> <frame> <ref> <out.png> x0 y0 x1 y1` skins the layers without Unity and maps stretched (red) and compressed (blue) edges.
- Simulate the cloth with `cloth_bake.simulate`. Give each chain a natural period and damping ratio; do not tune raw stiffness numbers.

| Chain | Period | Damping ζ | Parent follow |
| --- | --- | --- | --- |
| Long hair | 0.6–0.7 s | 0.5 | 0.75 |
| Cape / shawl panel | 0.85–0.9 s | 0.48 | 0.25 (hangs with gravity) |
| Skirt columns (left/centre/right) | 0.72 / 0.55 / 0.62 s | 0.44–0.5 | 0.45–0.6 |

- Make the skirt columns differ in period so a wave crosses the hem. Identical columns read as one rigid block.
- Tips are softer than roots, so waves run downward.
- Idle: add a slow breeze (≈1° amplitude, phase per chain) and take the last cycle of several simulated loops. Close the loop with `close_loop` and use periodic tangents.
- One-shot clips: bake from before t = 0. Let the body reach rest before the end, then ease the cloth to rest over the last ~0.25 s with `settle`, so the transition back to idle does not pop.
- Sanity numbers per clip: tip travel in reference px and per-column angle against the parent. Watch for fast jitter (period < 0.3 s) or motion still swinging at the clip end.

## 7. Build and verify in Unity

1. Copy `LayeredRigBuild.cs` into an Editor folder.
2. Put `rig.json`, `anim.json` and `Art/` under `Assets/<Name>/`.
3. Run `-executeMethod LayeredRigBuild.Build -rigRoot Assets/<Name>`, then `LayeredRigBuild.Verify`. Verify requires every skin to have bind delta ≈ 0 at rest and to deform in every clip.
4. Add a Play-mode check in the project: Idle → trigger → back to Idle, no console errors.

## 8. Human visual review (automated checks are not enough)

Every earlier failure passed the automated checks. Before reporting, look at renders:

- **Proportions:** overlay a Unity render on the reference at matching scale. The face, shoulders, waist, knee and heel must coincide.
- **Grip:** at rest, strike and impact, the prop passes through the fist.
- **Attachment:** zoom on the shoulders and elbows at the extreme frames. No floating limb, cut line or cuff gap.
- **Bust and body shape:** zoom on the chest at the strike and impact frames. The contour stays round, nothing flattens or folds, and no cloth stretches between body and arm.
- **Stretch map:** run `stretch_check.py` on the strike and impact frames; no red cluster next to the body or at a cuff.
- **Refills:** zoom on every revealed region at its most exposed frame.
- **Cloth:** make a contact sheet of the hem and skirt across the attack. The shape must change between frames, and the columns must not move as one piece.
- **Feet:** planted feet stay put. Compare heel crops.
- **Mirror:** check the mirrored (left-facing) instance for asymmetric details.

Report automated checks and visual review separately, state which attack concept was chosen when the user left it open, and list the remaining refill areas with when they show.
