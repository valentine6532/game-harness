#!/bin/sh
# Rebuild layers/ from the v2 generations (idempotent). Order: finish -> split limbs -> fix hidden copies.
set -e
cd "$(dirname "$0")"
python labelmap/build_owner.py
python finalize_v2.py v2-S6 Chest
python finalize_v2.py v2-S1 FrontPanel Neck
python finalize_v2.py v2-S7 WaistDrape
python finalize_v2.py v2-S8 WaistCharm
python finalize_v2.py v2-S4 ChiffonL FrontLockL
python finalize_v2.py v2-S3 HairBack
python finalize_v2.py v2-S2 ShawlPanelL SleeveR
python finalize_v2.py v2-S5 SleeveL
python finalize_v2.py v2-R1 ChiffonR
python finalize_v2.py v2-R2 ShawlPanelR
cp layers_v1_backup/Head.png layers_v1_backup/Staff.png layers_v1_backup/HandL.png layers/
python finalize_v2.py --kept Head Staff HandL
python - <<'PY'
import numpy as np
from PIL import Image
b=np.asarray(Image.open("layers_v1_backup/HandR_back.png").convert("RGBA")).astype(int); f=np.asarray(Image.open("layers_v1_backup/HandR_front.png").convert("RGBA")).astype(int)
fa=f[...,3:4]/255; w=b.copy(); w[...,:3]=(f[...,:3]*fa+b[...,:3]*(1-fa)).astype(int); w[...,3]=np.maximum(b[...,3],f[...,3])
Image.fromarray(w.astype(np.uint8)).save("layers/HandR.png")
PY
python finalize_v2.py --kept HandR
python - <<'PY'
import numpy as np, os
from PIL import Image
h=np.asarray(Image.open("layers/HandR.png").convert("RGBA")).copy(); f0=np.asarray(Image.open("layers_v1_backup/HandR_front.png").convert("RGBA"))[...,3]>128
fr=h.copy(); fr[~f0,3]=0
Image.fromarray(fr).save("layers/HandR_front.png"); Image.fromarray(h).save("layers/HandR_back.png"); os.remove("layers/HandR.png")
PY
FIN_OUT=layers_fin python finalize_v2.py v2-L1 LegL ForearmR GloveL
FIN_OUT=layers_fin python finalize_v2.py v2-L2 LegR ShoeL
FIN_OUT=layers_fin python finalize_v2.py v2-L3 ShoeR
python split_limbs.py
python fix_hidden.py
LAMA_MODEL=D:/ai-tools/models/big-lama.pt D:/ai-tools/venv/Scripts/python.exe lama_hidden.py
python plate_fill.py plate/plate.png
python pad_limbs.py
python unmix_sheer.py
