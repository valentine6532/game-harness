# Rig a finished illustration with a visibility map (default method, 2026-09-29)

This supersedes the hand-cut layer method ([layered-illustration-rig.md](layered-illustration-rig.md), still valid for its weight, cloth and animation rules). The worked example is [../examples/estelle-v012/](../examples/estelle-v012/README.md); review and self-correction are in [review-protocol.md](review-protocol.md).

**Principle.** A per-part map of the reference decides where each part is visible at rest. Where a part is visible, its pixels ARE the approved illustration. Only what is hidden (behind other parts, under a sleeve, behind a prop) is generated, and generated paint is continued from the part's own visible art. Body parts are one-bone segments cut from continuous pieces with an overlap band. At rest the rig reproduces the illustration (Estelle: 0.12 % of pixels differ noticeably); in motion every revealed area is the right part.

Why not the alternatives (Estelle v008–v012, each tried and rejected by the user):
- Cutting layers by colour rules shredded parts and left cut lines that showed in motion (v008–v010).
- Generating each part separately and stacking them (v011) drifted in proportion (body stretched x1.035/y0.945), dropped a leg and a garment, and the fist did not hold the staff.
- Regenerating every part in full and using the generated paint where visible (first v012 assembly) passed a silhouette check (IoU 0.95) while 70 % of the interior showed the wrong part or drifted detail.

## 1. Proportion guide

Measure joints on the full-body reference (gridded zooms, `inspect_tools.py grid`) and write bones, lengths and rest angles (Estelle `guide/build_guide.py`). The guide fixes limb lengths for any generated limb.

## 2. Part map of the reference

1. Ask the image generator to repaint the reference as flat colour regions, one colour per part, the front-most part owning each pixel (Estelle prompt `prompts/full-LM-labelmap.txt`; it came back pixel-aligned).
2. Quantise to the palette, reassign off-palette and speck pixels, move stray islands to their surroundings, fix known confusions (gold chains read as hair, navy straps read as sleeve) → `labels.npy` (`labelmap/build_labels.py`).
3. Look at every part's region on the reference before using it.
4. Ownership rules → `owner.npy` (`labelmap/build_owner.py`):
   - the 2 px anti-aliased ring at every boundary, and dark outline strokes up to 4 px, belong to the part in FRONT; otherwise a thin line of the front part stays on the part behind and slides with it;
   - limb pixels seen through sheer cloth (warm pixels inside cloth touching a leg or shoe) belong to the limb;
   - thin slivers of one part that read as another part's lining go to that part;
   - through sheer cloth the limb keeps its own outline; cloth-coloured pixels inside a prop label belong to the cloth.

## 3. Templates and generation (colouring book)

- **Numbers in a prompt do not control proportion; a drawn shape does.** Pixel sizes in prompts gave limbs at 0.5–2x and thighs 1.5x too wide. Grey silhouettes at the guide proportions, painted inside by the generator, came back with IoU ≥ 0.996 and widths within 1.3 %, four samples out of four. The generator composites its paint through the template alpha.
- Exploded sheets (parts floating apart on an empty canvas) fail: random scale, pipe-cut joint ends, mannequin rendering. Parts drawn **in place** on the reference canvas keep scale and style.
- Template per part = its visible region + a continuation only under parts in FRONT of it, never over the background or parts behind (`make_templates_v2.py`). Under a thin prop, continue across it from both sides only. Sheets never contain touching masks.
- Proportion-template limbs (straight, guide length, reference outline) are kept as the source for hidden limb segments.
- **Register every painted sheet before splitting it** (`scripts/register_sheet.py <sheet>`): in Estelle v013, 3 of 6 sheets came back shifted 20–30 px or re-shaped even though the prompt said "in place" (template IoU 0.55–0.77). An ECC affine fit of the painted alpha to the template alpha fixed the shifts (IoU → 0.90–0.99). If the fit needs shear or a scale far from 1, the paint is re-shaped, not shifted: regenerate that sheet instead of warping it.
- Operational: run at most 3–4 generations in parallel; allow 30 min each; the generator writes PNG files in chunks, so never read a file before its job has exited; moderation blocks bare limbs at random ("sexual") — use neutral costume wording ("the leg segment as seen through the skirt slit") and send two samples of the same request; a sample can succeed after an in-run retry. The generator may be refused writing its output file ("access denied", "exceeded the 64,000-byte limit"); the image still exists under `$CODEX_HOME/generated_images/<session>/exec-*.png` (the last one of that session is the final attempt; compare all attempts). `CODEX_HOME` comes from the environment of the shell that runs `codex exec` — a terminal inside another app (e.g. Orca) points it at that app's Codex home.

## 4. Build each layer

