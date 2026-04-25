#!/usr/bin/env node
/**
 * Copy specs from docs/{_design,_end-user,_developer}/ into Starlight content.
 * Underscore-prefixed folders are authoring layout; published routes stay /design/, /end-user/, …
 * Sidebar order is defined in astro.config.mjs (explicit items), not by filename.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const docsDir = path.resolve(__dirname, "..");
const contentDocs = path.join(docsDir, "src/content/docs");

const FILE_BASE =
  process.env.DOCS_GITHUB_FILE_BASE || "https://github.com/AstrocyteAI/synapse/blob/main";

/** Authoring folder (under docs/) → URL path segment (no underscore). */
const SOURCE_TO_PUBLIC = {
  _design: "design",
  "_end-user": "end-user",
  _developer: "developer",
};

const DOC_SOURCE_DIRS = new Set(Object.keys(SOURCE_TO_PUBLIC));

function publicSectionFromSourceDir(sourceDir) {
  return SOURCE_TO_PUBLIC[sourceDir] ?? sourceDir;
}

function escapeTitle(s) {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function stripFirstH1(md) {
  return md.replace(/^#\s+.+\n+/, "");
}

function repoLinksToGitHub(content) {
  return content.replace(/\]\((\.\.\/[^)]+)\)/g, (full, rel) => {
    const clean = rel.replace(/^\.\.\//, "");
    const firstSegment = clean.split("/")[0];
    if (DOC_SOURCE_DIRS.has(firstSegment)) return full;
    return `](${FILE_BASE}/${clean})`;
  });
}

function docsMarkdownLinksToRoutes(content, sourceFileAbs, destFileAbs) {
  return content.replace(/\]\((\.\.?\/[^)]*\.md)\)/g, (full, href) => {
    const abs = path.resolve(path.dirname(sourceFileAbs), href);
    const rel = path.relative(docsDir, abs);
    if (rel.startsWith("..") || path.isAbsolute(rel)) return full;
    const norm = rel.replace(/\\/g, "/");
    const segments = norm.split("/").filter(Boolean);
    if (segments.length < 2) return full;
    const sourceSection = segments[0];
    const file = segments[segments.length - 1];
    if (!file.endsWith(".md")) return full;
    if (!DOC_SOURCE_DIRS.has(sourceSection)) return full;
    const slug = file.replace(/\.md$/, "");
    const targetSection = publicSectionFromSourceDir(sourceSection);
    const targetSubDir = segments.length > 2 ? segments.slice(1, -1).join("/") : "";
    const targetRoute = targetSubDir
      ? `${targetSection}/${targetSubDir}/${slug}`
      : `${targetSection}/${slug}`;
    const destDir = destFileAbs.replace(/\.mdx?$/, "");
    const targetFull = path.join(contentDocs, targetRoute);
    const relPath = path.relative(destDir, targetFull).replace(/\\/g, "/");
    return `](${relPath}/)`;
  });
}

const PUBLIC_SECTIONS = new Set(["design", "end-user", "developer", "introduction"]);

function rootRelativeToRelative(content, destFileAbs) {
  return content.replace(/\]\(\/([\w-]+(?:\/[^)]*)?)\)/g, (full, route) => {
    const topSegment = route.split("/")[0];
    if (!PUBLIC_SECTIONS.has(topSegment)) return full;
    const cleanRoute = route.replace(/\/$/, "");
    const destDir = destFileAbs.replace(/\.mdx?$/, "");
    const targetFull = path.join(contentDocs, cleanRoute);
    const relPath = path.relative(destDir, targetFull).replace(/\\/g, "/");
    return `](${relPath}/)`;
  });
}

function transformBody(content, sourceFileAbs, destFileAbs) {
  let result = repoLinksToGitHub(content);
  result = docsMarkdownLinksToRoutes(result, sourceFileAbs, destFileAbs);
  result = rootRelativeToRelative(result, destFileAbs);
  return result;
}

function extractTitle(md) {
  const m = md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : "Untitled";
}

function ensureFrontmatter(raw, titleFallback, sourceFileAbs, topicId, destFileAbs) {
  const m = raw.match(/^#\s+(.+)$/m);
  const title = m ? m[1].trim() : titleFallback;
  const bodyMd = m ? stripFirstH1(raw) : raw;
  const body = transformBody(bodyMd, sourceFileAbs, destFileAbs);
  const fm = `---\ntitle: "${escapeTitle(title)}"\ndraft: false\ntopic: ${topicId}\n---\n\n`;
  return fm + body;
}

function writeIfChanged(dest, data) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  if (fs.existsSync(dest) && fs.readFileSync(dest, "utf8") === data) return;
  fs.writeFileSync(dest, data);
}

function rmGeneratedDirs() {
  for (const d of ["design", "end-user", "developer"]) {
    const p = path.join(contentDocs, d);
    if (fs.existsSync(p)) fs.rmSync(p, { recursive: true, force: true });
  }
}

function copyAllMdFromSourceSection(sourceDirName, subDir = "") {
  const srcDir = path.join(docsDir, sourceDirName, subDir);
  const destSection = publicSectionFromSourceDir(sourceDirName);
  if (!fs.existsSync(srcDir)) return;
  for (const ent of fs.readdirSync(srcDir, { withFileTypes: true })) {
    if (ent.isDirectory()) {
      copyAllMdFromSourceSection(sourceDirName, path.join(subDir, ent.name));
      continue;
    }
    const isMd = ent.isFile() && ent.name.endsWith(".md");
    const isMdx = ent.isFile() && ent.name.endsWith(".mdx");
    if (!isMd && !isMdx) continue;
    const srcPath = path.join(srcDir, ent.name);
    const raw = fs.readFileSync(srcPath, "utf8");
    const destDir = subDir
      ? path.join(contentDocs, destSection, subDir)
      : path.join(contentDocs, destSection);
    const destFile = path.join(destDir, ent.name);
    if (isMdx) {
      writeIfChanged(destFile, raw);
      continue;
    }
    let fb = extractTitle(raw);
    if (fb === "Untitled") fb = ent.name.replace(/\.md$/, "").replace(/-/g, " ");
    const body = ensureFrontmatter(raw, fb, srcPath, destSection, destFile);
    writeIfChanged(destFile, body);
  }
}

rmGeneratedDirs();

for (const src of ["_design", "_end-user", "_developer"]) {
  copyAllMdFromSourceSection(src);
}

console.log("sync-docs: _design→design, _end-user→end-user, _developer→developer");
