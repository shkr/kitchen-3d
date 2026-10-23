"""Inline out/kitchen.glb into web/viewer.html -> out/kitchen-viewer.html (one self-contained page)."""
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
page = (ROOT / "web/viewer.html").read_text()
glb = base64.b64encode((ROOT / "out/kitchen.glb").read_bytes()).decode()
(ROOT / "out/kitchen-viewer.html").write_text(page.replace("__GLB_BASE64__", glb))
print("wrote", ROOT / "out/kitchen-viewer.html")
