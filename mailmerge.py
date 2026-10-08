"""SVG mail merge with two output layouts.

Performs a "mail merge" of rows from a CSV onto an SVG template whose artwork
contains ``{{TOKEN}}`` placeholders. Every distinct token is auto-detected and
matched to a CSV column of the same name (case-insensitive, any order), so a
template declares the fields it needs and any matching CSV merges in.

Three output modes:

- ``grid`` -- the template carries a single repeating tile (a ``<g>`` labelled
  ``Nametag``/``Tile``/``Cell`` containing a ``... Border`` cut shape). The tile
  is copied once per row and tiled into a grid sized to fit a laser bed
  (e.g. a Glowforge Pro, 19.5in x 11in) with a small gap between cuts. The gap
  can differ horizontally and vertically, and the page margin can differ on
  each side, so a sheet can register to an asymmetric die-cut layout. Ideal for
  nametags, labels and other many-up cut sheets.
- ``fullsheet`` -- one page per CSV row, every cell a copy of that row. A
  template with a tile group uses that tile. A single-label SVG (no tile
  group) is copied onto the sheet as-is: US Letter, or the page of an Avery
  sheet chosen with ``--sheet``. A 30-up layout and a 40-row CSV produce 40
  sheets of 30 identical labels.
- ``individual`` -- the whole template page is one document (a certificate,
  diploma, badge, ...). One output SVG is written per CSV row.

``auto`` (the default) picks ``grid`` when the template has a recognised tile
group, otherwise ``individual``.

Design goals:
- Keep the template SVG as intact as possible. Artwork is copied verbatim from
  the template (the raw XML is sliced out as text rather than re-serialized), so
  fonts, logos, embedded images and cut borders are preserved byte-for-byte.
  The only changes are the substituted values and, in grid mode, made-unique
  element ids plus a wrapping ``translate()`` group per copy.
- No third-party dependencies -- standard library only.
"""

import argparse
import csv
import json
import os
import re
import sys


# --- placeholder / label configuration -------------------------------------

# Placeholders look like ``{{NAME}}`` / ``{{First Name}}``. Every distinct token
# found in the template is matched to a CSV column of the same name, so a
# template defines which fields it needs and any matching CSV merges into it.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

# Grid mode looks for a single repeating tile group carrying one of these
# Inkscape labels; its cut outline is labelled "Border" (or the tile label
# followed by " Border", e.g. "Nametag Border").
TILE_LABELS = ("Nametag", "Tile", "Cell")

MM_PER_INCH = 25.4

# A single-label template with no chosen sheet is laid out on US Letter.
LETTER_WIDTH_MM = 8.5 * MM_PER_INCH
LETTER_HEIGHT_MM = 11 * MM_PER_INCH

# Template vs sheet label size, and a grid that runs off the page, are reported
# rather than scaled or clipped when they differ by more than this.
SIZE_TOLERANCE_MM = 0.5

# Conversion of CSS/SVG absolute length units to millimetres. ``None`` marks
# units that have no fixed physical size (``%`` or unitless user units).
UNIT_TO_MM = {
    "": None,
    "mm": 1.0,
    "cm": 10.0,
    "q": 0.25,
    "in": 25.4,
    "pt": 25.4 / 72.0,
    "pc": 25.4 / 6.0,
    "px": 25.4 / 96.0,
    "%": None,
}

_LENGTH = re.compile(r"^\s*([+-]?[0-9]*\.?[0-9]+)\s*([a-z%]*)\s*$", re.IGNORECASE)


def parse_length(value):
    """Split an SVG length like ``19.5in`` into (number, unit). Returns
    (None, None) when the value is missing or unparseable."""
    m = _LENGTH.match(value or "")
    if not m:
        return None, None
    return float(m.group(1)), m.group(2).lower()


def fmt(value):
    """Format a float compactly (trim trailing zeros) for SVG attributes."""
    return f"{value:.5f}".rstrip("0").rstrip(".")


# --- Avery sheet library ----------------------------------------------------

def avery_sheets_path():
    """Path to the built-in sheet library (a JS assignment the browser can load)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "avery-sheets.js")


def load_avery_sheets(path=None):
    """Read ``avery-sheets.js`` and return the list of sheet records.

    The file is ``var AVERY_SHEETS = [ ... ];`` so a browser script tag can
    load it. Units inside each record are inches; see the file header.
    """
    path = path or avery_sheets_path()
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError(f"{path} does not contain a JSON array of Avery sheets.")
    return json.loads(text[start:end + 1])


def _sheet_key(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def find_sheet(token, sheets=None):
    """Return the sheet record whose id or product numbers match ``token``."""
    key = _sheet_key(token)
    if not key:
        raise ValueError("Sheet number is empty. Run --list-sheets to see the built-in formats.")
    sheets = load_avery_sheets() if sheets is None else sheets
    for sheet in sheets:
        names = [sheet.get("id")] + list(sheet.get("products") or [])
        if any(_sheet_key(name) == key for name in names):
            return sheet
    shown = ", ".join(sheet["products"][0] for sheet in sheets)
    raise ValueError(
        f"Unknown Avery sheet {token!r}. Run --list-sheets to see the built-in formats ({shown})."
    )


def sheet_option_label(sheet):
    """Dropdown text such as ``5160/5520 — 2-5/8" × 1" (30 per sheet)``."""
    numbers = "/".join(sheet["products"])
    count = sheet["columns"] * sheet["rows"]
    if sheet["pageWidthIn"] == 8.5 and sheet["pageHeightIn"] == 11:
        where = f"{count} per sheet"
    else:
        where = f"{count} per {sheet['pageWidthIn']:g}×{sheet['pageHeightIn']:g} in sheet"
    return f"{numbers} — {sheet['sizeLabel']} ({where})"


def sheet_spacing_mm(sheet):
    """Per-side margins and per-axis gaps for ``sheet``, in millimetres."""
    return {
        "gap_x": sheet["gapXIn"] * MM_PER_INCH,
        "gap_y": sheet["gapYIn"] * MM_PER_INCH,
        "margin_top": sheet["marginTopIn"] * MM_PER_INCH,
        "margin_right": sheet["marginRightIn"] * MM_PER_INCH,
        "margin_bottom": sheet["marginBottomIn"] * MM_PER_INCH,
        "margin_left": sheet["marginLeftIn"] * MM_PER_INCH,
    }


def sheet_label_mm(sheet):
    """Catalog label size ``(width_mm, height_mm)``."""
    return (sheet["labelWidthIn"] * MM_PER_INCH, sheet["labelHeightIn"] * MM_PER_INCH)


def sheet_page_mm(sheet):
    """Page size ``(width_mm, height_mm)``."""
    return (sheet["pageWidthIn"] * MM_PER_INCH, sheet["pageHeightIn"] * MM_PER_INCH)


def format_sheets_list(sheets=None):
    """Plain-text catalog for ``--list-sheets``."""
    sheets = load_avery_sheets() if sheets is None else sheets
    lines = ["Avery sheets (inches). Pick one with --sheet <number>.", ""]
    for sheet in sheets:
        lines.append(sheet_option_label(sheet))
        lines.append(
            f"    {sheet['columns']} cols × {sheet['rows']} rows, "
            f"page {sheet['pageWidthIn']:g} × {sheet['pageHeightIn']:g} in, "
            f"margins T {sheet['marginTopIn']:g} R {sheet['marginRightIn']:g} "
            f"B {sheet['marginBottomIn']:g} L {sheet['marginLeftIn']:g}, "
            f"gap X {sheet['gapXIn']:g} Y {sheet['gapYIn']:g}, "
            f"{sheet['shape']}"
        )
    return "\n".join(lines)


def xml_escape_text(text):
    """Escape a string for use as XML text content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# --- template parsing -------------------------------------------------------

