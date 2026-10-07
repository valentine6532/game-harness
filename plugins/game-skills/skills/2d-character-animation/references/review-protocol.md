# Review protocol and self-correction loop

A rig is not finished because it builds, binds and plays. Every Estelle version up to v012 passed bind delta 0, deformation and Play-mode checks, and v012's first assembly also passed a silhouette IoU of 0.95 while 70 % of the figure's interior was the wrong part. The only review that caught the defects compared every region with the reference, by eye, at rest and in motion. This file makes that review mandatory and repeatable, and makes the builder fix what it finds.

## 1. Run the automatic pass

`../scripts/review/review_asset.py <review.json> --out <dir>` (config keys are documented in the script; the Estelle config is `../examples/estelle-v012/review.json`). It writes:

- `regions/*.png`: one sheet per region, reference | Python rest | Python frames | Unity frames, same crop. Regions come from the part map's label boxes (large ones tiled) plus any extra boxes, so no area is left out by omission.
- `hotspots/*.png`: a zoom on every automatic finding, with the paint that was hidden at rest tinted by layer and seams that opened in magenta.
- `findings.json`: `rest_colour`, `hidden_exposed`, `holes` (a gap between different layers, not a part's own opening), `islands` (a piece that left the figure), `join_pop` (frame difference at a clip join vs an ordinary frame step), and `must_look`, the list of every sheet.

The numbers only point. `hidden_exposed` is expected in motion; it is a defect only when the exposed paint looks wrong.

## 2. Look at every sheet

- Open every file in `must_look`. A region that was not opened is reported as not checked; it is never called fine.
- Per sheet, compare each tile with the reference tile: is it the same part, same design, same outline? In motion tiles: does anything appear that is not in the reference (a copy of another part, a ghost outline, a blotch of the wrong colour, a stray strip, a hard straight cut), or disappear (a gap, a detached sleeve, a missing hem)?
- Look for these known defect types (each has a fix in section 3):

| Seen | Typical cause |
| --- | --- |
| Copy of a front part slides with a back part (double calf, second heel, staff line on a panel) | back layer's visible/hidden paint contains the front part |
| Semi-transparent ghost of hair or cloth where a front part moved away | hidden-edge fade too wide |
| Blotch of the wrong colour between moving parts | generated hidden paint that does not match the visible part |
| Floating strip or scrap in motion | hidden paint not connected to the part's visible region |
| Dashed or stair-step outline on a moving edge | binary label edge, template rim |
| Line or arc across a joint | painted end cap of a limb piece |
| Gap between a sleeve and the arm, seam opening | ownership or order at the join, cover too small |
| Whole-figure jump at a clip change | clips do not share the start pose, or a channel missing in one clip |
| Part keeps another clip's value (offset in one clip only) | channel not keyed in that clip |

## 3. Fix, rebuild, re-review

Map each finding to its fix, apply it, rebuild layers → rig → Unity, and run the review again. **Before handing a round to the reviewer, check that each fix landed at the finding's frame and pixel** (`scripts/review/layer_at.py <clip> <frame> x,y` and a local `review_asset.py` run): in Estelle v013 two staff fixes in a row never reached the cited spots (a rule limited to the staff foot; a figure closing that missed a thin hem), and each miss cost a full review round. This is checking the fix, not grading the asset. Up to three rounds by default; the user can lift the cap ("repeat until the review passes"). Stop early and report when a round does not reduce the count of high + medium findings. After every round, add each new defect type and fix to the tables here and a line to `CHANGELOG.md`, so the next asset starts with it. When one fix row has been applied twice and the finding stays, the row is wrong: find the cause from the hotspot tint (which layer is missing) and replace the row.

| Finding | Fix (Estelle v012 scripts in `../examples/estelle-v012/`) |
| --- | --- |
| Copy of a front part in a back layer | owner map gives the edge ring and see-through limb pixels to the front part (`build_owner.py`); limb-shaped copies are replaced from the proportion-template limb (`fix_hidden.py`) |
| Limb baked into sheer cloth | un-mix the cloth over the limb into colour + alpha (`unmix_sheer.py`) |
| Ghost | hidden-edge fade ≤ 5 px; never fade rigid limbs or props (`rig_v12.py` `HIDDEN_DEFAULT`, `NO_HIDDEN_FEATHER`) |
| Large area a strike uncovers looks blurred, streaked or blotched | clean plate of the reference without the moving arm and prop (`plate_fill.py`) |
| Wrong-colour hidden paint | LaMa continuation of the visible art into the hidden band, outside ring marked unknown (`lama_hidden.py`) |
| Floating scrap | drop pieces not connected to the part's visible region (`drop_islands`); close cloth across a thin prop that split it (`ACROSS_STAFF`) |
| Stair-step edges | soften interior label edges ~0.7 px (`EDGE_SIGMA`); shave the template rim |
| Joint line | straight extension of the limb's own paint past the joint, fade only the front piece (`ENDS`) |
| Gap at a join | check draw order and coverage fill; extend the cover part under the join |
| Clip-join jump | blend the one-shot clip to the idle's first frame at both ends (`join_to_idle`) |
| Channel carried over | key every channel any clip uses in every clip (constant at rest) |
| Cloth pulling a limb that sits under sheer cloth | keep that body part still (hips in idle, lean above the waist) |
| Torso side tears open when a covered arm lifts (skin blob, holes beside the bust) | cap the covered shoulder (~8°) and give the swing to the elbow (`SHOULDER_MAX`); a hidden limb under a rigid sleeve may only exist inside the sleeve |
| Background shows beside the bust/torso when the body leans in a strike (hole finding, 1000+ px, persists after the shoulder cap) | open the hole hotspot and see which layer is missing: the clean-plate pixels there went to the rigid torso instead of the hair/cloth behind it; limit the plate reach of rigid anatomy (`plate_fill.py` `REACH_OF`) so the layer behind owns them |
| Outlines dotted or saw-toothed only in Unity renders (clean in the Python render) | first check the capture scale: a Unity frame captured at 0.65x and enlarged for the sheet is compared with a 1x Python render. Capture review frames at 1 texel = 1 screen pixel (ortho size = screen height / (2 x PPU)). Trilinear mipmaps were tried and made the view soft and washed out (Estelle v013) |
| Background beside the torso when a covered arm lifts, and the hair behind swings the other way (plate reach already limited) | a torso-rigid backing layer behind the chest holding the clean plate under the arm, hidden at rest (`chest_back.py`, Estelle v013) |
| Pale band of a hidden limb that is never visible at rest shows through sheer cloth in motion | keep that limb only under opaque cloth at rest plus the joint overlap (`limit_back_thigh.py`) |
| Box of another part's paint with straight edges beside a prop strip | two plate sources meet on the same strip (a generator plate above a y limit, a LaMa plate below): use one source for the whole prop; assign a thin prop strip per row to the part bordering it (`plate_fill.py --rowwise`), not by colour distance |
| Dashed seam along both sides of where a thin prop lay on cloth | the prop's anti-aliased edge is baked into the visible cloth pixels beside it: take the plate within ~3 px of the prop too (`plate_fill.py --edge 3`); the prop layer covers them at rest |
| Loose dark strips riding on a prop, or a notch in the cloth edge beside it (wind-up frames) | the prop's dark outline ring took the neighbouring cloth's edge pixels: reassign prop-labelled pixels whose hue is the cloth's (navy) to the cloth, in the owner map and the prop layer; sample the wind-up frames too, not only the extremes |
| Tab and gap at a joint of a swapped-in painted limb | keep hand and forearm as one painted piece; let the prop turn only a little in the fist |
| Defects at a long prop's foot even in Idle | a long prop that tilts with the arm sweeps its far end over the cloth; in Idle let the end joint cancel the arm's rotation so the prop keeps its angle, and return it exactly to rest after a strike |
| Flat cut top, notch or loose strip where a prop's foot lay on a hem, after a plate | bridge the cloth under the prop per row only where the cloth layer has paint on both sides, smooth inpaint colour, clear the other rows (`hem_fix.py`, Estelle v014) |
| Hard notch / straight seam where a prop crossed cloth, after a plate fill | the generator plate is a repaint; where it is not pixel-identical to the reference (median difference outside the removed area > ~3) do not use it. Row interpolation across the prop smeared the cloth into stair-stepped bands (round 6). Use a LaMa plate instead: inpaint the reference itself with the prop removed, so it continues the surrounding pixels exactly (`scripts/make_lama_plate.py`), then give its pixels to the parts behind (`plate_fill.py --mask`) |
| Grey/brown hidden paint beside a limb that only sways (idle) | LaMa plate of the reference with that limb removed (close the figure across the limb width), given to the parts behind; the limb's own hidden end continued from its visible paint (`lama_hidden` FULL) |
| Pale lines of a part behind showing through a visible limb near a joint | the joint fade (`fade_end`) or straight extension (`straighten_end`) touched pixels visible at rest; never fade or repaint the part's own visible pixels |
| Scrap of a neighbouring part (shoe, hem) rides on a prop's tip | the kept prop layer and its label carry pixels of what used to lie beside it; keep only the prop's shape at its tip (a cone around the axis) in the layer and the owner map (`limit_staff.py`, `build_owner.py`) |
| Block sticking out of a limb end hidden under the hand | straight extension of the limb's own paint past the joint (`ENDS`, not faded) instead of the painted hidden end |
| Dark jagged fringe on hair wisps / denser edge at rest | the semi-transparent silhouette rim (alpha < 250) counted as inside: cap every layer's alpha there to the art's and give the rim to its owner only (`rest_clip`, rim ownership in `load_layers`) |
| Dark gap behind a limb that swings away | continue the part behind (back hair) under the parts that move away; fill large extensions with shifted 2-D patches of its real texture, not LaMa (blur) or per-row mirroring (streaks) (`EXTEND_UNDER`) |
| Cloth piece stuck to a prop | owner map: cloth-coloured pixels inside the prop label belong to the cloth |
| Strip where a prop crossed cloth | keep the cloth only where it bridges across the prop, fill the strip by interpolating the cloth on both sides of each row |
| Pale strip beside a limb under sheer cloth | the limb keeps its own outline under sheer cloth (owner map); pad limb pieces a few px under opaque front parts (`pad_limbs.py`); clamp the un-mixed cloth colour near its local mean |

## 4. Report

Three separate lists: automatic checks with numbers; visual review per region and frame, with the sheet paths; what was not checked. Never write "no seams" or "matches the reference" without the sheets that show it.

## Independent reviewer

The review in sections 1–2 is done by a separate reviewer that only reads and reports. Its instructions are `../reviewer/2d-rig-reviewer.md` (one file for both hosts):
- Claude Code: the `2d-rig-reviewer` agent (listed as `game-skills:2d-rig-reviewer` when the skill comes from the game-skills plugin, which carries an identical copy in its `agents/` folder; without the plugin, `~/.claude/agents/2d-character-animation` is a junction to the `reviewer/` folder). Give it the path of this skill folder along with `review.json`.
- Codex: run it as its own process so it cannot reuse the builder's context, and do not let it edit the asset, e.g. `codex exec --skip-git-repo-check "Act as the reviewer in <skill>/reviewer/2d-rig-reviewer.md. Review <asset>/review.json, round N, output <asset>/check/review-roundN." > <asset>/check/review-roundN.log`, then read its final message. The builder does not grade its own work: in Estelle v012 the builder reported arms as fine without looking, and the user found them broken.
