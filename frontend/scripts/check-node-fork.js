/* eslint-disable no-console */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { fork } = require("node:child_process");

function parseMajor(version) {
  const major = Number(String(version).split(".")[0]);
  return Number.isFinite(major) ? major : null;
}

function printHelp(error) {
  const nodeVersion = process.versions.node;
  console.error("");
  console.error("Frontend dev server failed to start because Node cannot fork child processes.");
  console.error(`Detected Node.js ${nodeVersion} at: ${process.execPath}`);
  if (error) {
    const code = error.code ? String(error.code) : "unknown";
    console.error(`Fork error: ${code}${error.message ? ` (${error.message})` : ""}`);
  }
  console.error("");
  console.error("Fix:");
  console.error("- Install and use Node.js 22 LTS (recommended) or Node.js 20 LTS.");
  console.error("- Then reinstall frontend dependencies and retry:");
  console.error("  - cd frontend");
  console.error("  - Remove-Item -Recurse -Force node_modules,package-lock.json");
  console.error("  - npm install");
  console.error("  - npm run dev");
  console.error("");
  console.error("Why this happens:");
  console.error("- On some Windows setups, Node.js 24+ can throw EPERM on child_process.fork(),");
  console.error("  which Next.js relies on to start the dev server.");
  console.error("");
}

async function main() {
  const major = parseMajor(process.versions.node);
  const isPotentiallyProblematicWindowsNode =
    process.platform === "win32" && major !== null && major >= 24;

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "effector-frontend-check-"));
  const childScript = path.join(tmpDir, "child.js");
  fs.writeFileSync(childScript, "process.exit(0);\n", "utf8");

  try {
    await new Promise((resolve, reject) => {
      const cp = fork(childScript, [], {
        stdio: "ignore",
        windowsHide: true,
      });
      cp.on("error", reject);
      cp.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`exit ${code}`))));
    });
    if (isPotentiallyProblematicWindowsNode) {
      // Node 24+ can be problematic on some Windows setups (EPERM on fork()).
      // If the probe above succeeded, allow dev to proceed but warn loudly.
      console.warn("");
      console.warn(
        `Warning: Detected Node.js ${process.versions.node} on Windows. If the dev server fails, use Node.js 22/20 LTS.`
      );
      console.warn("");
    }
  } catch (error) {
    // Some Windows environments block IPC-based process spawning (fork) with EPERM.
    // Next.js can still run in a single-process fallback mode (see patched next-dev.js),
    // so warn but do not hard-fail here.
    if (error && String(error.code || "").toUpperCase() === "EPERM") {
      console.warn("");
      console.warn(
        `Warning: Node cannot fork child processes here (EPERM). Continuing; Next.js dev may run in single-process mode.`
      );
      console.warn("");
    } else {
      printHelp(error);
      process.exit(1);
      return;
    }
  } finally {
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
}

main().catch((error) => {
  printHelp(error);
  process.exit(1);
});
