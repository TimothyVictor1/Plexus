# Landing page assets

Drop two files here and the landing page picks them up. Both are optional: the page is built
to look right without either, so a missing file is never a broken image or a missing glyph.

| File | What it is | Without it |
|---|---|---|
| `logo.webp` | The brand mark, shown inside the white circle in the header | A drawn SVG mark stands in. The page probes for the file on load and swaps to it the moment it exists. |
| `fonts/GeistPixel-Circle.woff2` | The local fallback display face | The headline uses BubbledotICG-FinePos from the CDN, which is the primary face anyway; monospace is behind that. |

The logo is probed rather than rendered and caught, because an `<img>` that 404s during the
server render has already failed by the time React hydrates: its `onError` never fires and the
browser's broken-image icon stays on the page.
