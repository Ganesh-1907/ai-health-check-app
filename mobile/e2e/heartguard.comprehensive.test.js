const { expect: jestExpect } = require("@jest/globals");
const {
  capture,
  dismissInputFocus,
  expectVisibleIds,
  fillField,
  launchApp,
  openTab,
  scrollToTop,
  scrollToVisible,
} = require("./helpers/app");

const today = new Date().toISOString().slice(0, 10);
const assessmentValues = {
  name: "Detox Patient",
  age: "47",
  gender: "Female",
  location: "Bengaluru",
  contact: "9876543210",
  bp: "126/82",
  heartRate: "78",
  sugar: "108",
  cholesterol: "186",
  height: "170",
  weight: "72",
  history: "No previous surgeries. Prior palpitations under review.",
  medicines: "Aspirin 75 mg",
  familyHistory: "Father had coronary artery disease.",
  smoking: "No",
  alcohol: "Occasional",
  exercise: "Walking 30 min daily",
  foodHabits: "Mostly home-cooked low-salt meals",
  sleep: "7.2",
  stress: "Moderate",
};
const reportType = "lipid_profile";
const trackingValues = {
  bp: "128/82",
  sugar: "110",
  weight: "71.8",
  steps: "6400",
  sleep: "7.5",
};
const expectedTrackingLog = `- ${today}: BP 128/82, Sugar 110, Steps 6400, Sleep 7.5h`;
const assistantQuestion = "What should I do after this uploaded report?";
const followUpAssistantQuestion = "Should I seek urgent doctor review for the blockage finding?";
const e2eLatitude = "12.9716";
const e2eLongitude = "77.5946";
const e2eLocationLabel = "12.9716, 77.5946";

