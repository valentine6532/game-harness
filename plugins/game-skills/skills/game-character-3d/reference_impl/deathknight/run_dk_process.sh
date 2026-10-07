#!/bin/bash
# deathknight: process_character on the Tripo-rigged whole body with the assembled parts swapped in (--baked)
# usage: bash workspace/deathknight/run_dk_process.sh <out dir> [extra args]
OUT=$1; shift
W=D:/HarnessPrograming/diablo/workspace
D=$W/deathknight
M=$W/plaza_v2/mixamo
pythonw $W/plaza_v2/tools/nowin.py D:/blander/blender.exe -b --factory-startup -P $W/plaza_v2/tools/process_character.py -- --name Hero \
  --glb $D/body/rigged/rig/tripo-out/rig-11-f28b2831/model.fbx \
  --fbx $D/body/rigged/anim/tripo-out/retarget-16-071fc80e/model.fbx \
  --out "$OUT" --baked $D/assembly/final \
  --parts $D/assembly/final/Hero_parts.glb --parts-json $D/assembly/final/Hero_parts.json \
  --fur-shells 12 --fur-length 0.018 --texfix "--steel-f0 keep --steel-chroma 1.0 --gold-f0 keep" \
  --mixamo mx_inward=$M/5_inward_slash.fbx --mixamo mx_outward=$M/3_outward_slash.fbx --mixamo mx_down=$M/2_downward_slash.fbx \
  --mixamo ssidle=$M/7_ss_idle.fbx --mixamo swordrun=$M/11_run_with_sword.fbx \
  --mixamo onehand=$M/6_one_hand_combo.fbx --mixamo power=$M/1_power_slash.fbx --mixamo ssplay=$M/14_idle_ss_play.fbx --mixamo runintent=$M/31_run_intent.fbx \
  --rezero onehand=16-40,45-68,75-98 --rezero power=18-50 --exaggerate onehand=1.35 --exaggerate power=1.35 \
  --attack-body onehand=2.2:0.12:15@16:26:34:40,45:56:63:68,75:86:92:98 --attack-body power=2.2:0.12:15@18:38:42:50 \
  --fist-hole R:0.00955 "$@"
# 4-30: blade roll so the edge, not the flat, leads the strikes -> grip.R.edge_axis (fit to the onehand/power strike frames:
# re-run after changing attack clips or windows)
pythonw $W/plaza_v2/tools/nowin.py D:/blander/blender.exe -b --factory-startup -P $D/tools/edge_axis.py -- "$OUT/SK_Hero.fbx" "$OUT/Hero.json"   --win onehand=26:33,56:62,86:91 --win power=38:42 --write
# sword grip (4-26): --fist-hole takes the grip line from the Mixamo finger bones, opens the fist tunnel along it to ~2.1 cm (game) for the
# thinned handle (props_spec HeroSword 'handle') and writes grip.R = hole centre + axis. (fist_hole.py counted the thigh
# as hole wall and is no longer run.)
# 4-28: --exaggerate turns the upper spine 1.35x as far from each attack window's start pose (quarter-view readability)
# 4-28: --attack-body (exaggerate_attack.py): step 2.2x, hip dip 12 % of height, chest lean 15 deg at the hit, legs re-solved
