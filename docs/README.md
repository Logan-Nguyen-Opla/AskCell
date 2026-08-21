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