describe("HeartGuard AI comprehensive e2e", () => {
  beforeAll(async () => {
    await launchApp({ deleteApp: true });
  });

  it("covers the dashboard overview, metrics, alerts, and guidance sections", async () => {
    await waitFor(element(by.id("screen-dashboard"))).toBeVisible().withTimeout(30000);
    await expectVisibleIds(
      [
        "tab-dashboard",
        "tab-assessment",
        "tab-reports",
        "tab-tracking",
        "tab-assistant",
        "tab-care",
        "screen-dashboard",
        "dashboard-hero",
        "dashboard-risk-title",
        "dashboard-risk-confidence",
        "dashboard-refresh-button",
        "dashboard-metric-grid",
        "dashboard-metric-value-bp",
        "dashboard-metric-value-sugar",
        "dashboard-metric-value-bmi",
        "dashboard-metric-value-sleep",
      ],
    );
    await capture("01-dashboard-top");

    await element(by.id("dashboard-refresh-button")).tap();

    await expectVisibleIds(
      [
        "dashboard-active-alerts-card",
        "dashboard-alert-1",
        "dashboard-weekly-trend-card",
        "dashboard-trend-row-1",
        "dashboard-trend-legend",
        "dashboard-daily-tips-card",
        "dashboard-daily-tip-1",
        "dashboard-diet-plan-card",
        "dashboard-diet-item-1",
        "dashboard-foods-to-avoid-card",
        "dashboard-food-avoid-item-1",
        "dashboard-medicine-guidance-card",
        "dashboard-medicine-guidance-item-1",
      ],
      "screen-dashboard-scroll",
    );
    await capture("02-dashboard-guidance");
  });

  it("fills the full assessment flow, taps every symptom chip, and verifies the BMI update", async () => {
    await openTab("tab-assessment", "screen-assessment");
    await expectVisibleIds(
      [
        "assessment-header",
        "assessment-personal-details-card",
        "field-assessment-full-name",
        "field-assessment-age",
        "field-assessment-gender",
        "field-assessment-location",
        "field-assessment-contact-number",
        "assessment-health-values-card",
        "field-assessment-blood-pressure",
        "field-assessment-heart-rate",
        "field-assessment-blood-sugar",
        "field-assessment-cholesterol",
        "field-assessment-height-cm",
        "field-assessment-weight-kg",
      ],
      "screen-assessment-scroll",
    );
    await capture("03-assessment-top");
    await scrollToTop("screen-assessment-scroll");

    await fillField("field-assessment-full-name", assessmentValues.name, "screen-assessment-scroll");
    await fillField("field-assessment-age", assessmentValues.age, "screen-assessment-scroll");
    await fillField("field-assessment-gender", assessmentValues.gender, "screen-assessment-scroll");
    await fillField("field-assessment-location", assessmentValues.location, "screen-assessment-scroll");
    await fillField("field-assessment-contact-number", assessmentValues.contact, "screen-assessment-scroll");
    await fillField("field-assessment-blood-pressure", assessmentValues.bp, "screen-assessment-scroll");
    await fillField("field-assessment-heart-rate", assessmentValues.heartRate, "screen-assessment-scroll");
    await fillField("field-assessment-blood-sugar", assessmentValues.sugar, "screen-assessment-scroll");
    await fillField("field-assessment-cholesterol", assessmentValues.cholesterol, "screen-assessment-scroll");
    await fillField("field-assessment-height-cm", assessmentValues.height, "screen-assessment-scroll");
    await fillField("field-assessment-weight-kg", assessmentValues.weight, "screen-assessment-scroll");

    await scrollToVisible("assessment-symptoms-card", "screen-assessment-scroll");
    await element(by.id("chip-assessment-symptom-chest-pain")).tap();
    await element(by.id("chip-assessment-symptom-chest-pain")).tap();
    await element(by.id("chip-assessment-symptom-dizziness")).tap();
    await element(by.id("chip-assessment-symptom-fatigue")).tap();
    await element(by.id("chip-assessment-symptom-shortness-of-breath")).tap();
    await element(by.id("chip-assessment-symptom-sweating")).tap();

    await scrollToVisible("assessment-medical-history-card", "screen-assessment-scroll");
    await fillField("field-assessment-history", assessmentValues.history, "screen-assessment-scroll");
    await fillField("field-assessment-current-medicines", assessmentValues.medicines, "screen-assessment-scroll");
    await fillField("field-assessment-family-history", assessmentValues.familyHistory, "screen-assessment-scroll");

    await scrollToVisible("assessment-lifestyle-card", "screen-assessment-scroll");
    await fillField("field-assessment-smoking", assessmentValues.smoking, "screen-assessment-scroll");
    await fillField("field-assessment-alcohol", assessmentValues.alcohol, "screen-assessment-scroll");
    await fillField("field-assessment-exercise", assessmentValues.exercise, "screen-assessment-scroll");
    await fillField("field-assessment-food-habits", assessmentValues.foodHabits, "screen-assessment-scroll");
    await fillField("field-assessment-sleep-hours", assessmentValues.sleep, "screen-assessment-scroll");
    await fillField("field-assessment-stress-level", assessmentValues.stress, "screen-assessment-scroll");
    await capture("04-assessment-bottom");

    await scrollToVisible("assessment-submit-button", "screen-assessment-scroll");
    await dismissInputFocus();
    await element(by.id("assessment-submit-button")).tap();

    await openTab("tab-dashboard", "screen-dashboard");
    await element(by.id("dashboard-refresh-button")).tap();
    await waitFor(element(by.id("dashboard-metric-value-bmi"))).toHaveText("24.91").withTimeout(30000);
    await capture("05-dashboard-after-assessment");
  });

  it("uploads a report and verifies the extracted document summary", async () => {
    await openTab("tab-reports", "screen-reports");
    await expectVisibleIds(
      [
        "reports-header",
        "reports-definitions-card",
        "reports-upload-center-card",
        "reports-select-file-button",
        "reports-upload-button",
        "reports-upload-status",
      ],
      "screen-reports-scroll",
    );
    await capture("06-reports-before-upload");

    // Two-step flow: Select then Submit
    await element(by.id("reports-select-file-button")).tap();
    await waitFor(element(by.id("reports-upload-button"))).toBeVisible().withTimeout(5000);
    await element(by.id("reports-upload-button")).tap();

    await expectVisibleIds(["reports-document-intelligence-card"], "screen-reports-scroll");
    await scrollToVisible("reports-latest-file", "screen-reports-scroll");
    await waitFor(element(by.id("reports-latest-file"))).toHaveText("File").withTimeout(30000);
    // Verifying the value in the next column/text node (or just checking text exists)
    await expect(element(by.id("reports-latest-type"))).toBeVisible();
    await expect(element(by.id("reports-latest-confidence"))).toBeVisible();
    await expect(element(by.id("reports-upload-status"))).toBeVisible();
    const findings = await element(by.id("reports-latest-findings")).getAttributes();
    jestExpect(findings.text).toContain("ldl");
    jestExpect(findings.text).toContain("182");
    jestExpect(findings.text).toContain("blockage percent");
    jestExpect(findings.text).toContain("78");
    await capture("07-reports-after-upload");
  });

  it("saves a daily tracking log and verifies recent log plus dashboard metrics", async () => {
    await openTab("tab-tracking", "screen-tracking");
    await expectVisibleIds(
      [
        "tracking-header",
        "tracking-todays-log-card",
        "field-tracking-blood-pressure",
        "field-tracking-blood-sugar",
        "field-tracking-weight",
        "field-tracking-steps",
        "field-tracking-sleep-hours",
        "tracking-save-daily-record-button",
        "tracking-progress-graph-card",
        "tracking-progress-row-1",
        "tracking-progress-legend",
        "tracking-recent-logs-card",
      ],
      "screen-tracking-scroll",
    );
    await scrollToTop("screen-tracking-scroll");

    await fillField("field-tracking-blood-pressure", trackingValues.bp, "screen-tracking-scroll");
    await fillField("field-tracking-blood-sugar", trackingValues.sugar, "screen-tracking-scroll");
    await fillField("field-tracking-weight", trackingValues.weight, "screen-tracking-scroll");
    await fillField("field-tracking-steps", trackingValues.steps, "screen-tracking-scroll");
    await fillField("field-tracking-sleep-hours", trackingValues.sleep, "screen-tracking-scroll");
    await capture("08-tracking-form");

    await dismissInputFocus();
    await element(by.id("tracking-save-daily-record-button")).tap();
    await scrollToVisible("tracking-recent-log-1", "screen-tracking-scroll");
    await waitFor(element(by.id("tracking-recent-log-1"))).toHaveText(expectedTrackingLog).withTimeout(30000);
    await capture("09-tracking-after-save");

    await openTab("tab-dashboard", "screen-dashboard");
    await waitFor(element(by.id("dashboard-metric-value-bp"))).toHaveText("128/82").withTimeout(30000);
    await expect(element(by.id("dashboard-metric-value-sugar"))).toHaveText("110");
    await expect(element(by.id("dashboard-metric-value-sleep"))).toHaveText("7.5h");
    await capture("10-dashboard-after-tracking");
  });

  it("sends assistant messages, verifies the replies, and confirms chat history survives tab changes", async () => {
    await openTab("tab-assistant", "screen-assistant");
    await expectVisibleIds(
      [
        "assistant-header",
        "assistant-conversation-card",
        "assistant-message-1-assistant",
        "assistant-message-text-1-assistant",
        "assistant-chat-input",
        "assistant-send-message-button",
      ],
    );
    await capture("11-assistant-before-send");

    await element(by.id("assistant-chat-input")).tap();
    await element(by.id("assistant-chat-input")).replaceText(assistantQuestion);
    await expect(element(by.id("assistant-chat-input"))).toHaveText(assistantQuestion);
    await dismissInputFocus();
    await element(by.id("assistant-send-message-button")).tap();

    await waitFor(element(by.id("assistant-message-2-user"))).toBeVisible().withTimeout(15000);
    await waitFor(element(by.id("assistant-message-3-assistant"))).toBeVisible().withTimeout(30000);
    await expect(element(by.text(assistantQuestion))).toBeVisible();
    const firstReply = await element(by.id("assistant-message-text-3-assistant")).getAttributes();
    jestExpect(firstReply.text).toContain("Direct answer:");
    await capture("12-assistant-after-send");

    await element(by.id("assistant-chat-input")).tap();
    await element(by.id("assistant-chat-input")).replaceText(followUpAssistantQuestion);
    await dismissInputFocus();
    await element(by.id("assistant-send-message-button")).tap();

    await waitFor(element(by.id("assistant-message-4-user"))).toBeVisible().withTimeout(15000);
    await waitFor(element(by.id("assistant-message-5-assistant"))).toBeVisible().withTimeout(30000);
    const secondReply = await element(by.id("assistant-message-text-5-assistant")).getAttributes();
    jestExpect(secondReply.text).toContain("Urgent care:");

    await openTab("tab-dashboard", "screen-dashboard");
    await openTab("tab-assistant", "screen-assistant");
    await expect(element(by.id("assistant-message-5-assistant"))).toBeVisible();
    await capture("13-assistant-history");
  });

  it("covers manual and GPS care search flows plus the emergency action section", async () => {
    await openTab("tab-care", "screen-care");
    await expectVisibleIds(
      [
        "care-header",
        "care-location-card",
        "care-location-label",
        "field-care-latitude",
        "field-care-longitude",
        "care-manual-search-button",
        "care-gps-search-button",
        "care-nearby-care-card",
      ],
    );
    await expect(element(by.id("care-no-results"))).toBeVisible();

    await fillField("field-care-latitude", e2eLatitude, "screen-care-scroll");
    await fillField("field-care-longitude", e2eLongitude, "screen-care-scroll");
    await capture("14-care-before-manual-search");
    await dismissInputFocus();
    await element(by.id("care-manual-search-button")).tap();

    await scrollToTop("screen-care-scroll");
    await waitFor(element(by.id("care-location-label"))).toHaveText(e2eLocationLabel).withTimeout(20000);
    await waitFor(element(by.id("care-result-1"))).toBeVisible().withTimeout(30000);
    await capture("15-care-manual-search");

    await fillField("field-care-latitude", "0", "screen-care-scroll");
    await fillField("field-care-longitude", "0", "screen-care-scroll");
    await dismissInputFocus();
    await element(by.id("care-gps-search-button")).tap();

    await scrollToTop("screen-care-scroll");
    await waitFor(element(by.id("field-care-latitude"))).toHaveText(e2eLatitude).withTimeout(20000);
    await waitFor(element(by.id("field-care-longitude"))).toHaveText(e2eLongitude).withTimeout(20000);
    await waitFor(element(by.id("care-location-label"))).toHaveText(e2eLocationLabel).withTimeout(20000);

    await scrollToVisible("care-emergency-action-card", "screen-care-scroll");
    await expectVisibleIds([
      "care-emergency-action-card",
      "care-emergency-action-1",
      "care-emergency-action-2",
      "care-emergency-action-3",
    ]);
    await capture("16-care-gps-search");
  });
});