_G_TOKEN = re.compile(r"<g(?=[\s>])|</g>")
_ID_ATTR = re.compile(r'(?<=\s)id="([^"]*)"')


def find_labeled_group(svg_text, label):
    """Return (start, end) char offsets of the <g> whose opening tag carries
    ``inkscape:label="<label>"``, spanning the full element including nested
    groups. Raises ValueError if not found."""
    needle = f'inkscape:label="{label}"'
    label_pos = svg_text.find(needle)
    if label_pos == -1:
        raise ValueError(f'Could not find a <g> with inkscape:label="{label}" in the template.')

    # The label is an attribute of an opening tag; walk back to that tag's '<'.
    start = svg_text.rfind("<", 0, label_pos)
    if start == -1 or svg_text[start:start + 2] != "<g":
        raise ValueError(f'Malformed template: label "{label}" is not on a <g> element.')

    # Walk forward, tracking <g> nesting depth, to find the matching </g>.
    depth = 0
    pos = start
    while True:
        m = _G_TOKEN.search(svg_text, pos)
        if m is None:
            raise ValueError(f'Unbalanced <g> tags while extracting "{label}".')
        token = m.group()
        if token == "</g>":
            depth -= 1
            pos = m.end()
            if depth == 0:
                return start, pos
        else:  # an opening "<g"
            gt = svg_text.find(">", m.end())
            if gt == -1:
                raise ValueError("Malformed template: unterminated <g> tag.")
            self_closing = svg_text[gt - 1] == "/"
            if not self_closing:
                depth += 1
            pos = gt + 1


def find_tile_group(svg_text):
    """Find the first recognised repeating-tile group.

    Returns ``(start, end, label)`` for the ``<g>`` whose ``inkscape:label`` is
    one of ``TILE_LABELS``, or ``None`` when the template has no tile group (in
    which case the template is treated as a single per-record document)."""
    for label in TILE_LABELS:
        if f'inkscape:label="{label}"' in svg_text:
            try:
                start, end = find_labeled_group(svg_text, label)
            except ValueError:
                continue
            return start, end, label
    return None


def get_attr(tag_text, name):
    """Read a single attribute value out of an element's opening-tag text."""
    m = re.search(rf'{re.escape(name)}="([^"]*)"', tag_text)
    return m.group(1) if m else None


def parse_page(svg_text):
    """Inspect the root <svg> element.

    Returns ``(width_uu, height_uu, uu_per_mm)`` where the page size is given in
    the template's own user units (its viewBox), and ``uu_per_mm`` is how many of
    those user units make up one millimetre -- derived from the declared
    ``width``/``height`` so that physical spacing is honoured no matter what
    units or dimensions the template uses. ``uu_per_mm`` is ``None`` when the
    template gives no absolute physical size (then spacing falls back to being
    interpreted directly in user units)."""
    svg_start = svg_text.find("<svg")
    svg_open_end = svg_text.find(">", svg_start)
    svg_tag = svg_text[svg_start:svg_open_end]

    view_box = get_attr(svg_tag, "viewBox")
    if not view_box:
        raise ValueError("Template <svg> has no viewBox; cannot determine page size.")
    parts = view_box.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError(f"Unexpected viewBox value: {view_box!r}")
    vb_w, vb_h = float(parts[2]), float(parts[3])

    uu_per_mm = _scale_from_dimension(get_attr(svg_tag, "width"), vb_w)
    if uu_per_mm is None:
        uu_per_mm = _scale_from_dimension(get_attr(svg_tag, "height"), vb_h)

    return vb_w, vb_h, uu_per_mm


def _scale_from_dimension(dim_value, viewbox_extent):
    """User units per millimetre implied by a physical width/height attribute
    paired with the matching viewBox extent. Returns ``None`` if it can't be
    determined (missing, percentage, or unitless)."""
    value, unit = parse_length(dim_value)
    if value is None or not viewbox_extent:
        return None
    mm_per_unit = UNIT_TO_MM.get(unit)
    if mm_per_unit is None:
        return None
    physical_mm = value * mm_per_unit
    if physical_mm <= 0:
        return None
    return viewbox_extent / physical_mm


def parse_tag_geometry(nametag_xml, border_labels):
    """Return (width, height, stroke) of the border element, in the template's
    user units (the same space as the viewBox and transforms).

    ``border_labels`` is a label or list of candidate labels tried in order, so
    the cut outline can be labelled either ``<Tile> Border`` (e.g.
    ``Nametag Border``) or simply ``Border``.

    The border may be any of ``rect``, ``circle``, ``ellipse``, ``polygon`` or
    ``polyline``, so tiles can be any shape; the width/height returned are the
    shape's bounding box, which is what the grid tiles on."""
    if isinstance(border_labels, str):
        border_labels = [border_labels]
    border_pos = -1
    border_label = border_labels[0]
    for cand in border_labels:
        pos = nametag_xml.find(f'inkscape:label="{cand}"')
        if pos != -1:
            border_pos, border_label = pos, cand
            break
    if border_pos == -1:
        shown = " or ".join(f'"{lbl}"' for lbl in border_labels)
        raise ValueError(
            f"Could not find a border element with inkscape:label {shown} "
            "in the tile group."
        )
    el_start = nametag_xml.rfind("<", 0, border_pos)
    el_end = nametag_xml.find(">", border_pos)
    if el_start == -1 or el_end == -1:
        raise ValueError(f'Malformed "{border_label}" element in the template.')
    el = nametag_xml[el_start:el_end + 1]

    name_match = re.match(r"<\s*([A-Za-z0-9:]+)", el)
    tag_name = name_match.group(1).split(":")[-1].lower() if name_match else ""

    width, height = _shape_bbox(tag_name, el)
    if width is None or height is None:
        raise ValueError(
            f'Could not determine the size of the "{border_label}" '
            f"<{tag_name or '?'}> element."
        )

    stroke = 0.0
    style = get_attr(el, "style") or ""
    m = re.search(r"stroke-width:\s*([0-9.]+)", style)
    if m:
        stroke = float(m.group(1))
    elif get_attr(el, "stroke-width"):
        try:
            stroke = float(get_attr(el, "stroke-width"))
        except ValueError:
            stroke = 0.0
    return float(width), float(height), stroke