Estelle `build_layers_v2.sh`, in this order:
1. **Reference where visible** (`finalize_v2.py`): visible region = reference pixels, hidden region = generated paint tone-matched at low frequency, 10 px blend, reference alpha on the silhouette edge. Automatic registration of generated paint failed (too few matching features); do not rely on it.
2. **Limbs** (`split_limbs.py`): one continuous in-place piece per limb (leg, glove, shoe), split at the guide joints with a 40 px overlap band; the part behind keeps a straight extension of its own paint, the part in front fades out past the joint. Painted rounded end caps show as an arc across the joint — do not use them.
3. **Copies of front parts in hidden paint** (`fix_hidden.py`): the generator paints what the reference shows behind a front part (a second leg inside the chiffon, sleeves inside the chest). Replace hidden limb paint from the proportion-template limb; refill hidden paint that matches the reference there.
4. **Continue visible art into the hidden band** (`lama_hidden.py`, LaMa): band 40–70 px, whole hidden region for small parts; mark the ring outside the layer as unknown too, or LaMa pulls the background in; close cloth across a thin prop that split it; refill hidden paint of the wrong colour class; keep hidden paint from bulging past the visible outline; the underskirt/back plate stays inside the dress and 12 px inside the silhouette.
5. **Clean plate for what a moving limb or prop reveals** (`plate_fill.py`, prompt `prompts/full-PLATE.txt`): ask the generator to repaint the reference with the moving arm, its sleeve and the held prop removed, everything else identical; check alignment outside the removed area (Estelle: median difference 0). Give each plate pixel in the removed area to the part behind whose local colour it matches, and let that part's layer take it. Limit the reach of rigid anatomy (chest, neck) to ~10 px of its own outline: with a common 60 px reach the chest took the back hair behind the staff arm (similar light colours), carried it away in the lean, and the background showed beside the bust in four review rounds. This replaced blurred LaMa hair, streaked robe edges and blotches under the arm (review rounds 1–2); prefer it to LaMa for any large area a strike uncovers.
6. **Sheer cloth** (`unmix_sheer.py`): where a sheer layer is visible over a limb, solve colour + alpha from the reference and the limb behind it so the rest pose is exact and the limb shows through in motion. Otherwise the limb is baked into the cloth and slides with it (a second calf outline and heel).

## 5. Layer processing in the rig (`rig_v12.py load_layers`)

Process front to back so each layer's "covered" test uses the finished layers in front of it:
- hidden-edge fade only ~5 px (22 px made see-through ghosts of hair and cloth); never on rigid limbs or props;
- rest clip: at rest a layer may only show where its own part is visible or where a part in front covers it;
- drop hidden pieces not connected to the part's visible region (they float in motion);
- coverage fill: every visible pixel is shown by its owner layer at full opacity;
- soften interior label edges by ~0.7 px (binary edges read as dashed stair steps in motion); keep the reference alpha on the silhouette;
- parts named like a bone get a suffix ("Art"): Unity transform names must be unique.

## 6. Motion rules added by v012

- Legs: two-bone IK every frame, feet planted.
- If sheer cloth covers a limb, keep that limb's parent still where possible: idle breath in the chest and neck, hips still; attack lean above the waist (hips keep ~30 %).
- The hem lying on the floor blends onto the root bone across the whole dress.
- A one-shot clip starts and ends on the idle's first frame for every channel (cloth included); key every channel either clip uses in both clips (an unkeyed hip kept the attack's offset during idle capture).
- Check clip joins: the frame difference at a join must not exceed an ordinary frame step.

## 6b. Poses the rest art cannot reach: swap in a painted pose (Estelle v014)

A covered shoulder can only turn a little before the rest-pose sleeve leaves the body (Estelle: ~45°); the user still asked for a full reach. Do not stretch the rig: paint the limb in the target pose and swap it in.
1. Pick the target pose on the rig itself (render candidates with `pose_render`; straighten the elbow by searching the elbow angle whose posed forearm direction matches the upper arm).
2. `scripts/arm_ext_guide.py`: render the posed body without that limb (context) and a grey template built from the posed joints (capsules for upper arm + sleeve, forearm, an ellipse for the fist on the prop, a small drape under the raised sleeve). Use a **1024x1536 canvas** crop — a 1536x1536 request came back as 1254x1254 at another scale and could not be registered.
3. Paint it with the colouring-book prompt (template, context, rest-pose design as three images).
4. `scripts/armext_parts.py`: split at the posed elbow and wrist with overlap and move each piece back by the inverse of its bone's rest→target transform; the pieces are rigid parts marked `hidden` in rig.json and skipped by every rest-pose layer step.
4b. Give the generator an enlarged "allowed area" and ask it to leave transparent what is not arm or cloth: a template-exact fill copied the template's straight edges (the sleeve read as a cut-out flag, Estelle v014 round 1). Split the pieces by material (dark sleeve on the upper bone; light glove and cuff on the forearm bone), not by straight lines, and continue the glove back to the elbow under the sleeve.
5. Make the swaps one-frame snaps inside fast motion (Estelle v14 round 3): into the painted limb straight from the wind-up while it already rises, and back straight to the rest limb's rest pose. A rest limb drawn bent looks broken at its middle angles (flat slab forearm, exposed hidden ends), so it must never be animated through them. Lock the painted limb's inner joints at their painted angles while it shows (Estelle: elbow at −150°; moving it detached the forearm from the sleeve and broke the wrist in review v14 round 2); move only the root joint. Leave the end joint only a little freedom (±45° here) if a held prop must stay near upright, and fill a short wrist under the cuff smoothly (inpaint; a pixel smear left a striped block). Swap in and out at a pose where the rest limb has the same silhouette (straight arm, low). Earlier note: keep the painted limb near its painted joint angles while it shows (straight elbow here) — bending it pulls the glove out of the sleeve hem — and swap back only where the rest limb still looks right (shoulder below ~25° for Estelle). Animation: step channels — `alpha` on the swap pieces, `hide` on the rest limb pieces — keyed in every clip (constant in Idle). Swap during fast motion (after the wind-up, back once the limb is low again). `pose_render` and the Unity builder support both channels.

## 7. Review

Silhouette IoU, bind delta, deformation and Play mode are necessary, not sufficient. Run [review-protocol.md](review-protocol.md) after every build and after every fix round; the builder does not grade its own work.
