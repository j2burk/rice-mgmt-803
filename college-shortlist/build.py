# Builds shortlist.html (the published page) from src.html + map.json.
from pathlib import Path
d = Path(__file__).parent
src = (d / "src.html").read_text()
(d / "shortlist.html").write_text(src.replace("/*MAPDATA*/null", (d / "map.json").read_text()))
print("built", d / "shortlist.html")
