function sanitizeName(value) {
  return value.replace(/[^a-zA-Z0-9-_]+/g, "-");
}

async function launchApp(options = {}) {
  await device.launchApp({
    delete: options.deleteApp === true,
    newInstance: true,
  });
  await waitFor(element(by.id("screen-dashboard"))).toBeVisible().withTimeout(30000);
}

async function capture(name) {
  await device.takeScreenshot(sanitizeName(name));
}

async function scrollToTop(scrollViewId) {
  const scrollView = element(by.id(scrollViewId));
  try {
    await scrollView.scrollTo("top");
    return;
  } catch {
    // Fall back to repeated upward scrolls when scrollTo is unavailable.
  }

  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      await scrollView.scroll(500, "up");
    } catch {
      break;
    }
  }
}

async function scrollToVisible(targetId, scrollViewId) {
  try {
    await expect(element(by.id(targetId))).toBeVisible();
    return;
  } catch {
    // Fall through to scroll-based lookup.
  }

  await waitFor(element(by.id(targetId)))
    .toBeVisible()
    .whileElement(by.id(scrollViewId))
    .scroll(220, "down");
}

async function openTab(tabId, screenId) {
  await element(by.id(tabId)).tap();
  await waitFor(element(by.id(screenId))).toBeVisible().withTimeout(15000);
  await scrollToTop(`${screenId}-scroll`);
}

async function fillField(fieldId, value, scrollViewId) {
  const field = element(by.id(fieldId));
  try {
    await field.tap();
  } catch {
    await scrollToVisible(fieldId, scrollViewId);
    await field.tap();
  }
  await field.replaceText(String(value));
}

async function dismissInputFocus() {
  try {
    await device.pressBack();
  } catch {
    // Ignore cases where no focused editor is active.
  }
}

async function expectVisibleIds(ids, scrollViewId) {
  for (const id of ids) {
    if (scrollViewId) {
      await scrollToVisible(id, scrollViewId);
    }
    await expect(element(by.id(id))).toBeVisible();
  }
}

module.exports = {
  capture,
  dismissInputFocus,
  expectVisibleIds,
  fillField,
  launchApp,
  openTab,
  scrollToTop,
  scrollToVisible,
};
