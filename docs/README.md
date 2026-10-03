# docs

**`AskCell-Method-Brief.html`** — a condensed, print-oriented version of the
technical proposal. Self-contained: the fonts are embedded as data URIs, so it
renders and prints identically with no network access.

To read it, open the file in any browser. To print, `Ctrl+P` — the print
stylesheet forces black-on-white regardless of your screen theme, so a dark-mode
browser will not produce dark pages.

`AskCell-Method-Brief.pdf` is that file rendered to 8 pages. Regenerate it with
any Chromium browser:

```bash
chrome --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=docs/AskCell-Method-Brief.pdf \
  file:///absolute/path/to/docs/AskCell-Method-Brief.html
```

On Windows, `chrome` is usually
`"C:/Program Files/Google/Chrome/Application/chrome.exe"`, and `msedge.exe`
works identically.

---

**`AskCell-Bao-Cao-Nghien-Cuu.html`** — the formal Vietnamese-language research
report (báo cáo nghiên cứu) for a school science-fair submission, following the
competition's required format (A4, 3/2/2/2 cm margins, Times New Roman 14,
single spacing, cover page + mục lục + 5 chapters + references). Regenerate the
PDF the same way as the method brief above, substituting the filename. The
mục lục's page numbers are hand-estimated and should be checked against the
actual PDF pagination before submission; the reference list (6 sources) was
verified against real published papers, not generated from memory alone.
