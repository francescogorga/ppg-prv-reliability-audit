"""Builds brief/brief.pdf from brief_draft.md (markdown -> HTML -> headless Chrome)."""
import re
import os
import shutil
import tempfile
import subprocess
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
CHROME = (os.environ.get("CHROME_BIN") or shutil.which("google-chrome")
          or shutil.which("chromium") or shutil.which("chromium-browser")
          or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CSS = """
@page { size: A4; margin: 12mm 14mm; }
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; font-size: 9pt; line-height: 1.28; color: #111; }
h1 { font-size: 13.5pt; margin: 0 0 4px; line-height: 1.2; }
h2 { font-size: 10.5pt; margin: 9px 0 3px; border-bottom: 1px solid #ddd; }
p, li { margin: 2px 0; } ul, ol { margin: 2px 0 2px 16px; padding: 0; }
table { border-collapse: collapse; width: 100%; font-size: 8.3pt; margin: 4px 0; }
th, td { border-bottom: 1px solid #e3e3e3; padding: 2px 4px; text-align: left; vertical-align: top; }
img { width: 100%; display: block; margin: 2px auto; }
code { font-size: 8.3pt; }
a { overflow-wrap: anywhere; }
tr, img { break-inside: avoid; }
h2 { break-after: avoid; }
"""


def main():
    md = (HERE / "brief_draft.md").read_text()
    # Python-Markdown needs 4-space indentation for nested lists (the .md uses 2-3 spaces)
    md = re.sub(r"(?m)^ {2,3}([-*] )", r"    \1", md)
    body = markdown.markdown(md, extensions=["tables"])
    html = HERE / "brief.html"
    html.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Brief</title><style>{CSS}</style></head><body>{body}</body></html>")
    try:
        if not Path(CHROME).is_file():
            raise FileNotFoundError("Install Chrome/Chromium or set CHROME_BIN to its executable")
        with tempfile.TemporaryDirectory(prefix="brief-chrome-") as profile:
            subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={profile}", f"--print-to-pdf={HERE / 'brief.pdf'}",
                            html.as_uri()], check=True, capture_output=True, timeout=90)
    finally:
        html.unlink(missing_ok=True)
    print("wrote", HERE / "brief.pdf")


if __name__ == "__main__":
    main()
