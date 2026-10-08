"""Combine review renders into one contact sheet: python sheet.py <dir> [names...]"""
import sys
from pathlib import Path
from PIL import Image
d = Path(sys.argv[1])
names = sys.argv[2:] or ['front_x', 'front_y', 'back_x', 'back_y', 'quarter', 'quarter_wire', 'front_y_wire', 'front_x_wire']
ims = [Image.open(d / f'{n}.png').convert('RGB').resize((400, 400)) for n in names if (d / f'{n}.png').exists()]
cols = 4
rows = (len(ims) + cols - 1) // cols
c = Image.new('RGB', (400 * cols, 400 * rows), 'white')
for k, i in enumerate(ims):
    c.paste(i, ((k % cols) * 400, (k // cols) * 400))
c.save(d / '_sheet.png')
print(d / '_sheet.png')
