const fs = require("fs");
const path = require("path");

const shortMobileRoot = "C:\\HGAI_mobile";
const mobileRoot = fs.existsSync(shortMobileRoot) ? shortMobileRoot : __dirname;

/** @type {Detox.DetoxConfig} */
module.exports = {
  testRunner: {
    args: {
      "$0": path.join(mobileRoot, "node_modules", ".bin", process.platform === "win32" ? "jest.cmd" : "jest"),
      config: "e2e/jest.config.js",
    },
    jest: {
      setupTimeout: 240000,
    },
  },
  artifacts: {
    rootDir: "artifacts/detox",
    plugins: {
      log: "none",
      screenshot: "manual",
      video: "none",
      instruments: "none",
      uiHierarchy: "disabled",
    },
  },
  apps: {
    "android.debug": {
      type: "android.apk",
      binaryPath: path.join(mobileRoot, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk"),
      testBinaryPath: path.join(mobileRoot, "android", "app", "build", "outputs", "apk", "androidTest", "debug", "app-debug-androidTest.apk"),
      build: "node ./e2e/scripts/build-android-debug.cjs",
      reversePorts: [8000],
    },
  },
  devices: {
    emulator: {
      type: "android.emulator",
      device: {
        avdName: "Pixel_9",
      },
    },
    attached: {
      type: "android.attached",
      device: {
        adbName: ".*",
      },
    },
  },
  configurations: {
    "android.emu.debug": {
      device: "emulator",
      app: "android.debug",
    },
    "android.att.debug": {
      device: "attached",
      app: "android.debug",
    },
  },
};
