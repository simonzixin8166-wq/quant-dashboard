# V4.8.0 — Unified Design System

V4.8 consolidates the accumulated `design-v4.x.css` override chain into one maintained stylesheet: `docs/assets/design-v4.8.css`.

- One versioned design stylesheet is loaded by the generated site.
- Legacy design-v4.x files are removed automatically on every build.
- Module-owned CSS remains separate (`dashboard-v2.2.css`, `options-v2.css`, `finance-tools.css`, `opportunity-radar.css`, `roll-manager.css`, `mobile-shell.css`).
- The historical effective cascade is preserved inside the unified file, followed by a small final normalization layer.
- App and asset version bumped to 4.8.0.
