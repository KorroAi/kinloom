"""Keeps only the floor atlas (with its grass/dirt terrain set) from the pixel-boy NinjaAdventure tileset.tres (CC0)."""
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")
sections = [s for s in re.split(r"(?m)^(?=\[)", text) if s]

floor_ext = next(re.search(r'(?<![a-z])id="([^"]+)"', s).group(1) for s in sections
                 if s.startswith("[ext_resource") and "tileset_floor.png" in s)
keep = []
floor_sub = None
for sec in sections:
    if sec.startswith("[gd_resource"):
        keep.append(re.sub(r"load_steps=\d+ ", "", sec))
    elif sec.startswith("[ext_resource") and "tileset_floor.png" in sec:
        keep.append(sec.replace("res://content/map/tileset_floor.png", "res://assets/tiles/tileset_floor.png"))
    elif sec.startswith("[sub_resource") and f'ExtResource("{floor_ext}")' in sec:
        floor_sub = re.search(r'(?<![a-z])id="([^"]+)"', sec).group(1)
        keep.append(sec)
    elif sec.startswith("[resource]"):
        lines = [l for l in sec.splitlines() if not l.startswith("sources/")]
        lines.append(f'sources/0 = SubResource("{floor_sub}")')
        keep.append("\n".join(lines) + "\n")
out = re.sub(r' uid="uid://[^"]+"', "", "".join(keep))
dst.write_text(out, encoding="utf-8")
print(f"{dst}: {out.count('terrain_set = 0')} terrain tiles")
