import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const fields = require("../editor/preserve-fields.js");

const EXAMPLE = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="19.5in" height="11in" viewBox="0 0 495.3 279.4" version="1.1">
  <g id="nametag" inkscape:label="Nametag">
    <text x="44.45" y="36" font-family="sans-serif">{{NAME}}</text>
    <text x="44.45" y="49">{{ROLE}}</text>
    <rect id="badge-cut" inkscape:label="Nametag Border" x="0" y="0" width="88.9" height="57.15" style="fill:none;stroke:#ff0000;stroke-width:0.3"/>
  </g>
</svg>`;

const CERT = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="11in" height="8.5in" viewBox="0 0 279.4 215.9">
  <g inkscape:groupmode="layer" inkscape:label="Backdrop" style="display:none">
    <rect x="0" y="0" width="279.4" height="215.9"/>
  </g>
  <text>{{Name}}</text>
  <text>{{Position}}</text>
</svg>`;

function quotedAttr(svg, name) {
  const re = new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*=\\s*\"([^\"]*)\"", "g");
  const out = [];
  let m;
  while ((m = re.exec(svg))) out.push(m[1]);
  return out;
}

// Stand-in for SVG-Edit's sanitizer and root rewrite: Inkscape attributes and
// viewBox are dropped, data-* and placeholder text are kept.
function fakeEditor(svg) {
  let out = svg.replace(/\sxmlns:inkscape\s*=\s*("[^"]*"|'[^']*')/gi, "");
  out = out.replace(/\sinkscape:label\s*=\s*("[^"]*"|'[^']*')/gi, "");
  out = out.replace(/\sinkscape:groupmode\s*=\s*("[^"]*"|'[^']*')/gi, "");
  out = out.replace(/\sviewBox\s*=\s*("[^"]*"|'[^']*')/gi, "");
  out = out.replace(/\swidth\s*=\s*("[^"]*"|'[^']*')/gi, " width=\"495.3\"");
  out = out.replace(/\sheight\s*=\s*("[^"]*"|'[^']*')/gi, " height=\"279.4\"");
  return out;
}

test("placeholders and inkscape labels survive a simulated editor round trip", () => {
  const page = fields.capturePage(EXAMPLE);
  const prepared = fields.prepareTemplateForEditor(EXAMPLE);
  assert.deepEqual(fields.placeholderFields(prepared), ["name", "role"]);
  assert.ok(prepared.includes("data-mm-label=\"Nametag\""));
  assert.ok(prepared.includes("data-mm-label=\"Nametag%20Border\""));
  assert.ok(prepared.includes("{{NAME}}"));
  assert.ok(prepared.includes("{{ROLE}}"));

  const edited = fakeEditor(prepared);
  assert.equal(edited.includes("inkscape:label"), false);
  assert.ok(edited.includes("{{NAME}}"));

  const restored = fields.restoreTemplateFromEditor(edited, page, { w: 495.3, h: 279.4 });
  assert.deepEqual(quotedAttr(restored, "inkscape:label").sort(), ["Nametag", "Nametag Border"]);
  assert.deepEqual(fields.placeholderFields(restored), ["name", "role"]);
  assert.ok(restored.includes("{{NAME}}"));
  assert.ok(restored.includes("{{ROLE}}"));
  assert.ok(restored.includes("xmlns:inkscape=\"http://www.inkscape.org/namespaces/inkscape\""));
  assert.match(rootTag(restored), /width="19\.5in"/);
  assert.match(rootTag(restored), /height="11in"/);
  assert.match(rootTag(restored), /viewBox="0 0 495\.3 279\.4"/);
  assert.equal(restored.includes("data-mm-label"), false);
});

test("a changed editor page size is kept", () => {
  const page = fields.capturePage(EXAMPLE);
  const prepared = fields.prepareTemplateForEditor(EXAMPLE);
  let edited = fakeEditor(prepared);
  edited = edited.replace(/\swidth="495\.3"/, " width=\"100\"");
  edited = edited.replace(/\sheight="279\.4"/, " height=\"80\"");
  const restored = fields.restoreTemplateFromEditor(edited, page, { w: 100, h: 80 });
  assert.match(rootTag(restored), /viewBox="0 0 100 80"/);
  assert.match(rootTag(restored), /width="100"/);
  assert.equal(rootTag(restored).includes("19.5in"), false);
  assert.ok(restored.includes("{{NAME}}"));
});

test("backdrop layer label and group mode survive", () => {
  const page = fields.capturePage(CERT);
  const prepared = fields.prepareTemplateForEditor(CERT);
  assert.ok(prepared.includes("data-mm-groupmode=\"layer\""));
  assert.ok(prepared.includes("data-mm-label=\"Backdrop\""));
  const edited = fakeEditor(prepared)
    .replace(/\swidth="495\.3"/, " width=\"279.4\"")
    .replace(/\sheight="279\.4"/, " height=\"215.9\"");
  const restored = fields.restoreTemplateFromEditor(edited, page, { w: 279.4, h: 215.9 });
  assert.ok(restored.includes("inkscape:label=\"Backdrop\""));
  assert.ok(restored.includes("inkscape:groupmode=\"layer\""));
  assert.deepEqual(fields.placeholderFields(restored), ["name", "position"]);
  assert.match(rootTag(restored), /width="11in"/);
  assert.match(rootTag(restored), /height="8\.5in"/);
});

test("bundled template.svg markers survive the simulated editor", () => {
  const svg = fs.readFileSync(new URL("../template.svg", import.meta.url), "utf8");
  const page = fields.capturePage(svg);
  const before = quotedAttr(svg, "inkscape:label").sort();
  assert.ok(before.includes("Nametag"));
  assert.ok(before.includes("Nametag Border"));
  assert.deepEqual(fields.placeholderFields(svg), ["name"]);

  const prepared = fields.prepareTemplateForEditor(svg);
  assert.equal(fields.placeholderFields(prepared).join(), "name");
  const restored = fields.restoreTemplateFromEditor(fakeEditor(prepared), page, {
    w: page.viewBox.split(/\s+/)[2],
    h: page.viewBox.split(/\s+/)[3],
  });
  assert.deepEqual(quotedAttr(restored, "inkscape:label").sort(), before);
  assert.ok(restored.includes("{{NAME}}"));
  assert.match(rootTag(restored), /width="19\.5in"/);
  assert.match(rootTag(restored), /height="11in"/);
});

test("a label with an escaped quote round-trips", () => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="10px" height="10px" viewBox="0 0 10 10">
    <g inkscape:label="Say &quot;Hi&quot;"><text>{{ First Name }}</text></g>
  </svg>`;
  const page = fields.capturePage(svg);
  const restored = fields.restoreTemplateFromEditor(
    fakeEditor(fields.prepareTemplateForEditor(svg)).replace(/width="495\.3"/, " width=\"10\"").replace(/height="279\.4"/, " height=\"10\""),
    page,
    { w: 10, h: 10 }
  );
  assert.ok(restored.includes("inkscape:label=\"Say &quot;Hi&quot;\""));
  assert.deepEqual(fields.placeholderFields(restored), ["first name"]);
});

function rootTag(svg) {
  const m = svg.match(/<svg\b[^>]*>/i);
  return m ? m[0] : "";
}