def _shape_bbox(tag_name, el):
    """Bounding-box (width, height) for a supported border shape, or (None, None)."""
    def num(attr):
        try:
            return float(get_attr(el, attr))
        except (TypeError, ValueError):
            return None

    if tag_name == "rect":
        return num("width"), num("height")
    if tag_name == "circle":
        r = num("r")
        return (2 * r, 2 * r) if r is not None else (None, None)
    if tag_name == "ellipse":
        rx, ry = num("rx"), num("ry")
        return (2 * rx, 2 * ry) if rx is not None and ry is not None else (None, None)
    if tag_name in ("polygon", "polyline"):
        points = get_attr(el, "points") or ""
        coords = [float(v) for v in re.findall(r"[-+]?[0-9]*\.?[0-9]+", points)]
        xs, ys = coords[0::2], coords[1::2]
        if xs and ys:
            return max(xs) - min(xs), max(ys) - min(ys)
    return None, None


# --- grid layout ------------------------------------------------------------

# User units. Keeps an exact die-cut fit (pitch * n + margins == page) from
# rounding down to one fewer row or column. Far smaller than a print dot.
_FIT_EPS = 1e-4


def _pick_spacing(specific, fallback):
    """Use ``specific`` when it was provided, otherwise the shared fallback.

    ``0`` is a real value (a flush gutter or a flush edge). Only ``None`` means
    "not set"."""
    return fallback if specific is None else specific


def resolve_grid_spacing(gap, margin, gap_x=None, gap_y=None,
                         margin_top=None, margin_right=None,
                         margin_bottom=None, margin_left=None):
    """Resolve per-axis gaps and per-side margins.

    ``gap`` applies to both axes unless ``gap_x`` or ``gap_y`` is set.
    ``margin`` applies to every side unless that side is set. All six numbers
    are in the same unit (millimetres at the CLI; user units in the layout).
    """
    return {
        "gap_x": _pick_spacing(gap_x, gap),
        "gap_y": _pick_spacing(gap_y, gap),
        "margin_top": _pick_spacing(margin_top, margin),
        "margin_right": _pick_spacing(margin_right, margin),
        "margin_bottom": _pick_spacing(margin_bottom, margin),
        "margin_left": _pick_spacing(margin_left, margin),
    }


def _slots(avail, size, pitch):
    """How many tiles of ``size`` fit in ``avail`` stepped by ``pitch``."""
    if pitch <= 0:
        return 1 if avail + _FIT_EPS >= size else 0
    if avail + _FIT_EPS < size:
        return 0
    return int((avail - size + _FIT_EPS) / pitch) + 1


def compute_grid(page_w, page_h, tag_w, tag_h, stroke, gap, margin,
                 gap_x=None, gap_y=None,
                 margin_top=None, margin_right=None,
                 margin_bottom=None, margin_left=None):
    """Compute how many columns/rows of tags fit on the page.

    ``gap`` is the space between tiles on both axes and ``margin`` is the
    inset on every side, matching the original single-value behaviour. Pass
    ``gap_x`` / ``gap_y`` or a side margin to override one axis or edge.
    """
    spacing = resolve_grid_spacing(
        gap, margin,
        gap_x=gap_x, gap_y=gap_y,
        margin_top=margin_top, margin_right=margin_right,
        margin_bottom=margin_bottom, margin_left=margin_left,
    )
    pitch_x = tag_w + spacing["gap_x"]
    pitch_y = tag_h + spacing["gap_y"]
    avail_w = page_w - stroke - spacing["margin_left"] - spacing["margin_right"]
    avail_h = page_h - stroke - spacing["margin_top"] - spacing["margin_bottom"]

    cols = max(_slots(avail_w, tag_w, pitch_x), 1)
    rows = max(_slots(avail_h, tag_h, pitch_y), 1)
    return cols, rows, pitch_x, pitch_y


# --- placeholder detection & name copy generation ---------------------------

def detect_placeholders(nametag_xml):
    """Return an ordered mapping of every distinct ``{{token}}`` found in the
    nametag markup to its normalised (lower-cased, stripped) field name. The
    raw token text -- braces and inner spacing included -- is the dict key, so
    substitution replaces exactly what appears in the template."""
    tokens = {}
    for m in PLACEHOLDER_RE.finditer(nametag_xml):
        raw = m.group(0)
        if raw not in tokens:
            tokens[raw] = m.group(1).strip().lower()
    return tokens


def make_tag_copy(nametag_xml, row, tokens, index, tx, ty, missing):
    """Return a positioned copy of the nametag group with every ``{{token}}``
    replaced by the matching value from ``row`` (a dict keyed by lower-cased
    column name). Tokens with no matching column are blanked and recorded in
    ``missing``."""
    body = nametag_xml
    for raw, field in tokens.items():
        if field in row:
            value = row[field]
        else:
            missing.add(field)
            value = ""
        body = body.replace(raw, xml_escape_text(value))
    # Make every id unique to this copy so the merged SVG stays valid.
    body = _ID_ATTR.sub(lambda m: f'id="{m.group(1)}__{index}"', body)
    return (
        f'<g id="nametag-{index}" '
        f'inkscape:label="Nametag {index + 1}" '
        f'transform="translate({fmt(tx)},{fmt(ty)})">'
        f"{body}</g>"
    )


# --- csv input --------------------------------------------------------------

def read_rows(csv_path):
    """Read a CSV with a header row into (fieldnames, rows). Each row is a dict
    keyed by lower-cased, stripped column name so it matches placeholder fields
    case-insensitively."""
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            row = {}
            for key, value in raw.items():
                if key is None:
                    continue
                row[key.strip().lower()] = (value or "").strip()
            # Skip fully blank rows.
            if any(row.values()):
                rows.append(row)
    return fieldnames, rows


# --- output assembly --------------------------------------------------------

def page_filename(output_path, page_number):
    if page_number == 1:
        return output_path
    stem, ext = os.path.splitext(output_path)
    return f"{stem}_{page_number}{ext}"


_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(value):
    """Turn an arbitrary field value into a safe file name (no extension)."""
    cleaned = _UNSAFE_FILENAME.sub("_", value or "").strip().rstrip(". ")
    return cleaned


def unique_name(base, used):
    """Return ``base`` (or ``base-2``, ``base-3`` ...) not already in ``used``,
    and record the result in ``used``."""
    name = base
    n = 2
    while name.lower() in used:
        name = f"{base}-{n}"
        n += 1
    used.add(name.lower())
    return name


def fullsheet_basename(row, name_fields, index, count):
    """File stem for one full-sheet export: sanitized fields, then the row number.

    ``index`` is the 0-based position among usable data rows. The row number is
    1-based and zero-padded to at least two digits (more when ``count`` needs
    it) so the files sort in row order. Two rows that share a name stay distinct
    because the row number differs; ``unique_name`` still breaks any leftover
    collision.
    """
    label = sanitize_filename(
        " - ".join(row.get(field, "") for field in name_fields if row.get(field, ""))
    )
    width = max(2, len(str(count)))
    return f"{label or 'row'}-{str(index + 1).zfill(width)}"


def match_fields(tokens, fieldnames):
    """Given detected placeholder tokens and CSV field names, return
    ``(template_fields, matched, unmatched, header_set)``."""
    template_fields = list(dict.fromkeys(tokens.values()))
    header_set = {f.strip().lower() for f in fieldnames}
    matched = [f for f in template_fields if f in header_set]
    unmatched = [f for f in template_fields if f not in header_set]
    return template_fields, matched, unmatched, header_set


