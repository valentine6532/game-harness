# Worked example: Estelle v012 (visibility-map method)

The complete pipeline that produced `workspace/2d_animation_test/references/8_results/v012/` (2026-09-29), after the user's region review. It is a record of one character: every polygon, zone, part name and threshold here belongs to Estelle and is **not** a default for another image. Method and rules: `../../references/visibility-map-rig.md`; review: `../../references/review-protocol.md`.

Order (paths are the asset's `references/3_parts/v012/` in the original project):

| Step | Script | Output |
| --- | --- | --- |
| Proportion guide | `guide/build_guide.py` | joints, bone lengths, overlay |
| Part map of the reference | Codex with `prompts/full-LM-labelmap.txt`, then `labelmap/build_labels.py` | `labels.npy` |
| Ownership (edge rings, see-through limbs) | `labelmap/build_owner.py` | `owner.npy` |
| Limb templates (proportion) | `make_template.py`, Codex `prompts/full-T2a-limbs.txt`, `check_template.py` | colouring-book limbs |
| In-place templates from the part map | `make_templates_v2.py`, Codex `prompts/full-P-*.txt`, `check_inplace.py` | per-part paint |
| Reference where visible, paint where hidden | `finalize_v2.py` | `layers/` |
| Limbs split at joints with overlap | `split_limbs.py` | thigh/shin/foot, upper arm/forearm |
| Copies of front parts in hidden paint | `fix_hidden.py` | |
| Continue visible art into the hidden band | `lama_hidden.py` (LaMa venv) | |
| Clean plate under the staff arm and staff | Codex `prompts/full-PLATE.txt`, `plate_fill.py plate/plate.png` | |
| Pad limbs under opaque front parts | `pad_limbs.py` | |
| Sheer cloth over limbs | `unmix_sheer.py` | colour + alpha |
| All of the above | `build_layers_v2.sh` | |
| Rig | `rig_v12.py extract` (front-to-back processing, rest clip, coverage fill, edge softening) | `rig.json`, `parts/` |
| Motion | `anim_v12.py` (leg IK, cloth bake, join to idle) | `anim.json` |
| Unity | `unity/EstelleV12Build.cs` Build / Export, `EstelleV12Capture.cs`, `EstelleV12Runtime.cs` | prefab, clips, scene, frames |
| Review | `../../scripts/review/review_asset.py review.json` + reviewer | sheets, findings |

Results: rest pose share of pixels with LAB difference > 25 = 0.12 %; Unity 31 renderers, 10 skins, Play mode 0 errors; clip joins no larger than one idle frame step.

`rig_v12.py`, `anim_v12.py` and the Unity scripts grew from v007–v011; comments in them record why each rule exists.
