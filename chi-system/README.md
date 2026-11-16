# CHI Design System assets

- Version: **v1.2.0**（status／h／merch accent 跟主題色走）
- Source repository: https://github.com/47tsai/chi-system
- Pinned source commit: `a7f018b7836afe42103b717b5379f72a244dfded`

Vendored generated assets (copied from the CHI `dist/` directory at the pinned commit):
- `tokens.css`
- `components.css`
- `theme.js`
- `icon.js`

Logo is referenced pinned, not vendored: the logo files are `logo/status-b.png` /
`logo/status-w.png` via
`https://raw.githubusercontent.com/47tsai/chi-system/2b8cd040116133a580bae0136794679fdafdaeb1/logo/status-*.png`
(no floating `main` branch). They still point at 2b8cd04 because the status logo
bytes are unchanged between 2b8cd04 and the pinned a7f018b (only tokens.css
changed among the vendored files); the HTML pages were left untouched for this
re-pin. They are not copied into this repository because
the GitHub connector cannot push binary files; copy them locally under
`chi-system/logo/` if a future change makes local copies possible.

These files are copied from the CHI `dist/` directory at the pinned commit.
Do not edit them in this repository. Upgrade by copying a new pinned release and
reviewing the status integration before deployment.