def _length_mm(value):
    """Convert an SVG length to millimetres, or ``None`` when it has no physical size."""
    number, unit = parse_length(value)
    if number is None:
        return None
    factor = UNIT_TO_MM.get(unit)
    if factor is None:
        return None
    return number * factor


def _split_root_svg(svg_text):
    """Return ``(open_tag, inner_xml)`` for the root ``<svg>`` element."""
    start = svg_text.find("<svg")
    if start < 0:
        raise ValueError("Template has no <svg> element.")
    open_end = svg_text.find(">", start)
    if open_end < 0:
        raise ValueError("Template <svg> tag is not closed.")
    close = svg_text.rfind("</svg>")
    if close < open_end:
        raise ValueError("Template <svg> element is not closed.")
    return svg_text[start:open_end + 1], svg_text[open_end + 1:close]


_XMLNS_ATTR = re.compile(r'xmlns(?::[\w.-]+)?="[^"]*"')


def _xmlns_decl(open_tag):
    """Namespace declarations from the root tag, with the SVG default if missing."""
    found = _XMLNS_ATTR.findall(open_tag)
    if not any(item.startswith("xmlns=") for item in found):
        found.insert(0, 'xmlns="http://www.w3.org/2000/svg"')
    return " ".join(found)


def uniquify_ids(xml, index):
    """Suffix ids and the ``url(#id)`` / ``href="#id"`` references that point at them."""
    xml = _ID_ATTR.sub(lambda m: f'id="{m.group(1)}__{index}"', xml)
    xml = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{m.group(1).strip()}__{index})", xml)
    xml = re.sub(
        r'((?:xlink:)?href="#)([^"]+)(")',
        lambda m: f"{m.group(1)}{m.group(2)}__{index}{m.group(3)}",
        xml,
    )
    return xml


def _format_size_mm(width_mm, height_mm):
    return (
        f"{width_mm / MM_PER_INCH:.3f} in × {height_mm / MM_PER_INCH:.3f} in "
        f"({width_mm:.2f} mm × {height_mm:.2f} mm)"
    )


def size_mismatch_warning(template_mm, sheet_mm, sheet_name):
    """Warn when the artwork size and the chosen sheet's label size differ.

    Within ``SIZE_TOLERANCE_MM`` the two are treated as the same die. The
    artwork is never scaled to the catalog size.
    """
    if template_mm is None or sheet_mm is None:
        return None
    tw, th = template_mm
    sw, sh = sheet_mm
    if abs(tw - sw) <= SIZE_TOLERANCE_MM and abs(th - sh) <= SIZE_TOLERANCE_MM:
        return None
    name = sheet_name or "the chosen sheet"
    return (
        f"The template label is {_format_size_mm(tw, th)} but {name} is "
        f"{_format_size_mm(sw, sh)}. The artwork was not scaled."
    )


def overflow_warning(page_w, page_h, origin_x, origin_y, pitch_x, pitch_y,
                     label_w, label_h, cols, rows, uu_per_mm):
    """Warn when the last cell extends past the page. Nothing is clipped."""
    far_x = origin_x + (cols - 1) * pitch_x + label_w
    far_y = origin_y + (rows - 1) * pitch_y + label_h
    if uu_per_mm:
        mm_per_uu = 1.0 / uu_per_mm
        over_x = (far_x - page_w) * mm_per_uu
        over_y = (far_y - page_h) * mm_per_uu
        tol = SIZE_TOLERANCE_MM
        page_txt = f"{page_w * mm_per_uu:.1f} mm × {page_h * mm_per_uu:.1f} mm"
        reach = f"{far_x * mm_per_uu:.1f} mm × {far_y * mm_per_uu:.1f} mm"
    else:
        over_x = far_x - page_w
        over_y = far_y - page_h
        tol = 1e-3
        page_txt = f"{page_w:g} × {page_h:g} user units"
        reach = f"{far_x:g} × {far_y:g} user units"
    if over_x > tol or over_y > tol:
        return (
            f"This layout extends past the page (content reaches {reach} on a "
            f"{page_txt} sheet). Nothing was clipped; check the sheet, the label "
            "size, or the margins."
        )
    return None


def _positive_count(value, name):
    """``None`` when unset. Otherwise an integer of at least 1."""
    if value is None or value == "":
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number.")
    if count < 1:
        raise ValueError(f"{name} must be at least 1.")
    return count


def _no_physical_size_error():
    return ValueError(
        "This template has no repeating tile group, and its root <svg> has no "
        "physical width and height (such as 1.75in and 0.66in). Add those, or "
        "draw the label as a tile group labelled Nametag, Tile, or Cell."
    )


def generate(template_path, names_csv_path, output_path="output.svg", mode="auto",
             gap=2.0, margin=0.0, out_dir="output", name_field=None,
             gap_x=None, gap_y=None,
             margin_top=None, margin_bottom=None,
             margin_left=None, margin_right=None,
             columns=None, rows=None,
             page_width_mm=None, page_height_mm=None,
             sheet_label_mm=None, sheet_name=None):
    """Dispatch to the grid or individual generator.

    ``mode`` is ``"auto"`` (choose based on whether the template has a tile
    group), ``"grid"`` or ``"individual"``.

    In grid and fullsheet mode ``gap`` (mm) is the space between tiles on both
    axes and ``margin`` (mm) is the inset on every side. ``gap_x`` / ``gap_y``
    and ``margin_top`` / ``margin_bottom`` / ``margin_left`` /
    ``margin_right`` override one axis or side; leave them unset to keep the
    shared value. Fullsheet writes one SVG per row into ``out_dir``, named
    from ``name_field`` plus the row number.

    ``columns`` / ``rows`` fix the grid when a sheet was chosen. For a
    single-label template, ``page_width_mm`` / ``page_height_mm`` are that
    sheet's page (US Letter when omitted) and ``sheet_label_mm`` is the
    catalog label size used for pitch and the size-mismatch warning.
    """
    with open(template_path, encoding="utf-8") as fh:
        svg_text = fh.read()

    tile = find_tile_group(svg_text)
    resolved = mode
    if mode == "auto":
        resolved = "grid" if tile else "individual"

    layout_kwargs = dict(
        columns=columns, rows=rows,
        sheet_label_mm=sheet_label_mm, sheet_name=sheet_name,
    )
    if resolved == "grid":
        if tile is None:
            raise ValueError(
                "Grid mode needs a repeating tile group labelled one of "
                f"{', '.join(TILE_LABELS)} (e.g. inkscape:label=\"Nametag\"). "
                "A single-label SVG can be printed with --mode fullsheet."
            )
        return generate_grid(
            svg_text, tile, names_csv_path, output_path, gap, margin,
            gap_x=gap_x, gap_y=gap_y,
            margin_top=margin_top, margin_bottom=margin_bottom,
            margin_left=margin_left, margin_right=margin_right,
            **layout_kwargs,
        )
    if resolved == "fullsheet":
        if tile is None:
            return generate_label_sheets(
                svg_text, names_csv_path, out_dir, name_field,
                gap, margin,
                gap_x=gap_x, gap_y=gap_y,
                margin_top=margin_top, margin_bottom=margin_bottom,
                margin_left=margin_left, margin_right=margin_right,
                columns=columns, rows=rows,
                page_width_mm=page_width_mm, page_height_mm=page_height_mm,
                sheet_label_mm=sheet_label_mm, sheet_name=sheet_name,
            )
        return generate_fullsheet(
            svg_text, tile, names_csv_path, out_dir, name_field,
            gap, margin,
            gap_x=gap_x, gap_y=gap_y,
            margin_top=margin_top, margin_bottom=margin_bottom,
            margin_left=margin_left, margin_right=margin_right,
            **layout_kwargs,
        )
    return generate_individual(svg_text, names_csv_path, out_dir, name_field)


