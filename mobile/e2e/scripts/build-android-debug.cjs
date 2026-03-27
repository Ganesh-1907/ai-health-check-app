const fs = require("fs");
const { spawnSync } = require("child_process");
const path = require("path");

const shortMobileRoot = "C:\\HGAI_mobile";
const mobileRoot = fs.existsSync(shortMobileRoot) ? shortMobileRoot : path.resolve(__dirname, "..", "..");
const androidDir = path.join(mobileRoot, "android");
const gradleArgs = [
  "assembleDebug",
  "assembleAndroidTest",
  "-DtestBuildType=debug",
  "-PreactNativeArchitectures=x86_64",
];
const env = {
  ...process.env,
  EXPO_PUBLIC_E2E_MODE: "1",
  EXPO_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000/api/v1",
  NODE_ENV: process.env.NODE_ENV || "test",
};

const command = process.platform === "win32" ? "cmd.exe" : "./gradlew";
const args = process.platform === "win32" ? ["/c", "gradlew.bat", ...gradleArgs] : gradleArgs;

const result = spawnSync(command, args, {
  cwd: androidDir,
  env,
  stdio: "inherit",
});

if (result.status !== 0) {
  process.exit(result.status || 1);
}
