# CHI Design System assets

- Version: **v1.1.0**（含 100dvh 側邊欄修正）
- Source repository: https://github.com/47tsai/chi-system
- Pinned source commit: `2b8cd040116133a580bae0136794679fdafdaeb1`

Vendored generated assets (copied from the CHI `dist/` directory at the pinned commit):
- `tokens.css`
- `components.css`
- `theme.js`
- `icon.js`

Logo is referenced pinned, not vendored: the logo files are the same pinned
commit's `logo/status-b.png` / `logo/status-w.png` via
`https://raw.githubusercontent.com/47tsai/chi-system/2b8cd040116133a580bae0136794679fdafdaeb1/logo/status-*.png`
(no floating `main` branch). They are not copied into this repository because
the GitHub connector cannot push binary files; copy them locally under
`chi-system/logo/` if a future change makes local copies possible.

These files are copied from the CHI `dist/` directory at the pinned commit.
Do not edit them in this repository. Upgrade by copying a new pinned release and
reviewing the status integration before deployment.