def _grid_layout(svg_text, tile, gap, margin, gap_x, gap_y,
                 margin_top, margin_bottom, margin_left, margin_right,
                 columns=None, rows=None, sheet_label_mm=None, sheet_name=None):
    """Shared sheet geometry for grid and full-sheet mode.

    Spacing arrives in millimetres and is converted into the template's user
    units so a millimetre is a real millimetre. If the template declares no
    absolute size, the values are used as user units. A single gap or margin
    still fills both axes or every side; an explicit per-axis gap or per-side
    margin replaces only that one.
    """
    start, end, tile_label = tile
    nametag_xml = svg_text[start:end]
    border_labels = [f"{tile_label} Border", "Border"]

    tokens = detect_placeholders(nametag_xml)
    if not tokens:
        raise ValueError(
            f"No {{{{placeholder}}}} tokens found inside the {tile_label} group. "
            "Add at least one, e.g. {{NAME}}."
        )

    page_w, page_h, uu_per_mm = parse_page(svg_text)
    tag_w, tag_h, stroke = parse_tag_geometry(nametag_xml, border_labels)

    scale = uu_per_mm if uu_per_mm else 1.0
    spacing_mm = resolve_grid_spacing(
        gap, margin,
        gap_x=gap_x, gap_y=gap_y,
        margin_top=margin_top, margin_right=margin_right,
        margin_bottom=margin_bottom, margin_left=margin_left,
    )
    spacing = {key: value * scale for key, value in spacing_mm.items()}

    cols, rows, pitch_x, pitch_y = compute_grid(
        page_w, page_h, tag_w, tag_h, stroke,
        spacing["gap_x"], spacing["margin_top"],
        gap_x=spacing["gap_x"], gap_y=spacing["gap_y"],
        margin_top=spacing["margin_top"],
        margin_right=spacing["margin_right"],
        margin_bottom=spacing["margin_bottom"],
        margin_left=spacing["margin_left"],
    )
    fixed_cols = _positive_count(columns, "columns")
    fixed_rows = _positive_count(rows, "rows")
    if fixed_cols is not None:
        cols = fixed_cols
    if fixed_rows is not None:
        rows = fixed_rows

    mm_per_uu = (1.0 / uu_per_mm) if uu_per_mm else None
    if mm_per_uu is not None:
        page_size_in = (page_w * mm_per_uu / MM_PER_INCH, page_h * mm_per_uu / MM_PER_INCH)
        tag_size_in = (tag_w * mm_per_uu / MM_PER_INCH, tag_h * mm_per_uu / MM_PER_INCH)
    else:
        page_size_in = None
        tag_size_in = None

    warnings = []
    overflow = overflow_warning(
        page_w, page_h, spacing["margin_left"], spacing["margin_top"],
        pitch_x, pitch_y, tag_w, tag_h, cols, rows, uu_per_mm,
    )
    if overflow:
        warnings.append(overflow)
    if sheet_label_mm and mm_per_uu is not None:
        mismatch = size_mismatch_warning(
            (tag_w * mm_per_uu, tag_h * mm_per_uu), sheet_label_mm, sheet_name,
        )
        if mismatch:
            warnings.append(mismatch)

    return {
        "prefix": svg_text[:start],
        "suffix": svg_text[end:],
        "nametag_xml": nametag_xml,
        "tile_label": tile_label,
        "tokens": tokens,
        "page_w": page_w,
        "page_h": page_h,
        "tag_w": tag_w,
        "tag_h": tag_h,
        "spacing_mm": spacing_mm,
        "spacing": spacing,
        "cols": cols,
        "rows": rows,
        "pitch_x": pitch_x,
        "pitch_y": pitch_y,
        "per_page": cols * rows,
        "page_size_in": page_size_in,
        "tag_size_in": tag_size_in,
        "warnings": warnings,
    }


def _placed_copies(layout, cell_rows, missing):
    """Tile ``cell_rows`` into the sheet, one translate() group per cell."""
    copies = []
    cols = layout["cols"]
    pitch_x = layout["pitch_x"]
    pitch_y = layout["pitch_y"]
    spacing = layout["spacing"]
    for i, data_row in enumerate(cell_rows):
        col = i % cols
        grid_row = i // cols
        tx = spacing["margin_left"] + col * pitch_x
        ty = spacing["margin_top"] + grid_row * pitch_y
        copies.append(make_tag_copy(
            layout["nametag_xml"], data_row, layout["tokens"], i, tx, ty, missing,
        ))
    return "".join(copies)


def _resolve_name_fields(name_field, matched, header_set, fieldnames):
    """Columns used to name per-row files. Same default as individual mode."""
    name_fields = [
        field.strip().lower()
        for field in (name_field or "").split(",")
        if field.strip()
    ]
    invalid_name_fields = [field for field in name_fields if field not in header_set]
    if invalid_name_fields:
        raise ValueError(
            f"--name-field contains unknown CSV column(s): {invalid_name_fields}. "
            f"Available columns: {fieldnames}."
        )
    if not name_fields:
        name_fields = ["name", "date"] if "name" in matched and "date" in matched else [matched[0]]
    return name_fields


def generate_grid(svg_text, tile, names_csv_path, output_path, gap=2.0, margin=0.0,
                  gap_x=None, gap_y=None,
                  margin_top=None, margin_bottom=None,
                  margin_left=None, margin_right=None,
                  columns=None, rows=None, sheet_label_mm=None, sheet_name=None):
    layout = _grid_layout(
        svg_text, tile, gap, margin, gap_x, gap_y,
        margin_top, margin_bottom, margin_left, margin_right,
        columns=columns, rows=rows,
        sheet_label_mm=sheet_label_mm, sheet_name=sheet_name,
    )
    tokens = layout["tokens"]
    per_page = layout["per_page"]

    fieldnames, data_rows = read_rows(names_csv_path)
    if not data_rows:
        raise ValueError(f"No data rows found in {names_csv_path}.")

    template_fields, matched, unmatched, _ = match_fields(tokens, fieldnames)
    if not matched:
        raise ValueError(
            f"CSV {names_csv_path} has no columns matching the template "
            f"placeholders {template_fields}. CSV columns: {fieldnames}."
        )

    missing = set()
    total_pages = (len(data_rows) + per_page - 1) // per_page
    written = []
    for page in range(total_pages):
        chunk = data_rows[page * per_page:(page + 1) * per_page]
        out_svg = layout["prefix"] + _placed_copies(layout, chunk, missing) + layout["suffix"]
        out_name = page_filename(output_path, page + 1)
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(out_svg)
        written.append((out_name, len(chunk)))

    return {
        "mode": "grid",
        "tile_label": layout["tile_label"],
        "fields": template_fields,
        "matched": matched,
        "unmatched": sorted(unmatched),
        "csv_columns": fieldnames,
        "page_size_uu": (layout["page_w"], layout["page_h"]),
        "tag_size_uu": (layout["tag_w"], layout["tag_h"]),
        "page_size_in": layout["page_size_in"],
        "tag_size_in": layout["tag_size_in"],
        "grid": (layout["cols"], layout["rows"]),
        "spacing_mm": layout["spacing_mm"],
        "per_page": per_page,
        "names": len(data_rows),
        "files": written,
        "warnings": layout["warnings"],
    }


