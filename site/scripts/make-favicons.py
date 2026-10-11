"""Build tab icons: the mark on a rounded white tile, so it reads on light and dark browser chrome."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
mark = Image.open(ROOT / "src/assets/genesis-mark.png").convert("RGBA")


def tile(size, radius_ratio=0.22, pad_ratio=0.12):
    scale = 4  # supersample for smooth corners
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, s - 1, s - 1), int(s * radius_ratio), fill=(255, 255, 255, 255))
    inner = int(s * (1 - 2 * pad_ratio))
    m = mark.copy()
    m.thumbnail((inner, inner), Image.LANCZOS)
    img.alpha_composite(m, ((s - m.width) // 2, (s - m.height) // 2))
    return img.resize((size, size), Image.LANCZOS)


tile(32).save(ROOT / "public/favicon-32.png")
tile(256).save(ROOT / "public/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("wrote favicon-32.png, favicon.ico")
