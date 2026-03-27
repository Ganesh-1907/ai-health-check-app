/** @type {import('@jest/types').Config.InitialOptions} */
module.exports = {
  rootDir: '..',
  testMatch: ['<rootDir>/e2e/**/*.test.js'],
  testTimeout: 240000,
  maxWorkers: 1,
  forceExit: true,
  globalSetup: '<rootDir>/e2e/jest.globalSetup.js',
  globalTeardown: '<rootDir>/e2e/jest.globalTeardown.js',
  reporters: ['detox/runners/jest/reporter'],
  testEnvironment: 'detox/runners/jest/testEnvironment',
  verbose: true,
};