def generate_fullsheet(svg_text, tile, names_csv_path, out_dir="output", name_field=None,
                       gap=2.0, margin=0.0, gap_x=None, gap_y=None,
                       margin_top=None, margin_bottom=None,
                       margin_left=None, margin_right=None,
                       columns=None, rows=None, sheet_label_mm=None, sheet_name=None):
    """Write one full sheet per CSV row, every cell a copy of that row.

    Placement uses the same margins, gaps and tile size as grid mode, so a
    sheet lines up with the mixed-label grid on the same die.
    """
    layout = _grid_layout(
        svg_text, tile, gap, margin, gap_x, gap_y,
        margin_top, margin_bottom, margin_left, margin_right,
        columns=columns, rows=rows,
        sheet_label_mm=sheet_label_mm, sheet_name=sheet_name,
    )
    tokens = layout["tokens"]
    per_page = layout["per_page"]

    fieldnames, data_rows = read_rows(names_csv_path)
    if not data_rows:
        raise ValueError(f"No data rows found in {names_csv_path}.")

    template_fields, matched, unmatched, header_set = match_fields(tokens, fieldnames)
    if not matched:
        raise ValueError(
            f"CSV {names_csv_path} has no columns matching the template "
            f"placeholders {template_fields}. CSV columns: {fieldnames}."
        )

    name_fields = _resolve_name_fields(name_field, matched, header_set, fieldnames)

    os.makedirs(out_dir, exist_ok=True)
    missing = set()
    used = set()
    written = []
    for i, data_row in enumerate(data_rows):
        copies = _placed_copies(layout, [data_row] * per_page, missing)
        out_svg = layout["prefix"] + copies + layout["suffix"]
        base = fullsheet_basename(data_row, name_fields, i, len(data_rows))
        out_name = os.path.join(out_dir, unique_name(base, used) + ".svg")
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(out_svg)
        written.append((out_name, per_page))

    return {
        "mode": "fullsheet",
        "tile_label": layout["tile_label"],
        "fields": template_fields,
        "matched": matched,
        "unmatched": sorted(unmatched),
        "csv_columns": fieldnames,
        "page_size_uu": (layout["page_w"], layout["page_h"]),
        "tag_size_uu": (layout["tag_w"], layout["tag_h"]),
        "page_size_in": layout["page_size_in"],
        "tag_size_in": layout["tag_size_in"],
        "grid": (layout["cols"], layout["rows"]),
        "spacing_mm": layout["spacing_mm"],
        "per_page": per_page,
        "name_field": ",".join(name_fields),
        "name_fields": name_fields,
        "out_dir": out_dir,
        "names": len(data_rows),
        "files": written,
        "warnings": layout["warnings"],
    }


def _viewbox_numbers(view_box):
    parts = (view_box or "").replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError(f"Unexpected viewBox value: {view_box!r}")
    return [float(part) for part in parts]


def _label_cell(inner_xml, tokens, row, index, tx, ty, label_w, label_h, view_box, missing):
    """One copy of a single-label template.

    A translate and scale keeps the template's own coordinates (so defs and
    styles still apply) and maps them onto the label's physical size. A group
    is used instead of a nested ``<svg>`` so the copy has the same size in an
    XML file and in the browser preview.
    """
    body = inner_xml
    for raw, field in tokens.items():
        if field in row:
            value = row[field]
        else:
            missing.add(field)
            value = ""
        body = body.replace(raw, xml_escape_text(value))
    body = uniquify_ids(body, index)
    vb_x, vb_y, vb_w, vb_h = _viewbox_numbers(view_box)
    if vb_w == 0 or vb_h == 0:
        raise ValueError("This template's viewBox has no area, so the label cannot be placed.")
    sx = label_w / vb_w
    sy = label_h / vb_h
    return (
        f'<g id="label-{index}" transform="translate({fmt(tx - vb_x * sx)},{fmt(ty - vb_y * sy)}) '
        f'scale({fmt(sx)},{fmt(sy)})">'
        f"{body}</g>"
    )


def _compose_label_page(cells):
    xmlns = cells["xmlns"]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg {xmlns} '
        f'width="{fmt(cells["page_w"])}mm" height="{fmt(cells["page_h"])}mm" '
        f'viewBox="0 0 {fmt(cells["page_w"])} {fmt(cells["page_h"])}">\n'
        f'{cells["body"]}\n'
        "</svg>\n"
    )


