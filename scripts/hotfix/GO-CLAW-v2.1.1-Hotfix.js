"use strict";

const fs = require("fs");
const path = require("path");
const { TextDecoder } = require("util");

const builtIns = new Set([
  "marketing-growth",
  "content-production",
  "data-processing",
  "business-analysis",
]);

function readJson(file) {
  const bytes = fs.readFileSync(file);
  const encodings = bytes[0] === 0xff && bytes[1] === 0xfe
    ? ["utf-16le", "utf-8", "gb18030", "utf-16be"]
    : bytes[0] === 0xfe && bytes[1] === 0xff
      ? ["utf-16be", "utf-8", "gb18030", "utf-16le"]
      : ["utf-8", "gb18030", "utf-16le", "utf-16be"];
  let lastError;
  for (const encoding of encodings) {
    try {
      const text = new TextDecoder(encoding, { fatal: true })
        .decode(bytes)
        .replace(/^\uFEFF/, "");
      return JSON.parse(text);
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`Cannot parse JSON ${file}: ${lastError.message}`);
}

function isChild(candidate, parent) {
  const rel = path.relative(path.resolve(parent), path.resolve(candidate));
  return rel !== "" && !rel.startsWith("..") && !path.isAbsolute(rel);
}

function loadConfig(root) {
  const configPath = path.join(root, "data", "config.json");
  return { configPath, config: readJson(configPath) };
}

function probe(root) {
  const { config } = loadConfig(root);
  const failed = [];
  for (const id of builtIns) {
    const profile = config.agents?.profiles?.[id];
    if (!profile) continue;
    try {
      const payload = readJson(path.join(profile.workspace_dir, "agent.json"));
      if (payload.id !== id) failed.push(id);
    } catch (_error) {
      failed.push(id);
    }
  }
  process.stdout.write(failed.join("\n"));
}

function patchManifest(manifestPath) {
  const manifest = readJson(manifestPath);
  if (!manifest.qwenpaw_version || typeof manifest.qwenpaw_version !== "object") {
    throw new Error(`Missing qwenpaw_version: ${manifestPath}`);
  }
  manifest.qwenpaw_version.max = "2.2.0";
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

function repair(root, backupRoot, idsText) {
  const ids = [...new Set(idsText.split(",").filter(Boolean))];
  for (const id of ids) {
    if (!builtIns.has(id)) throw new Error(`Refusing non-built-in agent: ${id}`);
  }
  const dataRoot = path.join(root, "data");
  const workspacesRoot = path.join(dataRoot, "workspaces");
  const backupWorkspaces = path.join(backupRoot, "workspaces");
  fs.mkdirSync(backupWorkspaces, { recursive: true });
  const { configPath, config } = loadConfig(root);
  fs.copyFileSync(configPath, path.join(backupRoot, "config.json.before"));

  for (const id of ids) {
    const profile = config.agents?.profiles?.[id];
    if (!profile) continue;
    const workspace = String(profile.workspace_dir || "");
    if (!isChild(workspace, workspacesRoot)) {
      throw new Error(`Workspace escapes product data for ${id}: ${workspace}`);
    }
    if (fs.existsSync(workspace)) {
      fs.renameSync(workspace, path.join(backupWorkspaces, id));
    }
    delete config.agents.profiles[id];
    config.agents.agent_order = config.agents.agent_order.filter(
      (candidate) => candidate !== id,
    );
  }

  const tempConfig = `${configPath}.hotfix.tmp`;
  fs.writeFileSync(tempConfig, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  fs.renameSync(tempConfig, configPath);

  const marker = path.join(
    dataRoot,
    ".migrations",
    "go-claw-presets-v1.json",
  );
  if (fs.existsSync(marker)) {
    fs.renameSync(marker, path.join(backupRoot, "go-claw-presets-v1.json"));
  }
}

const [mode, root, backupRoot, idsText = ""] = process.argv.slice(2);
if (mode === "probe") {
  probe(root);
} else if (mode === "patch-manifest") {
  patchManifest(root);
} else if (mode === "repair") {
  repair(root, backupRoot, idsText);
} else {
  throw new Error(`Unknown mode: ${mode}`);
}
