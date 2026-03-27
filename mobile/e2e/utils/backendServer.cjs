const fs = require("fs");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..", "..", "..");
const backendDir = path.join(repoRoot, "backend");
const backendDbPath = path.join(backendDir, "data", "heartguard.db");
const backendStorageDir = path.join(backendDir, "storage");
const artifactsDir = path.resolve(__dirname, "..", "..", "artifacts", "detox");
const stateFile = path.resolve(__dirname, "..", ".backend-server.json");
const backendUrl = "http://127.0.0.1:8000/api/v1/health";
const backendPort = 8000;

async function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isBackendHealthy() {
  try {
    const response = await fetch(backendUrl);
    return response.ok;
  } catch {
    return false;
  }
}

function resolvePythonLaunch() {
  const candidates = [
    { command: "py", prefixArgs: ["-3"] },
    { command: "python", prefixArgs: [] },
  ];

  for (const candidate of candidates) {
    const probe = spawnSync(candidate.command, [...candidate.prefixArgs, "--version"], { stdio: "ignore" });
    if (probe.status === 0) {
      return candidate;
    }
  }

  throw new Error("Python was not found. Install Python 3 and make sure `py` or `python` is available in PATH.");
}

async function waitForBackend(timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isBackendHealthy()) {
      return true;
    }
    await delay(1000);
  }

  return false;
}

function listListeningPidsOnPort(port) {
  if (process.platform === "win32") {
    const probe = spawnSync(
      "cmd.exe",
      ["/c", `netstat -ano -p tcp | findstr LISTENING | findstr :${port}`],
      { encoding: "utf8" },
    );
    if (probe.status !== 0 || !probe.stdout) {
      return [];
    }

    return [...new Set(
      probe.stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => line.split(/\s+/).pop())
        .filter((pid) => pid && /^\d+$/.test(pid)),
    )].map((pid) => Number(pid));
  }

  const probe = spawnSync("lsof", ["-t", `-iTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" });
  if (probe.status !== 0 || !probe.stdout) {
    return [];
  }

  return [...new Set(
    probe.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((pid) => /^\d+$/.test(pid)),
  )].map((pid) => Number(pid));
}

function stopProcessTree(pid) {
  if (!pid || !Number.isFinite(pid)) {
    return;
  }

  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(pid, "SIGTERM");
    }
  } catch {
    // Ignore cleanup errors for already-exited processes.
  }
}

function clearDirectoryContents(directoryPath) {
  if (!fs.existsSync(directoryPath)) {
    return;
  }

  for (const entry of fs.readdirSync(directoryPath, { withFileTypes: true })) {
    const entryPath = path.join(directoryPath, entry.name);
    fs.rmSync(entryPath, { recursive: true, force: true });
  }
}

function resetBackendData() {
  stopBackend();

  for (const pid of listListeningPidsOnPort(backendPort)) {
    stopProcessTree(pid);
  }

  fs.rmSync(stateFile, { force: true });
  fs.rmSync(backendDbPath, { force: true });
  fs.mkdirSync(path.dirname(backendDbPath), { recursive: true });
  fs.mkdirSync(backendStorageDir, { recursive: true });
  clearDirectoryContents(backendStorageDir);
}

async function ensureBackendRunning(options = {}) {
  if (options.reset) {
    resetBackendData();
  } else if (await isBackendHealthy()) {
    return { started: false };
  }

  fs.mkdirSync(artifactsDir, { recursive: true });
  const logPath = path.join(artifactsDir, "backend.log");
  const logFd = fs.openSync(logPath, "a");
  const python = resolvePythonLaunch();
  const child = spawn(
    python.command,
    [...python.prefixArgs, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
      },
      detached: true,
      stdio: ["ignore", logFd, logFd],
    },
  );

  child.unref();
  fs.writeFileSync(stateFile, JSON.stringify({ pid: child.pid, logPath }, null, 2), "utf8");

  const ready = await waitForBackend(90000);
  if (!ready) {
    throw new Error(`Backend did not become healthy within 90s. Check ${logPath}.`);
  }

  return { started: true, logPath };
}

function stopBackend() {
  if (!fs.existsSync(stateFile)) {
    return;
  }

  const { pid } = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  try {
    stopProcessTree(pid);
  } finally {
    fs.rmSync(stateFile, { force: true });
  }
}

module.exports = {
  ensureBackendRunning,
  stopBackend,
};
