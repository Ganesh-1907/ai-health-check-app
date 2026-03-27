const detoxGlobalSetup = require("detox/runners/jest/globalSetup");
const { ensureBackendRunning } = require("./utils/backendServer.cjs");

module.exports = async () => {
  await ensureBackendRunning({ reset: true });
  await detoxGlobalSetup();
};
