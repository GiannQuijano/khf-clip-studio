"""Build a self-contained demo page (for a claude.ai Artifact) from the real studio UI."""
import base64, re, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
s = (root / "static/index.html").read_text()
css = (root / "static/brand.css").read_text()
b64 = lambda f: "data:image/png;base64," + base64.b64encode((root / "static" / f).read_bytes()).decode()
s = re.sub(r"<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", s, flags=re.I)
s = re.sub(r'<meta charset[^>]*>\s*<meta name="viewport"[^>]*>\s*', "", s)
s = s.replace("<title>Clip Studio · Kind Human Foundation</title>", "<title>KHF Clip Studio Demo</title>")
s = s.replace('<link rel="stylesheet" href="brand.css">', "<style>\n" + css + "\n</style>")
s = s.replace('<link rel="icon" href="logo.png">\n', "")
s = s.replace('src="logo.png"', f'src="{b64("logo.png")}"').replace('src="logo-white.png"', f'src="{b64("logo-white.png")}"')
s = s.replace("</head>\n<body>\n", "")
s = s.replace("</body>\n</html>", "")
demo_css = """<style>
.demo-banner{background:var(--hl-soft);color:var(--ink);font-size:14px;padding-block:8px;padding-left:max(20px,env(safe-area-inset-left,0px));padding-right:max(20px,env(safe-area-inset-right,0px));border-bottom:1px solid var(--line)}
.demo-banner b{color:var(--hl-ink)}
.demo-player canvas{display:block;margin:0 auto;height:min(60vh,520px);max-width:100%;aspect-ratio:9/16;width:auto;border-radius:10px;background:#000;cursor:pointer}
.demo-bar{display:flex;align-items:center;gap:10px;margin-top:10px}
.demo-scrub{flex:1;height:6px;background:var(--chip);border-radius:99px;cursor:pointer;position:relative}
.demo-scrub i{position:absolute;left:0;top:0;bottom:0;background:var(--hl);border-radius:99px}
.demo-export{display:block;width:100%;height:auto;max-height:380px;object-fit:contain;border-radius:10px;background:#000}
.layout{min-height:auto}
</style>
"""
before = (root / "demo/shim-before.js").read_text()
after = (root / "demo/shim-after.js").read_text()
assert "\ninit();\n</script>" in s
s = s.replace("\ninit();\n</script>", "\n</script>\n<script>\n" + after + "\n</script>")
s = s.replace("<script>\n", demo_css + "<script>\n" + before + "\n</script>\n<script>\n", 1)
out = Path(sys.argv[1]); out.write_text(s); print(out, len(s))
