# MailMerge-SVG

Fork of [joncamp/MailMerge-SVG](https://github.com/joncamp/MailMerge-SVG) (MIT).
The browser app for this fork is at
<https://jclaire.github.io/MailMerge-SVG/>.

Mail-merge data from a CSV onto an SVG template and produce ready-to-use output in
one of three layouts:

- **Grid mode** — tile many small records (name badges, labels, place cards) into a
  grid sized for a **Glowforge Pro** laser cutter/engraver (19.5in x 11in bed).
- **Full-sheet mode** — one sheet per CSV row, every cell a copy of that single
  label, using the same margins, gaps and grid as grid mode (for example a full
  Avery sheet of one medication).
- **Individual mode** — emit one full-page SVG per CSV row (certificates, awards,
  invitations, signage).

In every mode each copy is taken verbatim from the template, so the artwork —
fonts, logos, borders, embedded images — is preserved intact; only the `{{...}}`
placeholders are replaced. The tool picks grid or individual **automatically**
from the template, or you can force a layout with `--mode` (full-sheet is always
explicit).

## Requirements

- Python 3.7 or higher
- **No third-party packages** — the standard library only.

## Quick start

```bash
# Grid of name badges (bundled template.svg + names.csv -> output.svg)
python mailmerge.py

# One certificate SVG per row, written to a folder
python mailmerge.py --template samples/certificate.svg --names samples/certificate.csv --out-dir out
```

The first command writes `output.svg` containing one badge per name, arranged in a
grid that fits the Glowforge bed. The second auto-detects that the certificate has
no repeating tile and writes one file per row (e.g. `out/John Doe.svg`).

See [`samples/`](samples/) for ready-to-use templates — five grid shapes (rounded
rectangle, oval, circle, rounded square, hexagon) plus a full-page certificate.

## Modes

| Mode | When it's used | Output |
| --- | --- | --- |
| `grid` | Template has a repeating tile group (label `Nametag`, `Tile`, or `Cell`) | A tiled sheet (`output.svg`, paginated to `output_2.svg`, …) |
| `fullsheet` | Explicit (`--mode fullsheet`) | One full sheet per CSV row in `--out-dir` (every cell is that row) |
| `individual` | Template has no tile group | One file per CSV row in `--out-dir` |
| `auto` (default) | — | Picks `grid` if a tile group is found, otherwise `individual` |

## Web app (no install)

[`index.html`](index.html) is a self-contained, browser-based version of the same
tool — no Python, no server, no dependencies. Drop in your template SVG and CSV,
pick the mode, preview the result, and download a single file or all of them as a
`.zip`. All processing happens locally in your browser; nothing is uploaded.

**One full sheet per label** (the browser’s “One full sheet per label” mode) builds
those sheets in the page and downloads them as PDFs: the sheet you are previewing,
or every row as one `.zip`. Choose the filename column under **Name files by**;
each name is that column plus the row number (`Amoxicillin-01.pdf`). The CLI
writes the same sheets as SVG (see below) so they can be diffed and printed; the
PDF step stays in the browser.

**Run it three ways:**

- **Open locally** — double-click `index.html` (or open it in any browser).
- **GitHub Pages (free hosting)** — the included workflow
  ([`.github/workflows/pages.yml`](.github/workflows/pages.yml)) publishes it on
  every push to `main`. Enable **Settings → Pages → Source: GitHub Actions** once;
  the app is then live at `https://jclaire.github.io/MailMerge-SVG/`.
- **Gist** — paste `index.html` into a public [gist](https://gist.github.com) and
  open it through `https://htmlpreview.github.io/?<raw-gist-url>`.

The web app and the Python CLI share identical merge logic and produce
byte-for-byte identical output.

## How it works

1. Reads the template and looks for a repeating **tile group** (the `<g>` whose
   Inkscape label is `Nametag`, `Tile`, or `Cell`). If one exists → grid mode; if
   not → individual mode.
2. **Auto-detects every `{{TOKEN}}` placeholder** and matches each to a CSV column
   of the same name — case-insensitive, any column order. A template can use one
   field (`{{NAME}}`) or many (`{{NAME}}`, `{{POSITION}}`, `{{DATE}}`, …); whatever
   the template declares, a matching CSV merges in automatically with no flags to
   change.
3. **Grid mode** copies the tile per row, substitutes the placeholder values
   (XML-escaped), makes the copy's element ids unique, and wraps it in a
   `translate()` group at its grid cell. Page size is read from the template's
   `viewBox` and the tile size from the `… Border` element, so the grid auto-fits
   whatever bed the template describes. With the bundled 3.25in x 0.75in tag on a
   19.5in x 11in bed this yields a **5 x 13 grid (65 tags per sheet)**; overflow
   rows spill onto `output_2.svg`, `output_3.svg`, …
4. **Full-sheet mode** uses that same grid, but each CSV row is its own sheet and
   every cell on the sheet is a copy of that one row.
5. **Individual mode** substitutes the placeholders across the whole template and
   writes one file per row, named after chosen fields (`--name-field`). Templates
   containing both `NAME` and `DATE` default to `Name - Date.svg`; other templates
   default to the first matched field. Filenames are sanitised and de-duplicated
   (`Ada Lovelace.svg`, `Ada Lovelace-2.svg`, …). The output is byte-for-byte the
   template with its tokens replaced — no re-serialisation.

**Any tile shape.** In grid mode the `… Border` cut outline may be a `rect`,
`circle`, `ellipse`, `polygon`, or `polyline`; its bounding box defines the tile
size.

**Any template size or unit works.** The template's page is reproduced exactly —
the same `viewBox`, `width`, `height` and surrounding markup are kept verbatim, so
the output is dimensionally identical to the input. In grid mode spacing is
given in millimetres and converted to the template's own coordinate system
using its declared physical `width`/`height`, so a 2&nbsp;mm gap is a real
2&nbsp;mm gap whether the template is authored in millimetres, inches, points or
pixels. `--gap` sets both axes and `--margin` sets every side. `--gap-x` /
`--gap-y` and `--margin-top` / `--margin-right` / `--margin-bottom` /
`--margin-left` override one axis or side (a value of `0` is kept; omitting the
flag keeps the shared value). (If a template declares no absolute size, the
spacing values are interpreted directly in user units.)

The template is treated as read-only and is never modified.

## CSV format

A header row whose column names match the template's placeholders. Matching is
case-insensitive and order-independent; extra columns are ignored, and any template
field with no matching column is left blank (with a warning).

```csv
Name,Title,Company
Sally Joe,Engineer,Contoso
Jim Bob,Designer,Fabrikam
```

## Options

```
python mailmerge.py [options]

  --template PATH     Template SVG (default: template.svg)
  --names PATH        CSV of merge data (default: names.csv)
  --mode MODE         auto | grid | fullsheet | individual (default: auto)

  Grid and full-sheet mode:
  --output PATH       [grid] Output SVG; extra sheets get _2, _3 suffixes (default: output.svg)
  --gap MM            Gap between tiles in millimetres, both axes (default: 2.0)
  --gap-x MM          Horizontal gap between columns in millimetres (default: --gap)
  --gap-y MM          Vertical gap between rows in millimetres (default: --gap)
  --margin MM         Margin on every side in millimetres (default: 0.0)
  --margin-top MM     Top page margin in millimetres (default: --margin)
  --margin-bottom MM  Bottom page margin in millimetres (default: --margin)
  --margin-left MM    Left page margin in millimetres (default: --margin)
  --margin-right MM   Right page margin in millimetres (default: --margin)

  Individual and full-sheet mode:
  --out-dir DIR       Folder for the per-row files (default: output)
  --name-field FIELDS Comma-separated template fields used to name each file.
                      Full-sheet names also append the row number
                      (default: NAME + DATE when present; otherwise first matched field)
```

Examples:

```bash
# Wider spacing and a 5mm margin on every side
python mailmerge.py --gap 4 --margin 5

# Same result, written out per axis and per side
python mailmerge.py --gap-x 4 --gap-y 4 \
  --margin-top 5 --margin-bottom 5 --margin-left 5 --margin-right 5

# A different grid shape + its CSV
python mailmerge.py --template samples/05-hexagon.svg --names samples/05-hexagon.csv --output hex.svg

# Certificates: one file per row, named by the POSITION field instead of NAME
python mailmerge.py --template samples/certificate.svg --names samples/certificate.csv \
  --out-dir certs --name-field position

# Force a mode (e.g. emit individual files from a template that also has a tile)
python mailmerge.py --mode individual --out-dir out
```

## One full sheet per label

Grid mode walks the CSV and puts a different row in each cell. **Full-sheet
mode** keeps that same sheet geometry — label size, columns, rows, per-side
margins and horizontal/vertical gaps — but writes **one sheet per row** and
fills every cell with copies of that row. Avery 5520 is 3 × 10 = 30 labels, so
a 40-row CSV produces 40 sheets of 30 identical labels.

In the browser, choose **One full sheet per label**, set the sheet spacing, pick
the filename column, then **Download PDF** for the sheet you are previewing or
**All PDFs (.zip)** for every row. Names look like `Amoxicillin-01.pdf`: the
chosen column, sanitized for file systems (`/`, `:`, and other unsafe
characters become `_`), plus the row number zero-padded so the files sort in
order. A blank value becomes `row-01`. If two names still collide, a `-2`
suffix is added. Blank CSV rows are skipped and do not consume a number.

The CLI writes those same sheets as SVG (this repo does not rasterize PDF
outside the browser):

```bash
python mailmerge.py --template samples/avery-5520-label.svg --names samples/avery-5520.csv \
  --mode fullsheet --out-dir labels --name-field medication \
  --margin-top 12.7 --margin-bottom 12.7 \
  --margin-left 4.7625 --margin-right 4.7625 \
  --gap-x 3.175 --gap-y 0
```

That sample is US Letter (215.9 mm × 279.4 mm) with a 66.675 mm × 25.4 mm tile,
which is the Avery 5520 die (1 in × 2⅝ in, 30-up). Print the SVG or the browser
PDF at **100% / actual size**. The first label’s top-left sits at the left
margin 4.7625 mm and top margin 12.7 mm; columns step by 69.85 mm and rows by
25.4 mm. In the browser each PDF page is that same physical size and the sheet
is drawn at 300 DPI so it fills the page.

## Letter label sheets

Grid mode can register a tile to a die-cut Letter sheet. Size the template page
to US Letter (215.9&nbsp;mm × 279.4&nbsp;mm, or 8.5&nbsp;in × 11&nbsp;in) and
size the tile border to the label. Give that border no stroke
(`stroke-width: 0`); a stroke is subtracted from the usable page and will shift
the grid. Print the SVG at **100% / actual size** — do not scale to fit.

Millimetre values below are the usual inch die layouts converted with
25.4&nbsp;mm/in. The single `--margin` / `--gap` flags still work; these
examples need the per-side and per-axis overrides. In the browser, **Gap (mm)**
and **Margin (mm)** copy into both axes and all four sides; edit **Gap X**,
**Gap Y**, **Margin top**, **Margin bottom**, **Margin left**, or **Margin
right** to override one of them.

| Sheet | Grid | Label (tile border) | Margins (mm): top, right, bottom, left | Gaps (mm): X, Y |
| --- | --- | --- | --- | --- |
| Avery 5520 (same layout as 1&nbsp;in × 2⅝&nbsp;in, 30-up) | 3 × 10 | 66.675 × 25.4 | 12.7, 4.7625, 12.7, 4.7625 | 3.175, 0 |
| Avery 5195 (1.75&nbsp;in × 0.666&nbsp;in, 60-up) | 4 × 15 | 44.45 × 16.9164 | 13.4874, 9.144, 12.1666, 7.5438 | 7.1374, 0 |
| Avery 5523 (4&nbsp;in × 2&nbsp;in, 10-up) | 2 × 5 | 101.6 × 50.8 | 12.7, 4.318, 12.7, 4.318 | 4.064, 0 |

5520 side margins are 0.1875&nbsp;in (often rounded to 0.188&nbsp;in) and the
horizontal gutter is 0.125&nbsp;in; rows are flush (vertical pitch equals the
1&nbsp;in label). 5195 is asymmetric: top 0.531&nbsp;in, right 0.36&nbsp;in,
bottom 0.479&nbsp;in, left 0.297&nbsp;in, horizontal pitch 2.031&nbsp;in
(gutter 0.281&nbsp;in), vertical pitch 0.666&nbsp;in. 5523 uses 0.5&nbsp;in
top and bottom, 0.17&nbsp;in sides, and a 0.16&nbsp;in horizontal gutter.

```bash
# Avery 5520 on US Letter. The template tile must already be 66.675 mm x 25.4 mm.
python mailmerge.py --template letter-label.svg --names names.csv --output labels.svg \
  --margin-top 12.7 --margin-bottom 12.7 \
  --margin-left 4.7625 --margin-right 4.7625 \
  --gap-x 3.175 --gap-y 0

# Avery 5195 — unequal left/right and top/bottom margins
python mailmerge.py --template letter-label.svg --names names.csv --output labels.svg \
  --margin-top 13.4874 --margin-bottom 12.1666 \
  --margin-left 7.5438 --margin-right 9.144 \
  --gap-x 7.1374 --gap-y 0

# Avery 5523
python mailmerge.py --template letter-label.svg --names names.csv --output labels.svg \
  --margin-top 12.7 --margin-bottom 12.7 \
  --margin-left 4.318 --margin-right 4.318 \
  --gap-x 4.064 --gap-y 0
```

## Files

- `template.svg` — grid template containing one tile with `{{...}}` placeholders.
- `names.csv` — merge data; column headers match the template's placeholders.
- `mailmerge.py` — the generator (grid + individual modes).
- `index.html` — browser-based version of the generator (no install).
- `output.svg` — generated grid (created when you run grid mode).
- `samples/` — example templates: five grid shapes, a full-page certificate,
  and an Avery 5520 letter label, each with a matching CSV.
- `tests/` — `python -m unittest tests.test_fullsheet` checks sheet alignment
  and that grid and individual output still match.

## Template requirements

**Grid mode and full-sheet mode**

- The tile artwork must live in a group labelled `Nametag`, `Tile`, or `Cell`
  (`inkscape:label="Tile"`).
- That group must contain at least one `{{TOKEN}}` placeholder.
- The cut outline must be labelled `<tile-label> Border` (e.g.
  `inkscape:label="Tile Border"`); it may be a `rect`, `circle`, `ellipse`,
  `polygon`, or `polyline`, and its bounding box defines the tile size.

**Individual mode**

- Any SVG containing at least one `{{TOKEN}}` placeholder. No tile group is needed.

**Both modes**

- The root `<svg>` must have a `viewBox`. Its `width`/`height` (in any absolute
  unit — mm, in, pt, px…) define the physical size; in grid mode the grid and the
  spacing flags (`--gap`, `--gap-x`, `--gap-y`, `--margin`, and the four side
  margins) adapt to it automatically. The page is otherwise reproduced exactly
  in the output.

---

*Formerly **Nametag-Generator**. It now also subsumes the old Certificate-Generator
tool via individual mode.*
