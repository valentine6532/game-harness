# Worked example: Estelle v007

These are the exact scripts that produced the current approved Estelle 2D rig (v007): a horned sorceress with a floor-length star shawl, a slit dress and an armillary staff. With the same reference image they reproduce the delivered `rig.json`, `anim.json` and layer PNGs byte for byte.

- `rig_v7.py`: all character data plus the pipeline, in one file.
  - Bones (31): body, head, arms, hair ×2 chains, shawl ×2, dress ×3 columns.
  - Layer polygons and colour rules: head cut, sleeves, gloves, hand, and the painted staff (top, shaft strip, pommel).
  - Refills: TELEA, a structured corset and shawl rebuild behind the staff arm, and a mirror fill along the staff line.
  - Weighting regions and chains, per-layer allowed bones, and sorting.
  - `python rig_v7.py extract` writes the parts and `rig.json`. `python rig_v7.py preview out.png` renders the reference, the segmentation, the base layer and the re-composite.
- `anim_v7.py`: the Idle (3.2 s) and Attack (1.25 s, forward staff thrust) body keys, and the cloth chain settings (period, damping, follow). `python anim_v7.py` writes `anim.json`.

Inputs and outputs are set with environment variables:

| Variable | Meaning |
| --- | --- |
| `RIG_REFERENCE` | the full-body reference PNG (1024 × 1536 for Estelle) |
| `RIG_OUT` | working output folder (`parts/`, `rig.json`, `anim.json`) |
| `RIG_UNITY_ROOT` | Unity folder receiving `rig.json`, `anim.json`, `Art/` |

To build in Unity, copy `../../scripts/unity/LayeredRigBuild.cs` into an Editor folder. Add an `effects` entry for the flash to `rig.json` (`{"name":"CastFlash","file":"v7-CastFlash.png","anchor":"StaffTip","worldSize":0.72,"order":70}`) and `"trigger":"Attack"` to the attack clip. Then run `Build`, `Verify` and `Capture` with `-rigRoot`.

v006 differs from the first approved version (v004) in its weighting and attack pose:
- The bust follows Chest only.
- The shawl edge over the bust is pinned to the body.
- The body never follows the arm bones.
- The shawl panels have a soft attachment.
- The glove extension runs along the forearm only.
- v007: the staff sleeve is rigid on the upper arm, the uncovered bust side is repainted, and a back-shawl layer sits behind. The shoulder lifts to 28° again, for full reach without stretch.
- `make_under_v7.py` is an optional LaMa pre-fill for the back cloth. It is disabled (`USE_LAMA_UNDER = False`) because procedural folds read better here.

Use this file as a template for a new character. Keep the structure and replace the data: coordinates, colour rules, chains, refills and poses all come from the new reference image, as described in `../../references/layered-illustration-rig.md`. The generic functions duplicated here also live in `../../scripts/rig_layers.py` and `../../scripts/cloth_bake.py`. New characters should import those instead of copying.
