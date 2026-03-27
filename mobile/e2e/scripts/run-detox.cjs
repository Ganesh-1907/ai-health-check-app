const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const mobileRoot = path.resolve(__dirname, "..", "..");
const fallbackSdkRoot = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, "Android", "Sdk") : "";
const androidSdkRoot = process.env.ANDROID_SDK_ROOT || process.env.ANDROID_HOME || fallbackSdkRoot;

if (!androidSdkRoot || !fs.existsSync(androidSdkRoot)) {
  throw new Error(
    "Android SDK was not found. Set ANDROID_SDK_ROOT or install the SDK under %LOCALAPPDATA%\\Android\\Sdk.",
  );
}

const env = {
  ...process.env,
  ANDROID_SDK_ROOT: androidSdkRoot,
  ANDROID_HOME: process.env.ANDROID_HOME || androidSdkRoot,
};

const detoxBinary = path.join(
  mobileRoot,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "detox.cmd" : "detox",
);
const command = process.platform === "win32" ? "cmd.exe" : detoxBinary;
const args = process.platform === "win32" ? ["/c", detoxBinary, ...process.argv.slice(2)] : process.argv.slice(2);
const result = spawnSync(command, args, {
  cwd: mobileRoot,
  env,
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

if (result.status !== 0) {
  process.exit(result.status || 1);
}
