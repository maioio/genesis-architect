"""Derive transparent dark-theme logo variants: lighten the navy artwork, keep alpha."""
from pathlib import Path
import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "src" / "assets"
NAVY = np.array([0, 32, 160], dtype=float)
NAVY_LIGHT = np.array([168, 200, 255], dtype=float)
BRIGHT = np.array([0, 128, 240], dtype=float)
BRIGHT_LIGHT = np.array([64, 176, 255], dtype=float)

for name in ("genesis-logo", "genesis-mark"):
    im = np.array(Image.open(ASSETS / f"{name}.png").convert("RGBA"), dtype=float)
    rgb, a = im[..., :3], im[..., 3:]
    d_navy = np.linalg.norm(rgb - NAVY, axis=-1)
    d_bright = np.linalg.norm(rgb - BRIGHT, axis=-1)
    # t=1 at navy, 0 far from it; same for the bright blue. Smooth, so anti-aliased edges stay clean.
    t_n = np.clip(1 - d_navy / 140, 0, 1)[..., None]
    t_b = np.clip(1 - d_bright / 140, 0, 1)[..., None]
    out = rgb + t_n * (NAVY_LIGHT - NAVY) + t_b * (BRIGHT_LIGHT - BRIGHT)
    out = np.clip(out, 0, 255)
    Image.fromarray(np.concatenate([out, a], axis=-1).astype("uint8"), "RGBA").save(ASSETS / f"{name}-dark.png")
    print("wrote", f"{name}-dark.png")
