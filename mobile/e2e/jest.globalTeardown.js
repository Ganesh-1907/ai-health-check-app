const detoxGlobalTeardown = require("detox/runners/jest/globalTeardown");
const { stopBackend } = require("./utils/backendServer.cjs");

module.exports = async () => {
  try {
    await detoxGlobalTeardown();
  } finally {
    stopBackend();
  }
};