def generate_label_sheets(svg_text, names_csv_path, out_dir="output", name_field=None,
                          gap=2.0, margin=0.0, gap_x=None, gap_y=None,
                          margin_top=None, margin_bottom=None,
                          margin_left=None, margin_right=None,
                          columns=None, rows=None,
                          page_width_mm=None, page_height_mm=None,
                          sheet_label_mm=None, sheet_name=None):
    """Tile a single-label SVG (no tile group) onto a sheet, one file per row.

    The root ``<svg>`` is the label. Its width and height are the physical
    label size and are not scaled to the sheet's catalog size. Each copy is a
    scaled group so defs and styles keep the template's coordinates. With no
    sheet, the page is US Letter and the grid is however many labels fit.
    """
    open_tag, inner_xml = _split_root_svg(svg_text)
    label_w, label_h = _length_mm(get_attr(open_tag, "width")), _length_mm(get_attr(open_tag, "height"))
    if label_w is None or label_h is None or label_w <= 0 or label_h <= 0:
        raise _no_physical_size_error()
    view_box = get_attr(open_tag, "viewBox")
    if not view_box:
        raise ValueError(
            "This template's root <svg> has no viewBox, so the label cannot be placed on a sheet."
        )
    tokens = detect_placeholders(inner_xml)
    if not tokens:
        raise ValueError(
            "No {{placeholder}} tokens found in the template. Add at least one, e.g. {{LABEL}}."
        )

    page_w = LETTER_WIDTH_MM if page_width_mm is None else page_width_mm
    page_h = LETTER_HEIGHT_MM if page_height_mm is None else page_height_mm
    spacing_mm = resolve_grid_spacing(
        gap, margin,
        gap_x=gap_x, gap_y=gap_y,
        margin_top=margin_top, margin_right=margin_right,
        margin_bottom=margin_bottom, margin_left=margin_left,
    )
    # The page is drawn in millimetres, so user units and millimetres are the same.
    pitch_label_w = label_w
    pitch_label_h = label_h
    if sheet_label_mm is not None:
        pitch_label_w, pitch_label_h = sheet_label_mm
    pitch_x = pitch_label_w + spacing_mm["gap_x"]
    pitch_y = pitch_label_h + spacing_mm["gap_y"]

    fixed_cols = _positive_count(columns, "columns")
    fixed_rows = _positive_count(rows, "rows")
    fit_cols, fit_rows, _, _ = compute_grid(
        page_w, page_h, pitch_label_w, pitch_label_h, 0,
        spacing_mm["gap_x"], spacing_mm["margin_top"],
        gap_x=spacing_mm["gap_x"], gap_y=spacing_mm["gap_y"],
        margin_top=spacing_mm["margin_top"],
        margin_right=spacing_mm["margin_right"],
        margin_bottom=spacing_mm["margin_bottom"],
        margin_left=spacing_mm["margin_left"],
    )
    cols = fixed_cols if fixed_cols is not None else fit_cols
    rows = fixed_rows if fixed_rows is not None else fit_rows

    warnings = []
    overflow = overflow_warning(
        page_w, page_h, spacing_mm["margin_left"], spacing_mm["margin_top"],
        pitch_x, pitch_y, label_w, label_h, cols, rows, 1.0,
    )
    if overflow:
        warnings.append(overflow)
    mismatch = size_mismatch_warning((label_w, label_h), sheet_label_mm, sheet_name)
    if mismatch:
        warnings.append(mismatch)

    fieldnames, data_rows = read_rows(names_csv_path)
    if not data_rows:
        raise ValueError(f"No data rows found in {names_csv_path}.")
    template_fields, matched, unmatched, header_set = match_fields(tokens, fieldnames)
    if not matched:
        raise ValueError(
            f"CSV {names_csv_path} has no columns matching the template "
            f"placeholders {template_fields}. CSV columns: {fieldnames}."
        )
    name_fields = _resolve_name_fields(name_field, matched, header_set, fieldnames)

    xmlns = _xmlns_decl(open_tag)
    per_page = cols * rows
    os.makedirs(out_dir, exist_ok=True)
    missing = set()
    used = set()
    written = []
    for i, data_row in enumerate(data_rows):
        parts = []
        for n in range(per_page):
            col = n % cols
            grid_row = n // cols
            tx = spacing_mm["margin_left"] + col * pitch_x
            ty = spacing_mm["margin_top"] + grid_row * pitch_y
            parts.append(_label_cell(
                inner_xml, tokens, data_row, n, tx, ty,
                label_w, label_h, view_box, missing,
            ))
        page = _compose_label_page({
            "page_w": page_w, "page_h": page_h, "body": "\n".join(parts), "xmlns": xmlns,
        })
        base = fullsheet_basename(data_row, name_fields, i, len(data_rows))
        out_name = os.path.join(out_dir, unique_name(base, used) + ".svg")
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(page)
        written.append((out_name, per_page))

    return {
        "mode": "fullsheet",
        "tile_label": "label",
        "fields": template_fields,
        "matched": matched,
        "unmatched": sorted(unmatched),
        "csv_columns": fieldnames,
        "page_size_uu": (page_w, page_h),
        "tag_size_uu": (label_w, label_h),
        "page_size_in": (page_w / MM_PER_INCH, page_h / MM_PER_INCH),
        "tag_size_in": (label_w / MM_PER_INCH, label_h / MM_PER_INCH),
        "grid": (cols, rows),
        "spacing_mm": spacing_mm,
        "per_page": per_page,
        "name_fields": name_fields,
        "out_dir": out_dir,
        "names": len(data_rows),
        "files": written,
        "warnings": warnings,
    }


def generate_individual(svg_text, names_csv_path, out_dir="output", name_field=None):
    """Write one output SVG per CSV row: the whole template page with its
    ``{{token}}`` placeholders merged. The template is reproduced byte-for-byte
    apart from the substituted values."""
    tokens = detect_placeholders(svg_text)
    if not tokens:
        raise ValueError(
            "No {{placeholder}} tokens found in the template. "
            "Add at least one, e.g. {{NAME}}."
        )

    fieldnames, data_rows = read_rows(names_csv_path)
    if not data_rows:
        raise ValueError(f"No data rows found in {names_csv_path}.")

    template_fields, matched, unmatched, header_set = match_fields(tokens, fieldnames)
    if not matched:
        raise ValueError(
            f"CSV {names_csv_path} has no columns matching the template "
            f"placeholders {template_fields}. CSV columns: {fieldnames}."
        )

    # Use an explicit comma-separated field list when supplied. Otherwise,
    # certificates with both NAME and DATE use both; other templates retain
    # the first-matched-field default.
    name_fields = _resolve_name_fields(name_field, matched, header_set, fieldnames)

    os.makedirs(out_dir, exist_ok=True)
    missing = set()
    used = set()
    written = []
    for i, row in enumerate(data_rows):
        body = svg_text
        for raw, field in tokens.items():
            if field in row:
                value = row[field]
            else:
                missing.add(field)
                value = ""
            body = body.replace(raw, xml_escape_text(value))

        base = sanitize_filename(
            " - ".join(row.get(field, "") for field in name_fields if row.get(field, ""))
        ) or f"row-{i + 1}"
        out_name = os.path.join(out_dir, unique_name(base, used) + ".svg")
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(body)
        written.append((out_name, 1))

    return {
        "mode": "individual",
        "fields": template_fields,
        "matched": matched,
        "unmatched": sorted(unmatched),
        "csv_columns": fieldnames,
        "name_field": ",".join(name_fields),
        "name_fields": name_fields,
        "out_dir": out_dir,
        "names": len(data_rows),
        "files": written,
    }


def format_spacing_mm(spacing_mm):
    """Human-readable gap and margin text shared by the grid-like modes."""
    sp = spacing_mm
    if sp["gap_x"] == sp["gap_y"]:
        gap_txt = f"gap {sp['gap_x']:g} mm"
    else:
        gap_txt = f"gap-x {sp['gap_x']:g} mm, gap-y {sp['gap_y']:g} mm"
    sides = (sp["margin_top"], sp["margin_right"], sp["margin_bottom"], sp["margin_left"])
    if len(set(sides)) == 1:
        margin_txt = f"margin {sides[0]:g} mm"
    else:
        margin_txt = (
            f"margin T {sp['margin_top']:g} / R {sp['margin_right']:g} / "
            f"B {sp['margin_bottom']:g} / L {sp['margin_left']:g} mm"
        )
    return gap_txt, margin_txt


