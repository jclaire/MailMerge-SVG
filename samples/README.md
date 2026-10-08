# Sample templates

Ready-to-use templates, each paired with a matching CSV. Five are small
nametag shapes for **grid mode** (sized for a shirt-pinned badge); one is a
full-page certificate for **individual mode**; two are label sheets. They demonstrate that the generator
**auto-detects whichever `{{TOKEN}}` placeholders a template uses** and merges in
any CSV whose column names match — by name, case-insensitive, in any order — and
that it picks the right layout automatically.

| Sample | Mode | Shape / size | Placeholders / CSV columns |
|--------|------|--------------|----------------------------|
| `01-classic-badge` | grid | Rounded rectangle, 3.5in x 2.25in | `{{NAME}}`, `{{ROLE}}` |
| `02-oval` | grid | Ellipse, 3.5in x 2.2in | `{{FIRSTNAME}}`, `{{LASTNAME}}` |
| `03-circle` | grid | Circle, 2.75in dia. | `{{NAME}}`, `{{TEAM}}` |
| `04-rounded-square` | grid | Rounded square, 2.75in x 2.75in | `{{NAME}}`, `{{PRONOUNS}}` |
| `05-hexagon` | grid | Hexagon, 3.4in x 3.0in | `{{NAME}}`, `{{TITLE}}`, `{{COMPANY}}` |
| `certificate` | individual | Full-page landscape, 11in x 8.5in | `{{NAME}}`, `{{POSITION}}` |
| `avery-5520-label` | fullsheet (or grid) | US Letter, 2.625in x 1in tile, 3 x 10 | `{{MEDICATION}}`, `{{DOSE}}` |
| `single-label` | fullsheet | One 1.75in x 0.66in label (Avery 5195) | `{{LABEL}}`, `{{DETAIL}}` |

The nametag samples use the Glowforge Pro 19.5in x 11in bed, and the red shape is
the cut line, so the generated grid is ready to send straight to the laser. The
certificate has no repeating tile, so the tool emits one SVG file per row. The
Avery 5520 sample is a US Letter page with a tile group. `single-label.svg` is
one label and no tile group; `--sheet 5195` lays it out 4 × 15. Use
`--mode fullsheet` or the browser’s “One full sheet per label”.

## Run one

From the repository root:

```bash
# Grid sample -> a single tiled sheet
python mailmerge.py --template samples/03-circle.svg --names samples/03-circle.csv --output circle-tags.svg

# Certificate sample -> one file per row in ./certs
python mailmerge.py --template samples/certificate.svg --names samples/certificate.csv --out-dir certs

# Avery 5520 tile -> one full sheet of copies per row (SVG)
python mailmerge.py --template samples/avery-5520-label.svg --names samples/avery-5520.csv \
  --mode fullsheet --out-dir labels --name-field medication --sheet 5520

# Single-label SVG (no tile group) -> 60 copies on Avery 5195
python mailmerge.py --template samples/single-label.svg --names samples/single-label.csv \
  --mode fullsheet --out-dir labels --name-field label --sheet 5195
```

The tool reports the fields it detected and which CSV columns matched, e.g.:

```
Bed: 19.50in x 11.00in   Tag: 2.75in x 2.75in
Fields: name, team  (matched CSV columns: name, team)
Grid: 6 cols x 3 rows = 18 tags/sheet
Records: 6  ->  1 sheet(s)
```

## Make your own

Copy any sample, change the `{{TOKEN}}` placeholders to the fields you want, and
provide a CSV with matching column headers — no code or flags to change.

For a **grid** template, keep the two conventions the generator relies on:

- the tile artwork lives in a group labelled `inkscape:label="Nametag"` (or
  `Tile` / `Cell`), and
- the cut outline is labelled `Border` (or `<tile-label> Border`, e.g.
  `inkscape:label="Nametag Border"`); it may be a `rect`, `circle`, `ellipse`,
  `polygon`, or `polyline` — its bounding box sets the grid tile size.

For an **individual** template (like `certificate.svg`), no tile group is needed —
any SVG with at least one `{{TOKEN}}` placeholder works, and the tool writes one
file per CSV row.
