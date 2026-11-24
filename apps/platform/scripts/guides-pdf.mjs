// Builds the guide PDFs (PR-018) from src/lib/guides.ts and the screenshots in public/guides/.
// Usage: pnpm guides:pdf   (refresh screenshots first with GUIDE_SHOTS=1, see e2e/guide-screenshots.spec.ts)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

import { GUIDES } from "../src/lib/guides.ts";

const PUBLIC = fileURLToPath(new URL("../public", import.meta.url));
const EDITION = new Date().toLocaleDateString("en-GB", { month: "long", year: "numeric" });

const esc = (s) =>
  s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

function image(img) {
  const data = readFileSync(`${PUBLIC}${img.src}`).toString("base64");
  const caption = img.caption ? `<figcaption>${esc(img.caption)}</figcaption>` : "";
  return `<figure><img src="data:image/png;base64,${data}" alt="${esc(img.alt)}">${caption}</figure>`;
}

function section(s, i) {
  return `<section>
    <h2><span class="n">${i + 1}</span>${esc(s.title)}</h2>
    ${s.audience ? `<p class="audience">For ${esc(s.audience.toLowerCase())}</p>` : ""}
    ${s.intro ? `<p>${esc(s.intro)}</p>` : ""}
    ${s.steps ? `<ol>${s.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
    ${s.points ? `<ul>${s.points.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${s.tip ? `<p class="tip"><strong>Tip:</strong> ${esc(s.tip)}</p>` : ""}
    ${s.image ? image(s.image) : ""}
  </section>`;
}

function html(guide) {
  const contents = guide.sections
    .map((s, i) => `<li><span class="n">${i + 1}</span>${esc(s.title)}</li>`)
    .join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(guide.title)}</title>
<style>
  @page { size: A4; margin: 18mm 16mm 20mm; }
  * { box-sizing: border-box; }
  body { font: 10.5pt/1.55 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1a1a1a; margin: 0; }
  .cover { height: 245mm; display: flex; flex-direction: column; justify-content: space-between; page-break-after: always; }
  .brand { font-weight: 700; letter-spacing: .02em; font-size: 13pt; display: flex; align-items: center; gap: 8px; }
  .mark { width: 18px; height: 18px; border: 4px solid #f26b1d; border-right-color: transparent; border-bottom-color: transparent; }
  .eyebrow { font: 600 8pt/1 ui-monospace, Menlo, monospace; letter-spacing: .2em; text-transform: uppercase; color: #f26b1d; }
  h1 { font-size: 30pt; line-height: 1.1; font-weight: 400; letter-spacing: -.02em; margin: 12px 0 14px; }
  .summary { font-size: 12pt; color: #444; max-width: 140mm; }
  .contents { list-style: none; padding: 0; margin: 28px 0 0; columns: 2; column-gap: 10mm; }
  .contents li { padding: 3px 0; break-inside: avoid; }
  .n { display: inline-block; min-width: 22px; font: 600 9pt ui-monospace, Menlo, monospace; color: #f26b1d; }
  .edition { color: #777; font-size: 9pt; }
  section { break-inside: auto; margin: 0 0 9mm; }
  h2 { font-size: 15pt; font-weight: 500; margin: 0 0 6px; break-after: avoid; border-top: 1px solid #e6e6e6; padding-top: 5mm; }
  .audience { font: 600 7.5pt ui-monospace, Menlo, monospace; letter-spacing: .14em; text-transform: uppercase; color: #777; margin: 0 0 6px; }
  ol, ul { padding-left: 18px; margin: 6px 0; }
  li { margin: 3px 0; }
  ol li::marker { color: #f26b1d; font-weight: 600; }
  .tip { background: #fff4ec; border: 1px solid #ffd8bf; border-radius: 6px; padding: 7px 10px; }
  figure { margin: 8px 0 0; break-inside: avoid; }
  img { width: 100%; border: 1px solid #ddd; border-radius: 6px; }
  figcaption { color: #777; font-size: 8.5pt; margin-top: 4px; }
</style></head><body>
<div class="cover">
  <div class="brand"><span class="mark"></span>Onyx</div>
  <div>
    <p class="eyebrow">Guide</p>
    <h1>${esc(guide.title)}</h1>
    <p class="summary">${esc(guide.summary)}</p>
    <ol class="contents">${contents}</ol>
  </div>
  <p class="edition">Onyx Platform · app.onyx.mt · ${esc(EDITION)}</p>
</div>
${guide.sections.map(section).join("\n")}
</body></html>`;
}

const browser = await chromium.launch(
  process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {},
);
const page = await browser.newPage();
for (const guide of GUIDES) {
  await page.setContent(html(guide), { waitUntil: "load" });
  const path = `${PUBLIC}/guides/onyx-${guide.slug}-guide.pdf`;
  await page.pdf({
    path,
    format: "A4",
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: `<div style="font: 7.5pt Helvetica, Arial; color: #888; width: 100%; padding: 0 16mm; display: flex; justify-content: space-between;"><span>${esc(guide.title)}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  });
  console.log("wrote", path);
}
await browser.close();
