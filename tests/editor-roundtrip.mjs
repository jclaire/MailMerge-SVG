/**
 * Load the app in headless Chrome, edit the example template in SVG-Edit,
 * and check that merge placeholders and Inkscape tile labels come back.
 *
 *   npm install --no-save puppeteer-core
 *   node tests/editor-roundtrip.mjs
 *
 * Uses the system Chrome (CHROME_PATH or /usr/bin/google-chrome).
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const chromePath = process.env.CHROME_PATH || "/usr/bin/google-chrome";
const shotDir = process.env.SCREENSHOT_DIR || "/opt/cursor/artifacts";

const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".png": "image/png",
  ".gif": "image/gif",
  ".txt": "text/plain; charset=utf-8",
};

function startServer() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    let rel = decodeURIComponent(url.pathname);
    if (rel.endsWith("/")) rel += "index.html";
    const file = path.normalize(path.join(root, rel));
    if (!file.startsWith(root)) {
      res.writeHead(403).end("forbidden");
      return;
    }
    fs.readFile(file, (err, buf) => {
      if (err) {
        res.writeHead(404).end("not found");
        return;
      }
      res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
      res.end(buf);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

async function loadPuppeteer() {
  const require = createRequire(import.meta.url);
  const spec = process.env.PUPPETEER_PATH || "puppeteer-core";
  try {
    if (spec.endsWith(".js")) return require(spec);
    return require(spec);
  } catch (err) {
    try {
      const href = spec.startsWith("file:") ? spec : pathToFileURL(spec).href;
      return await import(href);
    } catch (err2) {
      console.error("puppeteer-core is not installed. Run: npm install --no-save puppeteer-core");
      console.error(err2 && err2.message ? err2.message : err2);
      process.exit(1);
    }
  }
}

async function main() {
  const puppeteer = await loadPuppeteer();

  fs.mkdirSync(shotDir, { recursive: true });
  const server = await startServer();
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}/`;
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  const failed = [];
  const logs = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") logs.push(msg.text());
  });
  page.on("requestfailed", (req) => failed.push(req.url() + " " + (req.failure() && req.failure().errorText)));
  page.on("response", (res) => {
    if (res.status() >= 400) failed.push(res.status() + " " + res.url());
  });
  await page.setViewport({ width: 1440, height: 900 });

  try {
    await page.goto(base, { waitUntil: "networkidle0", timeout: 30000 });
    await page.click("#exampleBtn");
    await page.waitForSelector("#info", { timeout: 5000 });
    const before = await page.$eval("#info", (el) => el.innerText);
    assert(before.includes("19.50"), "example grid should report a 19.50in bed before editing; got: " + before);
    assert(/5\s*×\s*4/.test(before) || before.includes("5 ×"), "example should still tile a grid; got: " + before);

    await page.evaluate(() => {
      const orig = URL.createObjectURL;
      window.__downloads = [];
      URL.createObjectURL = function (blob) {
        window.__downloads.push(blob);
        return orig.call(this, blob);
      };
    });

    await page.click("#editTplBtn");
    await page.waitForFunction(() => {
      const btn = document.querySelector("#editorApply");
      return btn && !btn.disabled;
    }, { timeout: 30000 });

    const frame = page.frames().find((f) => f.url().includes("mailmerge.html"));
    assert(frame, "SVG-Edit frame did not load. Failures: " + failed.join("\n"));
    await frame.waitForSelector("#svgcanvas", { timeout: 10000 });

    const edited = await frame.evaluate(() => {
      const ed = window.svgEditor;
      const root = ed.svgCanvas.getSvgContent();
      const texts = [...root.querySelectorAll("text")].map((t) => t.textContent);
      const name = [...root.querySelectorAll("text")].find((t) => (t.textContent || "").includes("{{NAME}}"));
      if (!name) return { ok: false, texts };
      ed.svgCanvas.selectOnly([name], true);
      ed.svgCanvas.changeSelectedAttribute("fill", "#112233", [name]);
      const raw = ed.svgCanvas.getSvgString();
      const labels = [...root.querySelectorAll("[data-mm-label]")].map((el) => el.getAttribute("data-mm-label"));
      return {
        ok: true,
        texts,
        labels,
        rawHasName: raw.includes("{{NAME}}"),
        rawHasRole: raw.includes("{{ROLE}}"),
        rawHasInkscape: raw.includes("inkscape:label"),
        extensions: ed.configObj.curConfig.extensions,
      };
    });
    assert(edited.ok, "editor lost {{NAME}} text. texts=" + JSON.stringify(edited.texts));
    assert(edited.rawHasName && edited.rawHasRole, "editor SVG string dropped placeholders: " + JSON.stringify(edited));
    assert(edited.labels.includes("Nametag") && edited.labels.includes("Nametag%20Border"),
      "data-mm-label markers missing in the editor: " + JSON.stringify(edited.labels));
    assert(!edited.extensions.includes("ext-storage"), "storage extension should stay unloaded");

    const shot = path.join(shotDir, "editor-in-app.png");
    await page.screenshot({ path: shot });

    await page.click("#editorDownload");
    await page.waitForFunction(() => window.__downloads && window.__downloads.length > 0);
    const downloaded = await page.evaluate(async () => window.__downloads[0].text());
    assert(downloaded.includes("{{NAME}}") && downloaded.includes("{{ROLE}}"), "download dropped placeholders");
    assert(downloaded.includes('inkscape:label="Nametag"'), "download did not restore the tile label");
    assert(downloaded.includes('inkscape:label="Nametag Border"'), "download did not restore the border label");
    assert(downloaded.includes('width="19.5in"'), "download did not keep the page width: " + (downloaded.match(/<svg\b[^>]*>/i) || [""])[0]);
    assert(downloaded.includes("#112233"), "download did not keep the fill edit");
    assert(!downloaded.includes("data-mm-label"), "download still has temporary data-mm-label attributes");

    await page.click("#editorApply");
    await page.waitForSelector("#info", { timeout: 5000 });
    const after = await page.$eval("#info", (el) => el.innerText);
    const preview = await page.$eval("#stage", (el) => el.innerText + "\n" + el.innerHTML);
    assert(after.includes("19.50"), "bed size changed after apply: " + after);
    assert(preview.includes("Sally Joe"), "merged preview lost the first row: " + preview.slice(0, 500));
    assert(!preview.includes("{{NAME}}"), "merged preview still shows the placeholder");
    assert(preview.includes("#112233"), "applied template lost the color edit");

    await page.$eval("#marginLeft", (el) => { el.value = "4.7625"; el.dispatchEvent(new Event("input")); });
    await page.$eval("#marginTop", (el) => { el.value = "12.7"; el.dispatchEvent(new Event("input")); });
    await page.$eval("#gapX", (el) => { el.value = "3.175"; el.dispatchEvent(new Event("input")); });
    await page.$eval("#gapY", (el) => { el.value = "0"; el.dispatchEvent(new Event("input")); });
    const spaced = await page.$eval("#stage", (el) => el.innerHTML);
    const spacingInfo = await page.$eval("#info", (el) => el.innerText);
    assert(spaced.includes("translate(4.7625,12.7)"), "per-side margins did not place the first tile: " + spacingInfo + "\n" + spaced.slice(0, 400));
    assert(spacingInfo.includes("4.7625") && spacingInfo.includes("12.7") && spacingInfo.includes("3.175"),
      "spacing readout changed: " + spacingInfo);

    await page.select("#mode", "individual");
    await page.click("#exampleBtn");
    await page.click("#editTplBtn");
    await page.waitForFunction(() => {
      const btn = document.querySelector("#editorApply");
      return btn && !btn.disabled;
    }, { timeout: 30000 });
    const certFrame = page.frames().find((f) => f.url().includes("mailmerge.html"));
    const cert = await certFrame.evaluate(() => {
      const root = window.svgEditor.svgCanvas.getSvgContent();
      const texts = [...root.querySelectorAll("text")].map((t) => t.textContent);
      return {
        texts,
        hasName: texts.some((t) => t.includes("{{Name}}")),
        hasPosition: texts.some((t) => t.includes("{{Position}}")),
        backdrop: [...root.querySelectorAll("[data-mm-label]")].map((el) => el.getAttribute("data-mm-label")),
      };
    });
    assert(cert.hasName && cert.hasPosition, "certificate placeholders missing: " + JSON.stringify(cert));
    assert(cert.backdrop.includes("Backdrop"), "backdrop label missing: " + JSON.stringify(cert.backdrop));
    await page.click("#editorApply");
    await page.waitForFunction(() => document.querySelector("#info") && document.querySelector("#info").innerText.includes("Individual"));
    const certPreview = await page.$eval("#stage", (el) => el.innerText);
    const backdropVisible = await page.$eval("#backdropOpts", (el) => el.style.display !== "none");
    assert(certPreview.includes("John Doe"), "certificate merge lost the name: " + certPreview);
    assert(!certPreview.includes("{{Name}}"), "certificate preview still shows the placeholder");
    assert(backdropVisible, "backdrop layer label did not survive, so the preview toggle is hidden");

    await page.evaluate(async () => {
      const text = await (await fetch("template.svg")).text();
      const file = new File([text], "template.svg", { type: "image/svg+xml" });
      const dt = new DataTransfer();
      dt.items.add(file);
      const input = document.querySelector("#tplInput");
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.waitForFunction(() => {
      const status = document.querySelector("#editorStatus");
      const open = !document.querySelector("#editorOverlay").hidden;
      return !open && document.querySelector("#tplName").textContent.includes("template.svg");
    }, { timeout: 10000 });
    await page.click("#editTplBtn");
    await page.waitForFunction(() => {
      const btn = document.querySelector("#editorApply");
      return btn && !btn.disabled;
    }, { timeout: 30000 });
    const realFrame = page.frames().find((f) => f.url().includes("mailmerge.html"));
    const real = await realFrame.evaluate(() => {
      const raw = window.svgEditor.svgCanvas.getSvgString();
      return {
        hasName: raw.includes("{{NAME}}"),
        labels: [...window.svgEditor.svgCanvas.getSvgContent().querySelectorAll("[data-mm-label]")].map((el) => el.getAttribute("data-mm-label")),
      };
    });
    assert(real.hasName, "bundled template lost {{NAME}} inside SVG-Edit");
    assert(real.labels.includes("Nametag") && real.labels.includes("Nametag%20Border"),
      "bundled template labels missing in the editor: " + JSON.stringify(real.labels));
    await page.evaluate(() => { if (window.__downloads) window.__downloads.length = 0; });
    await page.click("#editorDownload");
    await page.waitForFunction(() => window.__downloads && window.__downloads.length > 0);
    const realDownload = await page.evaluate(async () => window.__downloads[0].text());
    assert(realDownload.includes("{{NAME}}"), "bundled template download lost {{NAME}}");
    assert(realDownload.includes('inkscape:label="Nametag"'), "bundled template download lost the tile label");
    assert(realDownload.includes('inkscape:label="Nametag Border"'), "bundled template download lost the border label");
    assert(realDownload.includes('width="19.5in"'), "bundled template download lost physical page width");
    await page.click("#editorCancel");

    const bad = failed.filter((u) => !u.includes("favicon"));
    if (bad.length) console.log("non-fatal request issues:\n" + bad.join("\n"));
    console.log("editor round-trip ok");
    console.log("screenshot " + shot);
  } catch (err) {
    const dump = path.join(shotDir, "editor-failure.png");
    try { await page.screenshot({ path: dump }); } catch (e) { /* page may be closed */ }
    console.error(err && err.stack ? err.stack : err);
    console.error("status: " + await page.$eval("#editorStatus", (el) => el.textContent).catch(() => ""));
    console.error("failed requests:\n" + failed.join("\n"));
    console.error("console:\n" + logs.slice(-40).join("\n"));
    process.exitCode = 1;
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main();
