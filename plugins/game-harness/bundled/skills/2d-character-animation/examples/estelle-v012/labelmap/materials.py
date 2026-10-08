"""Colour classes of the reference (per pixel), used to refine part boundaries."""
import numpy as np, cv2
from PIL import Image
from pathlib import Path
HERE = Path(__file__).resolve().parent
REF = np.asarray(Image.open(HERE.parent / "reference.png").convert("RGBA"))
A = REF[..., 3] > 128
hsv = cv2.cvtColor(REF[..., :3], cv2.COLOR_RGB2HSV_FULL).astype(float) / 255
H_, S_, V_ = hsv[..., 0], hsv[..., 1], hsv[..., 2]
R, G, B = [REF[..., i].astype(int) for i in range(3)]
CLS = {
    "gold": (S_ > 0.42) & (H_ > 0.07) & (H_ < 0.17) & (V_ > 0.35),
    "skin": ((H_ < 0.08) | (H_ > 0.96)) & (S_ > 0.13) & (S_ < 0.5) & (V_ > 0.55),
    "hair": (H_ >= 0.07) & (H_ < 0.17) & (S_ > 0.12) & (S_ <= 0.42) & (V_ > 0.55),
    "white": (S_ < 0.12) & (V_ > 0.74),
    "navy": (B > R + 4) & (V_ <= 0.5),
    "blue": (B > R + 4) & (V_ > 0.5) & (S_ >= 0.12),
    "greyblue": (V_ > 0.5) & (V_ <= 0.74) & (S_ < 0.12),
    "dark": (V_ <= 0.35) & ~((B > R + 4)),
}
ORDER = list(CLS)
def classes():
    lab = np.full(A.shape, -1, np.int8)
    for i, k in enumerate(ORDER):
        lab[CLS[k] & A & (lab < 0)] = i
    lab[A & (lab < 0)] = len(ORDER)       # other
    return lab
if __name__ == "__main__":
    lab = classes()
    cols = np.array([(255,200,0),(255,150,120),(240,230,120),(255,255,255),(20,30,140),(90,150,255),(150,160,190),(60,40,20),(255,0,255)],np.uint8)
    img = np.zeros(A.shape + (3,), np.uint8); img[lab >= 0] = cols[lab[lab >= 0]]
    Image.fromarray(img).save(HERE / "materials.png")
    for i, k in enumerate(ORDER + ["other"]): print(k, int((lab == i).sum()))