def _print_bed(result):
    if result["page_size_in"] and result["tag_size_in"]:
        pw, ph = result["page_size_in"]
        tw, th = result["tag_size_in"]
        print(f"Bed: {pw:.2f}in x {ph:.2f}in   Tile: {tw:.2f}in x {th:.2f}in")
    else:
        pw, ph = result["page_size_uu"]
        tw, th = result["tag_size_uu"]
        print(f"Bed: {pw:g} x {ph:g} (user units)   Tile: {tw:g} x {th:g} (user units)")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mail-merge rows from a CSV onto an SVG template. Either tile "
                    "a repeating nametag/label into a laser-ready grid, or emit "
                    "one full-page SVG per row (certificates, badges, ...)."
    )
    parser.add_argument("--template", default="template.svg", help="Template SVG (default: template.svg)")
    parser.add_argument("--names", default="names.csv", help="CSV of merge data (default: names.csv)")
    parser.add_argument("--mode", choices=("auto", "grid", "fullsheet", "individual"), default="auto",
                        help="Output layout: grid (tiled), fullsheet (one sheet of copies per row), "
                             "individual (one file per row), or auto-detect (default: auto)")
    parser.add_argument("--output", default="output.svg",
                        help="[grid] Output SVG; extra sheets get _2, _3 suffixes (default: output.svg)")
    parser.add_argument("--out-dir", default="output",
                        help="[individual, fullsheet] Directory for the per-row files (default: output)")
    parser.add_argument("--name-field", default=None,
                        help="[individual, fullsheet] CSV column(s), comma-separated, used to name each "
                             "output file. Full-sheet names also append the row number. "
                             "(default: NAME and DATE when both exist; otherwise the first matched field)")
    parser.add_argument("--sheet", "--preset", dest="sheet", default=None,
                        help="Avery product number, for example 5520 (alias --preset). "
                             "Sets the page, columns, rows, margins and gaps from the built-in library. "
                             "Explicit --gap / --margin flags override that sheet. See --list-sheets.")
    parser.add_argument("--list-sheets", action="store_true",
                        help="Print the built-in Avery sheet formats and exit.")
    parser.add_argument("--gap", type=float, default=None,
                        help="[grid, fullsheet] Gap between labels in mm, both axes "
                             "(default: 2.0, or the chosen sheet). "
                             "Overridden per axis by --gap-x / --gap-y.")
    parser.add_argument("--gap-x", type=float, default=None,
                        help="[grid] Horizontal gap between columns in mm (default: --gap)")
    parser.add_argument("--gap-y", type=float, default=None,
                        help="[grid] Vertical gap between rows in mm (default: --gap)")
    parser.add_argument("--margin", type=float, default=None,
                        help="[grid, fullsheet] Margin on every side in mm "
                             "(default: 0.0, or the chosen sheet). "
                             "Overridden per side by --margin-top/bottom/left/right.")
    parser.add_argument("--margin-top", type=float, default=None,
                        help="[grid] Top page margin in mm (default: --margin)")
    parser.add_argument("--margin-bottom", type=float, default=None,
                        help="[grid] Bottom page margin in mm (default: --margin)")
    parser.add_argument("--margin-left", type=float, default=None,
                        help="[grid] Left page margin in mm (default: --margin)")
    parser.add_argument("--margin-right", type=float, default=None,
                        help="[grid] Right page margin in mm (default: --margin)")
    args = parser.parse_args(argv)

    if args.list_sheets:
        try:
            print(format_sheets_list())
        except (ValueError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        sheet = find_sheet(args.sheet) if args.sheet else None
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    sheet_mm = sheet_spacing_mm(sheet) if sheet else None

    def _pick(specific, shared, sheet_value):
        if specific is not None:
            return specific
        if shared is not None:
            return shared
        if sheet_value is not None:
            return sheet_value
        return None

    page_width_mm = page_height_mm = None
    sheet_label = None
    sheet_name = None
    columns = rows = None
    if sheet is not None:
        page_width_mm, page_height_mm = sheet_page_mm(sheet)
        sheet_label = sheet_label_mm(sheet)
        sheet_name = "Avery " + "/".join(sheet["products"])
        columns = sheet["columns"]
        rows = sheet["rows"]

    try:
        result = generate(
            args.template, args.names, args.output, mode=args.mode,
            gap=2.0 if args.gap is None else args.gap,
            margin=0.0 if args.margin is None else args.margin,
            gap_x=_pick(args.gap_x, args.gap, sheet_mm["gap_x"] if sheet_mm else None),
            gap_y=_pick(args.gap_y, args.gap, sheet_mm["gap_y"] if sheet_mm else None),
            margin_top=_pick(args.margin_top, args.margin, sheet_mm["margin_top"] if sheet_mm else None),
            margin_bottom=_pick(args.margin_bottom, args.margin, sheet_mm["margin_bottom"] if sheet_mm else None),
            margin_left=_pick(args.margin_left, args.margin, sheet_mm["margin_left"] if sheet_mm else None),
            margin_right=_pick(args.margin_right, args.margin, sheet_mm["margin_right"] if sheet_mm else None),
            columns=columns, rows=rows,
            page_width_mm=page_width_mm, page_height_mm=page_height_mm,
            sheet_label_mm=sheet_label, sheet_name=sheet_name,
            out_dir=args.out_dir, name_field=args.name_field,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Fields: {', '.join(result['fields'])}  (matched CSV columns: {', '.join(result['matched'])})")
    if result["unmatched"]:
        print(f"WARNING: template fields with no CSV column (left blank): "
              f"{', '.join(result['unmatched'])}", file=sys.stderr)
    for warning in result.get("warnings") or []:
        print(f"WARNING: {warning}", file=sys.stderr)
    if sheet is not None and result["mode"] in ("grid", "fullsheet"):
        print(f"Sheet: {sheet_option_label(sheet)}")

    if result["mode"] == "grid":
        cols, rows = result["grid"]
        _print_bed(result)
        gap_txt, margin_txt = format_spacing_mm(result["spacing_mm"])
        print(f"Grid: {cols} cols x {rows} rows = {result['per_page']} per sheet")
        print(f"Spacing: {gap_txt}; {margin_txt}")
        print(f"Records: {result['names']}  ->  {len(result['files'])} sheet(s)")
        for name, count in result["files"]:
            print(f"  {name}: {count} tile(s)")
    elif result["mode"] == "fullsheet":
        cols, rows = result["grid"]
        _print_bed(result)
        gap_txt, margin_txt = format_spacing_mm(result["spacing_mm"])
        print(f"Mode: full sheet per label")
        print(f"Grid: {cols} cols x {rows} rows = {result['per_page']} copies per sheet")
        print(f"Spacing: {gap_txt}; {margin_txt}")
        print(f"File name from {' + '.join(result['name_fields'])} + row number")
        print(f"Records: {result['names']}  ->  {len(result['files'])} file(s) in {result['out_dir']}/")
        shown = result["files"][:10]
        for name, count in shown:
            print(f"  {name}: {count} tile(s)")
        if len(result["files"]) > len(shown):
            print(f"  ... and {len(result['files']) - len(shown)} more")
    else:
        print(f"Mode: individual  (file name from {' + '.join(result['name_fields'])})")
        print(f"Records: {result['names']}  ->  {len(result['files'])} file(s) in {result['out_dir']}/")
        shown = result["files"][:10]
        for name, _ in shown:
            print(f"  {name}")
        if len(result["files"]) > len(shown):
            print(f"  ... and {len(result['files']) - len(shown)} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
