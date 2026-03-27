import "react-native-gesture-handler";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  NativeModules,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import { LinearGradient } from "expo-linear-gradient";
import * as DocumentPicker from "expo-document-picker";
import { File, Paths } from "expo-file-system";
import * as Location from "expo-location";

import { dashboardSnapshot, initialChat } from "./src/data/mock";
import { palette } from "./src/theme";
import { storage } from "./src/utils/storage";

const Tab = createBottomTabNavigator();
const queryClient = new QueryClient();
const backendHealthTimeoutMs = 2500;
const requestTimeoutMs = 8000;
const uploadRequestTimeoutMs = 20000;
const storageKey = "heartguard-user-id";
const isE2EMode = process.env.EXPO_PUBLIC_E2E_MODE === "1";
const e2eCoordinates = { latitude: 12.9716, longitude: 77.5946 };
const e2eReportFileName = "detox-heart-report.txt";
const fallbackDietPlan = [
  "Build meals around vegetables, whole grains, and lean protein.",
  "Keep meal timing steady so sugar and energy swings stay more controlled.",
  "Use low-sodium cooking and avoid heavy fried meals when possible.",
];
const fallbackFoodsToAvoid = ["Deep-fried foods", "Sugary drinks", "Processed high-salt snacks"];
const fallbackMedicineGuidance = [
  "Continue prescribed medicines exactly as your doctor advised.",
  "Do not start or stop prescription medicines without consulting a doctor.",
];

function extractHostFromUri(value?: string | null): string | null {
  if (!value) return null;
  const withoutScheme = value.includes("://") ? value.split("://")[1] : value;
  const authority = withoutScheme.split("/")[0]?.split("?")[0]?.trim();
  if (!authority) return null;
  const host = authority.split(":")[0]?.trim();
  return host || null;
}

function resolveApiBaseUrl(): string {
  if (process.env.EXPO_PUBLIC_API_BASE_URL) {
    return process.env.EXPO_PUBLIC_API_BASE_URL;
  }

  const devHost = [
    Constants.expoConfig?.hostUri,
    (Constants.expoGoConfig as { debuggerHost?: string } | null)?.debuggerHost,
    (NativeModules.SourceCode?.scriptURL as string | undefined),
  ]
    .map((candidate) => extractHostFromUri(candidate))
    .find((host) => host && host !== "localhost" && host !== "127.0.0.1");

  if (devHost) {
    return `http://${devHost}:8000/api/v1`;
  }

  return Platform.OS === "android" ? "http://10.0.2.2:8000/api/v1" : "http://127.0.0.1:8000/api/v1";
}

const apiBaseUrl = resolveApiBaseUrl();

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

type DashboardPayload = {
  user: {
    id: number;
    name: string;
    age: number;
    gender: string;
    location: string;
    contact_number: string;
    latitude?: number;
    longitude?: number;
  };
  latest_assessment?: {
    systolic_bp?: number;
    diastolic_bp?: number;
    blood_sugar?: number;
    cholesterol?: number;
    bmi?: number;
    symptoms: string[];
  } | null;
  latest_prediction?: {
    risk_score: number;
    risk_level: string;
    confidence: number;
    explanation: string[];
  } | null;
  latest_recommendation?: {
    diet_plan: string[];
    foods_to_avoid: string[];
    medicine_guidance: string[];
    daily_tips: string[];
  } | null;
  active_alerts: Array<{
    id: number;
    title: string;
    message: string;
    severity?: string;
  }>;
  recent_daily_logs: Array<{
    id: number;
    log_date: string;
    systolic_bp?: number;
    diastolic_bp?: number;
    blood_sugar?: number;
    weight_kg?: number;
    steps?: number;
    sleep_hours?: number;
    created_at: string;
    updated_at: string;
  }>;
  reports: Array<{
    id: number;
    report_type: string;
    file_name: string;
    extracted_findings: Record<string, unknown>;
    extraction_confidence: number;
  }>;
};

type CareLocation = {
  name: string;
  kind: string;
  latitude: number;
  longitude: number;
  distance_km: number;
  address: string;
  phone: string;
  source: string;
};

type AssessmentFormState = {
  name: string;
  age: string;
  gender: string;
  location: string;
  contact: string;
  bp: string;
  heartRate: string;
  sugar: string;
  cholesterol: string;
  height: string;
  weight: string;
  history: string;
  medicines: string;
  familyHistory: string;
  smoking: string;
  alcohol: string;
  exercise: string;
  foodHabits: string;
  sleep: string;
  stress: string;
};

type DailyLogFormState = {
  bp: string;
  sugar: string;
  weight: string;
  steps: string;
  sleep: string;
};

type DailyLogEntry = DashboardPayload["recent_daily_logs"][number];

type TrendPoint = {
  key: string;
  day: string;
  bp: number;
  sugar: number;
  weight: number;
};

type AppState = {
  userId: number | null;
  dashboard: DashboardPayload | null;
  careResults: CareLocation[];
  messages: ChatMessage[];
  loading: boolean;
  syncing: boolean;
  backendIssue: string | null;
  latestReportMessage: string;
  refreshDashboard: () => Promise<void>;
  submitAssessment: (payload: AssessmentFormState, selectedSymptoms: string[]) => Promise<void>;
  submitDailyLog: (payload: DailyLogFormState) => Promise<void>;
  sendChat: (message: string) => Promise<void>;
  uploadReport: (reportType: string) => Promise<void>;
  searchCare: (latitude: number, longitude: number) => Promise<void>;
};

const navTheme = {
  dark: false,
  colors: {
    primary: palette.brand,
    background: palette.background,
    card: palette.surface,
    text: palette.ink,
    border: palette.line,
    notification: palette.danger,
  },
  fonts: {
    regular: { fontFamily: "System", fontWeight: "400" },
    medium: { fontFamily: "System", fontWeight: "500" },
    bold: { fontFamily: "System", fontWeight: "700" },
    heavy: { fontFamily: "System", fontWeight: "800" },
  },
};

const AppStateContext = createContext<AppState | null>(null);

function useAppState() {
  const value = useContext(AppStateContext);
  if (!value) {
    throw new Error("App state not available");
  }
  return value;
}

async function fetchWithTimeout(input: string, options?: RequestInit, timeoutMs = requestTimeoutMs): Promise<Response> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`Request to ${input} timed out after ${timeoutMs / 1000}s`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutHandle);
  }
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetchWithTimeout(`${apiBaseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  return (await response.json()) as T;
}

async function checkBackendHealth(): Promise<void> {
  const response = await fetchWithTimeout(`${apiBaseUrl}/health`, undefined, backendHealthTimeoutMs);
  if (!response.ok) {
    throw new Error(`Backend health check failed with ${response.status}`);
  }
}

function parseBp(value: string): { systolic?: number; diastolic?: number } {
  const [sys, dia] = value.split("/").map((item) => Number(item.trim()));
  return {
    systolic: Number.isFinite(sys) ? sys : undefined,
    diastolic: Number.isFinite(dia) ? dia : undefined,
  };
}

function truthyFromText(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return false;
  return !["no", "none", "nil", "false", "0"].includes(normalized);
}

function toTestIdSegment(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function makeTestId(prefix: string, value: string): string {
  const segment = toTestIdSegment(value);
  return segment ? `${prefix}-${segment}` : prefix;
}

function buildTrendData(logs?: DashboardPayload["recent_daily_logs"] | null): TrendPoint[] {
  if (!logs) {
    return dashboardSnapshot.trends.map((item, index) => ({
      key: `snapshot-trend-${item.day}-${index}`,
      day: item.day,
      bp: item.bp,
      sugar: item.sugar,
      weight: item.weight,
    }));
  }

  return logs.slice().reverse().map((log) => ({
    key: `daily-log-${log.id}`,
    day: log.log_date.slice(5),
    bp: log.systolic_bp || 0,
    sugar: log.blood_sugar || 0,
    weight: log.weight_kg || 0,
  }));
}

function compareDailyLogs(a: DailyLogEntry, b: DailyLogEntry): number {
  return (
    new Date(b.log_date).getTime() - new Date(a.log_date).getTime() ||
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime() ||
    b.id - a.id
  );
}

function formatAppError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (/Request to .* timed out after /i.test(message) || /Network request failed/i.test(message)) {
    return `${message}. Backend URL: ${apiBaseUrl}. Make sure the backend is running, started with --host 0.0.0.0, and reachable from this device.`;
  }
  return message;
}

function showAppAlert(title: string, message: string) {
  if (isE2EMode) {
    console.info(`[app-alert] ${title}: ${message}`);
    return;
  }

  Alert.alert(title, message);
}

async function createE2EUploadFileAsset(): Promise<{ uri: string; name: string; type: string }> {
  const content = [
    "HeartGuard AI Detox report",
    `Generated at ${new Date().toISOString()}`,
    "LDL 182 mg/dL",
    "HDL 36 mg/dL",
    "Triglycerides 224 mg/dL",
    "Total cholesterol 248 mg/dL",
    "Glucose 132 mg/dL",
    "Blood pressure 148/92",
    "Blockage 78%",
    "Ejection fraction 34%",
  ].join("\n");
  const file = new File(Paths.cache, e2eReportFileName);
  file.create({ intermediates: true, overwrite: true });
  file.write(content);
  return { uri: file.uri, name: e2eReportFileName, type: "text/plain" };
}

function showCriticalAlerts(nextDashboard: DashboardPayload | null) {
  if (!nextDashboard?.active_alerts?.length) return;
  const critical = nextDashboard.active_alerts.filter(
    (item) => item.severity === "critical" || /urgent|emergency|danger/i.test(`${item.title} ${item.message}`),
  );
  if (!critical.length) return;
  showAppAlert(critical[0].title || "Emergency Alert", critical[0].message);
}

function AppProvider({ children }: { children: React.ReactNode }) {
  const [userId, setUserId] = useState<number | null>(null);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [careResults, setCareResults] = useState<CareLocation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>(initialChat);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [backendIssue, setBackendIssue] = useState<string | null>(null);
  const [latestReportMessage, setLatestReportMessage] = useState("No report uploaded yet.");

  const loadChatHistory = async (nextUserId: number) => {
    try {
      const history = await fetchJson<Array<{ id: number; role: "assistant" | "user"; content: string }>>(
        `/users/${nextUserId}/chat-history`,
      );
      if (history.length) {
        setMessages(
          history.map((item) => ({
            id: `${item.id}`,
            role: item.role,
            text: item.content,
          })),
        );
      }
    } catch {
      setMessages(initialChat);
    }
  };

  const bootstrapDemoProfile = async (): Promise<number> => {
    const payload = await fetchJson<{ user_id: number; dashboard: DashboardPayload }>("/bootstrap/demo", {
      method: "POST",
    });
    setUserId(payload.user_id);
    setDashboard(payload.dashboard);
    setBackendIssue(null);
    showCriticalAlerts(payload.dashboard);
    await storage.set(storageKey, String(payload.user_id));
    await loadChatHistory(payload.user_id);
    return payload.user_id;
  };

  const ensureBackendSession = async (): Promise<number> => {
    try {
      await checkBackendHealth();
      if (userId) {
        setBackendIssue(null);
        return userId;
      }
      return await bootstrapDemoProfile();
    } catch (error) {
      const message = formatAppError(error);
      setBackendIssue(message);
      throw new Error(message);
    }
  };

  const refreshDashboard = async () => {
    const savedUserId = Number((await storage.get(storageKey)) || 0);
    const id = (userId ?? savedUserId) || (await ensureBackendSession());
    const nextDashboard = await fetchJson<DashboardPayload>(`/users/${id}/dashboard`);
    setDashboard(nextDashboard);
    setBackendIssue(null);
    showCriticalAlerts(nextDashboard);
  };

  useEffect(() => {
    const bootstrap = async () => {
      try {
        await checkBackendHealth();
        await bootstrapDemoProfile();
      } catch (error) {
        setDashboard(null);
        setBackendIssue(formatAppError(error));
      } finally {
        setLoading(false);
      }
    };
    void bootstrap();
  }, []);

  const submitAssessment = async (payload: AssessmentFormState, selectedSymptoms: string[]) => {
    setSyncing(true);
    try {
      const activeUserId = await ensureBackendSession();
      await fetchJson(`/users/${activeUserId}`, {
        method: "PUT",
        body: JSON.stringify({
          name: payload.name || dashboard?.user.name || "User",
          age: Number(payload.age || dashboard?.user.age || 40),
          gender: payload.gender || dashboard?.user.gender || "Male",
          location: payload.location || dashboard?.user.location || "",
          contact_number: payload.contact || dashboard?.user.contact_number || "",
        }),
      });

      const bp = parseBp(payload.bp);
      await fetchJson(`/users/${activeUserId}/assessments`, {
        method: "POST",
        body: JSON.stringify({
          systolic_bp: bp.systolic,
          diastolic_bp: bp.diastolic,
          heart_rate: Number(payload.heartRate) || null,
          blood_sugar: Number(payload.sugar) || null,
          cholesterol: Number(payload.cholesterol) || null,
          height_cm: Number(payload.height) || null,
          weight_kg: Number(payload.weight) || null,
          symptoms: selectedSymptoms,
          medical_history: {
            previous_heart_problems: truthyFromText(payload.history),
            surgeries: payload.history,
            current_medicines: payload.medicines,
            family_history: truthyFromText(payload.familyHistory),
            diabetes: Number(payload.sugar) >= 126,
            hypertension: (bp.systolic || 0) >= 140 || (bp.diastolic || 0) >= 90,
          },
          lifestyle: {
            smoking: truthyFromText(payload.smoking),
            alcohol: payload.alcohol,
            exercise: payload.exercise,
            food_habits: payload.foodHabits,
            sleep_hours: Number(payload.sleep) || null,
            stress_level: payload.stress,
          },
          notes: "Submitted from mobile assessment flow.",
        }),
      });
      await refreshDashboard();
      showAppAlert("Assessment Saved", "Heart-risk profile has been refreshed from the backend.");
    } catch (error) {
      showAppAlert("Assessment Error", formatAppError(error));
    } finally {
      setSyncing(false);
    }
  };

  const submitDailyLog = async (payload: DailyLogFormState) => {
    setSyncing(true);
    try {
      const activeUserId = await ensureBackendSession();
      const bp = parseBp(payload.bp);
      const createdLog = await fetchJson<DailyLogEntry>(`/users/${activeUserId}/daily-logs`, {
        method: "POST",
        body: JSON.stringify({
          log_date: new Date().toISOString().slice(0, 10),
          systolic_bp: bp.systolic,
          diastolic_bp: bp.diastolic,
          blood_sugar: Number(payload.sugar) || null,
          weight_kg: Number(payload.weight) || null,
          steps: Number(payload.steps) || null,
          sleep_hours: Number(payload.sleep) || null,
          notes: "Logged from mobile tracking screen.",
        }),
      });

      setDashboard((current) => {
        if (!current) return current;
        const recentDailyLogs = [createdLog, ...current.recent_daily_logs.filter((item) => item.id !== createdLog.id)]
          .sort(compareDailyLogs)
          .slice(0, 7);
        return { ...current, recent_daily_logs: recentDailyLogs };
      });

      try {
        await refreshDashboard();
        showAppAlert("Daily Record Saved", "Daily trends have been updated.");
      } catch (refreshError) {
        showAppAlert("Daily Record Saved", `The record was saved, but dashboard refresh failed. ${formatAppError(refreshError)}`);
      }
    } catch (error) {
      showAppAlert("Daily Log Error", formatAppError(error));
    } finally {
      setSyncing(false);
    }
  };

  const sendChat = async (message: string) => {
    if (!message.trim()) return;
    const userMessage: ChatMessage = { id: `${Date.now()}-user`, role: "user", text: message.trim() };
    setMessages((current) => [...current, userMessage]);
    try {
      const activeUserId = await ensureBackendSession();
      const payload = await fetchJson<{ reply: string }>("/chat", {
        method: "POST",
        body: JSON.stringify({ user_id: activeUserId, message: userMessage.text }),
      });
      setMessages((current) => [
        ...current,
        { id: `${Date.now()}-assistant`, role: "assistant", text: payload.reply },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: `${Date.now()}-assistant`, role: "assistant", text: `Chat request failed: ${formatAppError(error)}` },
      ]);
    }
  };

  const uploadReport = async (reportType: string) => {
    setSyncing(true);
    try {
      const activeUserId = await ensureBackendSession();
      const form = new FormData();
      form.append("report_type", reportType || "general_report");
      if (isE2EMode) {
        form.append("file", (await createE2EUploadFileAsset()) as never);
      } else {
        const result = await DocumentPicker.getDocumentAsync({ multiple: false, copyToCacheDirectory: true });
        if (result.canceled || !result.assets[0]) return;

        const asset = result.assets[0];
        form.append("file", { uri: asset.uri, name: asset.name, type: asset.mimeType || "application/octet-stream" } as never);
      }
      const response = await fetchWithTimeout(
        `${apiBaseUrl}/users/${activeUserId}/reports/upload`,
        { method: "POST", body: form },
        uploadRequestTimeoutMs,
      );
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      setLatestReportMessage(`Uploaded ${payload.file_name}. Extraction confidence: ${Math.round(payload.extraction_confidence * 100)}%.`);
      await refreshDashboard();
    } catch (error) {
      setLatestReportMessage(`Upload failed: ${formatAppError(error)}`);
    } finally {
      setSyncing(false);
    }
  };

  const searchCare = async (latitude: number, longitude: number) => {
    setSyncing(true);
    try {
      await ensureBackendSession();
      const payload = await fetchJson<CareLocation[]>("/care-search", {
        method: "POST",
        body: JSON.stringify({ latitude, longitude, radius_meters: 5000 }),
      });
      setCareResults(payload);
    } catch (error) {
      setCareResults([]);
      showAppAlert("Care Search Error", formatAppError(error));
    } finally {
      setSyncing(false);
    }
  };

  const contextValue = useMemo<AppState>(
    () => ({
      userId,
      dashboard,
      careResults,
      messages,
      loading,
      syncing,
      backendIssue,
      latestReportMessage,
      refreshDashboard,
      submitAssessment,
      submitDailyLog,
      sendChat,
      uploadReport,
      searchCare,
    }),
    [userId, dashboard, careResults, messages, loading, syncing, backendIssue, latestReportMessage],
  );

  return <AppStateContext.Provider value={contextValue}>{children}</AppStateContext.Provider>;
}

function AppShell() {
  const { loading } = useAppState();

  if (loading) {
    return (
      <SafeAreaView edges={["top"]} style={styles.loadingWrap} testID="app-loading">
        <ActivityIndicator color={palette.brand} size="large" testID="app-loading-spinner" />
        <Text style={styles.helperText}>Bootstrapping local demo profile and dashboard...</Text>
      </SafeAreaView>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar barStyle="dark-content" />
      <Tab.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarStyle: styles.tabBar,
          tabBarActiveTintColor: palette.brand,
          tabBarInactiveTintColor: palette.muted,
          tabBarButtonTestID: `tab-${toTestIdSegment(route.name)}`,
          tabBarIcon: ({ color, size }) => {
            const icons: Record<string, keyof typeof Ionicons.glyphMap> = {
              Dashboard: "pulse",
              Assessment: "clipboard",
              Reports: "document-text",
              Tracking: "analytics",
              Assistant: "chatbubble-ellipses",
              Care: "medkit",
            };
            return <Ionicons color={color} name={icons[route.name]} size={size} />;
          },
        })}
      >
        <Tab.Screen component={DashboardScreen} name="Dashboard" />
        <Tab.Screen component={AssessmentScreen} name="Assessment" />
        <Tab.Screen component={ReportsScreen} name="Reports" />
        <Tab.Screen component={TrackingScreen} name="Tracking" />
        <Tab.Screen component={AssistantScreen} name="Assistant" />
        <Tab.Screen component={CareScreen} name="Care" />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

function DashboardScreen() {
  const { dashboard, refreshDashboard, syncing } = useAppState();
  const prediction = dashboard?.latest_prediction;
  const assessment = dashboard?.latest_assessment;
  const recommendation = dashboard?.latest_recommendation;
  const recentLog = dashboard?.recent_daily_logs[0];
  const trendData = buildTrendData(dashboard?.recent_daily_logs);

  const metricCards = [
    {
      label: "BP",
      value: recentLog?.systolic_bp && recentLog?.diastolic_bp ? `${recentLog.systolic_bp}/${recentLog.diastolic_bp}` : "--",
      tone: "danger",
    },
    { label: "Sugar", value: recentLog?.blood_sugar ? `${recentLog.blood_sugar}` : "--", tone: "warning" },
    { label: "BMI", value: assessment?.bmi ? `${assessment.bmi}` : "--", tone: "warning" },
    { label: "Sleep", value: recentLog?.sleep_hours ? `${recentLog.sleep_hours}h` : "--", tone: "cool" },
  ];

  return (
    <Screen testID="screen-dashboard">
      <LinearGradient colors={["#0C6D70", "#0B4B54"]} style={styles.hero} testID="dashboard-hero">
        <View>
          <Text style={styles.heroEyebrow} testID="dashboard-hero-eyebrow">Heart Disease Prediction</Text>
          <Text style={styles.heroTitle} testID="dashboard-risk-title">
            {prediction?.risk_level || dashboardSnapshot.riskLevel} Risk {prediction?.risk_score || dashboardSnapshot.riskScore}%
          </Text>
          <Text style={styles.heroCopy} testID="dashboard-risk-confidence">
            Confidence {Math.round(((prediction?.confidence ?? dashboardSnapshot.confidence) as number) * 100)}%. Use this as early support, not a final diagnosis.
          </Text>
        </View>
        <PrimaryButton compact label={syncing ? "Refreshing..." : "Refresh"} onPress={() => void refreshDashboard()} testID="dashboard-refresh-button" />
      </LinearGradient>

      <View style={styles.metricGrid} testID="dashboard-metric-grid">
        {metricCards.map((metric) => (
          <View key={metric.label} style={styles.metricCard} testID={`dashboard-metric-${toTestIdSegment(metric.label)}`}>
            <Text style={styles.metricLabel}>{metric.label}</Text>
            <Text
              style={[
                styles.metricValue,
                metric.tone === "danger" ? styles.dangerText : metric.tone === "warning" ? styles.warningText : styles.coolText,
              ]}
              testID={`dashboard-metric-value-${toTestIdSegment(metric.label)}`}
            >
              {metric.value}
            </Text>
          </View>
        ))}
      </View>

      <SectionCard subtitle="Act fast when these patterns appear" title="Active Alerts" testID="dashboard-active-alerts-card">
        {(dashboard?.active_alerts.length
          ? dashboard.active_alerts.map((item) => ({ key: `alert-${item.id}`, text: item.message }))
          : dashboardSnapshot.alerts.map((message, index) => ({ key: `snapshot-alert-${index}`, text: message }))
        ).map((alert, index) => (
          <View key={alert.key} style={styles.alertCard} testID={`dashboard-alert-${index + 1}`}>
            <Ionicons color={palette.danger} name="warning" size={18} />
            <Text style={styles.alertText}>{alert.text}</Text>
          </View>
        ))}
      </SectionCard>

      <SectionCard subtitle="Monitor progress daily" title="Weekly Trend Snapshot" testID="dashboard-weekly-trend-card">
        {trendData.map((item, index) => (
          <View key={item.key} style={styles.trendRow} testID={`dashboard-trend-row-${index + 1}`}>
            <Text style={styles.trendDay}>{item.day}</Text>
            <View style={styles.trendBars}>
              <MiniBar color={palette.brand} value={item.bp} />
              <MiniBar color={palette.accent} value={item.sugar} />
              <MiniBar color={palette.cool} value={Math.round(item.weight * 10)} />
            </View>
          </View>
        ))}
        <Text style={styles.legend} testID="dashboard-trend-legend">Teal: BP  Gold: Sugar  Blue: Weight trend</Text>
      </SectionCard>

      <SectionCard subtitle="Dynamic guidance surface" title="Daily Tips" testID="dashboard-daily-tips-card">
        {(recommendation?.daily_tips || dashboardSnapshot.tips).map((tip, index) => (
          <Text key={tip} style={styles.listItem} testID={`dashboard-daily-tip-${index + 1}`}>
            - {tip}
          </Text>
        ))}
      </SectionCard>

      <SectionCard subtitle="Personalized heart-friendly meals" title="Diet Plan" testID="dashboard-diet-plan-card">
        {(recommendation?.diet_plan || fallbackDietPlan).map((item, index) => (
          <Text key={item} style={styles.listItem} testID={`dashboard-diet-item-${index + 1}`}>
            - {item}
          </Text>
        ))}
      </SectionCard>

      <SectionCard subtitle="Reduce triggers that worsen the current profile" title="Foods To Avoid" testID="dashboard-foods-to-avoid-card">
        {(recommendation?.foods_to_avoid || fallbackFoodsToAvoid).map((item, index) => (
          <Text key={item} style={styles.listItem} testID={`dashboard-food-avoid-item-${index + 1}`}>
            - {item}
          </Text>
        ))}
      </SectionCard>

      <SectionCard subtitle="Guidance only, always confirm with a doctor" title="Medicine Guidance" testID="dashboard-medicine-guidance-card">
        {(recommendation?.medicine_guidance || fallbackMedicineGuidance).map((item, index) => (
          <Text key={item} style={styles.listItem} testID={`dashboard-medicine-guidance-item-${index + 1}`}>
            - {item}
          </Text>
        ))}
      </SectionCard>
    </Screen>
  );
}

function AssessmentScreen() {
  const { dashboard, submitAssessment, syncing } = useAppState();
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>(dashboard?.latest_assessment?.symptoms || ["chest pain", "fatigue"]);
  const [profile, setProfile] = useState<AssessmentFormState>({
    name: dashboard?.user.name || "",
    age: String(dashboard?.user.age || ""),
    gender: dashboard?.user.gender || "",
    location: dashboard?.user.location || "",
    contact: dashboard?.user.contact_number || "",
    bp: dashboard?.latest_assessment?.systolic_bp && dashboard?.latest_assessment?.diastolic_bp
      ? `${dashboard.latest_assessment.systolic_bp}/${dashboard.latest_assessment.diastolic_bp}`
      : "",
    heartRate: "",
    sugar: dashboard?.recent_daily_logs[0]?.blood_sugar ? String(dashboard.recent_daily_logs[0].blood_sugar) : "",
    cholesterol: dashboard?.latest_assessment?.cholesterol ? String(dashboard.latest_assessment.cholesterol) : "",
    height: "",
    weight: dashboard?.recent_daily_logs[0]?.weight_kg ? String(dashboard.recent_daily_logs[0].weight_kg) : "",
    history: "",
    medicines: "",
    familyHistory: "",
    smoking: "",
    alcohol: "",
    exercise: "",
    foodHabits: "",
    sleep: dashboard?.recent_daily_logs[0]?.sleep_hours ? String(dashboard.recent_daily_logs[0].sleep_hours) : "",
    stress: "",
  });

  const symptomChoices = ["chest pain", "dizziness", "fatigue", "shortness of breath", "sweating"];

  const toggleSymptom = (symptom: string) => {
    setSelectedSymptoms((current) =>
      current.includes(symptom) ? current.filter((item) => item !== symptom) : [...current, symptom],
    );
  };

  return (
    <Screen testID="screen-assessment">
      <Header eyebrow="All required inputs" title="Assessment Intake" testID="assessment-header" />
      <SectionCard subtitle="Name, age, gender, location, contact" title="Personal Details" testID="assessment-personal-details-card">
        <Field label="Full name" value={profile.name} onChangeText={(name) => setProfile({ ...profile, name })} testID="field-assessment-full-name" />
        <Field label="Age" value={profile.age} onChangeText={(age) => setProfile({ ...profile, age })} testID="field-assessment-age" />
        <Field label="Gender" value={profile.gender} onChangeText={(gender) => setProfile({ ...profile, gender })} testID="field-assessment-gender" />
        <Field label="Location" value={profile.location} onChangeText={(location) => setProfile({ ...profile, location })} testID="field-assessment-location" />
        <Field label="Contact number" value={profile.contact} onChangeText={(contact) => setProfile({ ...profile, contact })} testID="field-assessment-contact-number" />
      </SectionCard>

      <SectionCard subtitle="BP, heart rate, sugar, cholesterol, height, weight" title="Health Values" testID="assessment-health-values-card">
        <Field label="Blood pressure" placeholder="120/80" value={profile.bp} onChangeText={(bp) => setProfile({ ...profile, bp })} testID="field-assessment-blood-pressure" />
        <Field label="Heart rate" value={profile.heartRate} onChangeText={(heartRate) => setProfile({ ...profile, heartRate })} testID="field-assessment-heart-rate" />
        <Field label="Blood sugar" value={profile.sugar} onChangeText={(sugar) => setProfile({ ...profile, sugar })} testID="field-assessment-blood-sugar" />
        <Field label="Cholesterol" value={profile.cholesterol} onChangeText={(cholesterol) => setProfile({ ...profile, cholesterol })} testID="field-assessment-cholesterol" />
        <Field label="Height (cm)" value={profile.height} onChangeText={(height) => setProfile({ ...profile, height })} testID="field-assessment-height-cm" />
        <Field label="Weight (kg)" value={profile.weight} onChangeText={(weight) => setProfile({ ...profile, weight })} testID="field-assessment-weight-kg" />
      </SectionCard>

      <SectionCard subtitle="Tap every symptom that applies" title="Symptoms" testID="assessment-symptoms-card">
        <View style={styles.chipWrap}>
          {symptomChoices.map((symptom) => (
            <Pressable
              key={symptom}
              onPress={() => toggleSymptom(symptom)}
              style={[styles.chip, selectedSymptoms.includes(symptom) && styles.chipActive]}
              testID={makeTestId("chip-assessment-symptom", symptom)}
            >
              <Text style={[styles.chipText, selectedSymptoms.includes(symptom) && styles.chipTextActive]}>{symptom}</Text>
            </Pressable>
          ))}
        </View>
      </SectionCard>

      <SectionCard subtitle="Previous issues, surgeries, medicines, family history" title="Medical History" testID="assessment-medical-history-card">
        <Field label="Previous heart problems / surgeries" value={profile.history} onChangeText={(history) => setProfile({ ...profile, history })} testID="field-assessment-history" />
        <Field label="Current medicines" value={profile.medicines} onChangeText={(medicines) => setProfile({ ...profile, medicines })} testID="field-assessment-current-medicines" />
        <Field label="Family history" value={profile.familyHistory} onChangeText={(familyHistory) => setProfile({ ...profile, familyHistory })} testID="field-assessment-family-history" />
      </SectionCard>

      <SectionCard subtitle="Smoking, alcohol, exercise, food, sleep, stress" title="Lifestyle" testID="assessment-lifestyle-card">
        <Field label="Smoking" value={profile.smoking} onChangeText={(smoking) => setProfile({ ...profile, smoking })} testID="field-assessment-smoking" />
        <Field label="Alcohol" value={profile.alcohol} onChangeText={(alcohol) => setProfile({ ...profile, alcohol })} testID="field-assessment-alcohol" />
        <Field label="Exercise" value={profile.exercise} onChangeText={(exercise) => setProfile({ ...profile, exercise })} testID="field-assessment-exercise" />
        <Field label="Food habits" value={profile.foodHabits} onChangeText={(foodHabits) => setProfile({ ...profile, foodHabits })} testID="field-assessment-food-habits" />
        <Field label="Sleep hours" value={profile.sleep} onChangeText={(sleep) => setProfile({ ...profile, sleep })} testID="field-assessment-sleep-hours" />
        <Field label="Stress level" value={profile.stress} onChangeText={(stress) => setProfile({ ...profile, stress })} testID="field-assessment-stress-level" />
      </SectionCard>

      <PrimaryButton label={syncing ? "Submitting..." : "Submit Assessment"} onPress={() => void submitAssessment(profile, selectedSymptoms)} testID="assessment-submit-button" />
    </Screen>
  );
}

function ReportsScreen() {
  const { dashboard, latestReportMessage, uploadReport, syncing } = useAppState();
  const [reportType, setReportType] = useState("lipid_profile");

  return (
    <Screen testID="screen-reports">
      <Header eyebrow="PDF or image intake" title="Medical Reports" testID="reports-header" />
      <SectionCard subtitle="Supported uploads" title="Upload Center" testID="reports-upload-center-card">
        {["TMT report", "2D Echo", "Angiogram", "Lipid profile blood test"].map((item, index) => (
          <Text key={item} style={styles.listItem} testID={`reports-supported-upload-${index + 1}`}>
            - {item}
          </Text>
        ))}
        <Field label="Report type" value={reportType} onChangeText={setReportType} testID="field-reports-report-type" />
        <PrimaryButton label={syncing ? "Uploading..." : "Choose And Upload File"} onPress={() => void uploadReport(reportType)} testID="reports-upload-button" />
        <Text style={styles.helperText} testID="reports-upload-status">{latestReportMessage}</Text>
      </SectionCard>

      <SectionCard subtitle="Latest extracted findings" title="Document Intelligence" testID="reports-document-intelligence-card">
        {dashboard?.reports?.length ? (
          <>
            <Text style={styles.listItem} testID="reports-latest-file">- File: {dashboard.reports[0].file_name}</Text>
            <Text style={styles.listItem} testID="reports-latest-type">- Type: {dashboard.reports[0].report_type}</Text>
            <Text style={styles.listItem} testID="reports-latest-confidence">- Confidence: {Math.round(dashboard.reports[0].extraction_confidence * 100)}%</Text>
            <Text style={styles.helperText} testID="reports-latest-findings">{JSON.stringify(dashboard.reports[0].extracted_findings)}</Text>
          </>
        ) : (
          <>
            <Text style={styles.listItem} testID="reports-fallback-item-1">- Report type classification</Text>
            <Text style={styles.listItem} testID="reports-fallback-item-2">- Text extraction and parsing</Text>
            <Text style={styles.listItem} testID="reports-fallback-item-3">- Key lab and imaging findings</Text>
            <Text style={styles.listItem} testID="reports-fallback-item-4">- Confidence score before feeding the risk engine</Text>
          </>
        )}
      </SectionCard>
    </Screen>
  );
}

function TrackingScreen() {
  const { dashboard, submitDailyLog, syncing } = useAppState();
  const [daily, setDaily] = useState<DailyLogFormState>({
    bp: "",
    sugar: "",
    weight: "",
    steps: "",
    sleep: "",
  });
  const trendData = buildTrendData(dashboard?.recent_daily_logs);

  return (
    <Screen testID="screen-tracking">
      <Header eyebrow="Database-backed daily records" title="Daily Tracking" testID="tracking-header" />
      <SectionCard subtitle="BP, sugar, weight, steps, sleep" title="Today's Log" testID="tracking-todays-log-card">
        <Field label="Blood pressure" value={daily.bp} onChangeText={(bp) => setDaily({ ...daily, bp })} testID="field-tracking-blood-pressure" />
        <Field label="Blood sugar" value={daily.sugar} onChangeText={(sugar) => setDaily({ ...daily, sugar })} testID="field-tracking-blood-sugar" />
        <Field label="Weight" value={daily.weight} onChangeText={(weight) => setDaily({ ...daily, weight })} testID="field-tracking-weight" />
        <Field label="Steps" value={daily.steps} onChangeText={(steps) => setDaily({ ...daily, steps })} testID="field-tracking-steps" />
        <Field label="Sleep hours" value={daily.sleep} onChangeText={(sleep) => setDaily({ ...daily, sleep })} testID="field-tracking-sleep-hours" />
        <PrimaryButton label={syncing ? "Saving..." : "Save Daily Record"} onPress={() => void submitDailyLog(daily)} testID="tracking-save-daily-record-button" />
      </SectionCard>

      <SectionCard subtitle="Live progress graph from stored daily records" title="Progress Graph" testID="tracking-progress-graph-card">
        {trendData.map((item, index) => (
          <View key={item.key} style={styles.trendRow} testID={`tracking-progress-row-${index + 1}`}>
            <Text style={styles.trendDay}>{item.day}</Text>
            <View style={styles.trendBars}>
              <MiniBar color={palette.brand} value={item.bp} />
              <MiniBar color={palette.accent} value={item.sugar} />
              <MiniBar color={palette.cool} value={Math.round(item.weight * 10)} />
            </View>
          </View>
        ))}
        <Text style={styles.legend} testID="tracking-progress-legend">Teal: BP  Gold: Sugar  Blue: Weight trend</Text>
      </SectionCard>

      <SectionCard subtitle="Most recent records from backend SQLite storage" title="Recent Logs" testID="tracking-recent-logs-card">
        {(dashboard?.recent_daily_logs || []).map((log, index) => (
          <Text key={log.id} style={styles.listItem} testID={`tracking-recent-log-${index + 1}`}>
            - {log.log_date}: BP {log.systolic_bp || "--"}/{log.diastolic_bp || "--"}, Sugar {log.blood_sugar || "--"}, Steps {log.steps || "--"}, Sleep {log.sleep_hours || "--"}h
          </Text>
        ))}
        {!dashboard?.recent_daily_logs?.length && <Text style={styles.helperText} testID="tracking-no-recent-logs">Recent logs will appear here after you start tracking daily values.</Text>}
      </SectionCard>
    </Screen>
  );
}

function AssistantScreen() {
  const { messages, sendChat } = useAppState();
  const [draft, setDraft] = useState("");

  const submit = async () => {
    if (!draft.trim()) return;
    const next = draft;
    setDraft("");
    await sendChat(next);
  };

  return (
    <Screen testID="screen-assistant">
      <Header eyebrow="Real assistant surface" title="AI Chatbot" testID="assistant-header" />
      <SectionCard subtitle="Questions about risk, reports, diet, medicines, and tracking" title="Conversation" testID="assistant-conversation-card">
        {messages.map((message, index) => (
          <View key={message.id} style={[styles.chatBubble, message.role === "assistant" ? styles.assistantBubble : styles.userBubble]} testID={`assistant-message-${index + 1}-${message.role}`}>
            <Text
              style={message.role === "assistant" ? styles.assistantText : styles.userText}
              testID={`assistant-message-text-${index + 1}-${message.role}`}
            >
              {message.text}
            </Text>
          </View>
        ))}
        <TextInput
          onChangeText={setDraft}
          placeholder="Ask about symptoms, reports, diet, medicines, or next steps..."
          placeholderTextColor={palette.muted}
          style={styles.chatInput}
          value={draft}
          testID="assistant-chat-input"
        />
        <PrimaryButton label="Send Message" onPress={() => void submit()} testID="assistant-send-message-button" />
      </SectionCard>
    </Screen>
  );
}

function CareScreen() {
  const { careResults, dashboard, searchCare, syncing } = useAppState();
  const [manualLat, setManualLat] = useState(dashboard?.user.latitude ? String(dashboard.user.latitude) : "");
  const [manualLon, setManualLon] = useState(dashboard?.user.longitude ? String(dashboard.user.longitude) : "");
  const [locationLabel, setLocationLabel] = useState("Use GPS or manual coordinates for nearby care suggestions.");

  const getCurrentLocation = async () => {
    if (isE2EMode) {
      setManualLat(String(e2eCoordinates.latitude));
      setManualLon(String(e2eCoordinates.longitude));
      setLocationLabel(`${e2eCoordinates.latitude.toFixed(4)}, ${e2eCoordinates.longitude.toFixed(4)}`);
      await searchCare(e2eCoordinates.latitude, e2eCoordinates.longitude);
      return;
    }

    try {
      const currentPermission = await Location.getForegroundPermissionsAsync();
      const permission = currentPermission.status === "granted"
        ? currentPermission
        : await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        showAppAlert("Permission needed", "Location access is required for nearby hospital suggestions.");
        return;
      }
      const freshPosition = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const coords = freshPosition.coords || (await Location.getLastKnownPositionAsync())?.coords;
      if (!coords) {
        throw new Error("Unable to determine the current device location.");
      }
      setManualLat(String(coords.latitude));
      setManualLon(String(coords.longitude));
      setLocationLabel(`${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`);
      await searchCare(coords.latitude, coords.longitude);
    } catch (error) {
      showAppAlert("Location Error", String(error));
    }
  };

  const runManualSearch = async () => {
    const latitude = Number(manualLat);
    const longitude = Number(manualLon);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      showAppAlert("Invalid Coordinates", "Enter valid latitude and longitude values.");
      return;
    }
    setLocationLabel(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
    await searchCare(latitude, longitude);
  };

  return (
    <Screen testID="screen-care">
      <Header eyebrow="Nearby hospital and specialist suggestions" title="Care Finder" testID="care-header" />
      <SectionCard subtitle="Location-driven care suggestions" title="Location" testID="care-location-card">
        <Text style={styles.helperText} testID="care-location-label">{locationLabel}</Text>
        <Field label="Latitude" value={manualLat} onChangeText={setManualLat} testID="field-care-latitude" />
        <Field label="Longitude" value={manualLon} onChangeText={setManualLon} testID="field-care-longitude" />
        <PrimaryButton label="Search With Manual Coordinates" onPress={() => void runManualSearch()} testID="care-manual-search-button" />
        <PrimaryButton label={syncing ? "Locating..." : "Use Current GPS Location"} onPress={() => void getCurrentLocation()} testID="care-gps-search-button" />
      </SectionCard>

      <SectionCard subtitle="Closest options" title="Nearby Care" testID="care-nearby-care-card">
        {careResults.length ? (
          careResults.map((item, index) => (
            <View key={`${item.name}-${item.distance_km}`} style={styles.careRow} testID={`care-result-${index + 1}`}>
              <View style={{ flex: 1 }}>
                <Text style={styles.careTitle}>{item.name}</Text>
                <Text style={styles.helperText}>
                  {item.kind}  {item.distance_km.toFixed(2)} km
                </Text>
                {!!item.address && <Text style={styles.helperText}>{item.address}</Text>}
                {!!item.source && <Text style={styles.helperText}>Source: {item.source}</Text>}
              </View>
              <Ionicons color={palette.brand} name="navigate" size={18} />
            </View>
          ))
        ) : (
          <Text style={styles.helperText} testID="care-no-results">
            Search with GPS or manual coordinates to load nearby hospitals and heart specialists.
          </Text>
        )}
      </SectionCard>

      <SectionCard subtitle="Never bury urgent behavior" title="Emergency Action" testID="care-emergency-action-card">
        <Text style={styles.listItem} testID="care-emergency-action-1">- Show emergency banner when values are dangerous</Text>
        <Text style={styles.listItem} testID="care-emergency-action-2">- Surface nearest hospitals first</Text>
        <Text style={styles.listItem} testID="care-emergency-action-3">- Provide one-tap emergency contact actions</Text>
      </SectionCard>
    </Screen>
  );
}

function Screen({ children, testID }: { children: React.ReactNode; testID: string }) {
  const { backendIssue } = useAppState();

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea} testID={testID}>
      <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false} testID={`${testID}-scroll`}>
        {!!backendIssue && (
          <View style={styles.statusBanner} testID={`${testID}-backend-status`}>
            <Text style={styles.statusBannerTitle}>Backend Offline</Text>
            <Text style={styles.statusBannerText}>{backendIssue}</Text>
          </View>
        )}
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

function Header({ eyebrow, title, testID }: { eyebrow: string; title: string; testID?: string }) {
  return (
    <View style={styles.header} testID={testID || makeTestId("header", title)}>
      <Text style={styles.eyebrow}>{eyebrow}</Text>
      <Text style={styles.headerTitle}>{title}</Text>
    </View>
  );
}

function SectionCard({ children, subtitle, title, testID }: { children: React.ReactNode; subtitle: string; title: string; testID?: string }) {
  return (
    <View style={styles.card} testID={testID || makeTestId("card", title)}>
      <Text style={styles.cardEyebrow}>{subtitle}</Text>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Field(props: { label: string; placeholder?: string; value: string; onChangeText: (value: string) => void; testID?: string }) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{props.label}</Text>
      <TextInput
        onChangeText={props.onChangeText}
        placeholder={props.placeholder || props.label}
        placeholderTextColor={palette.muted}
        style={styles.input}
        value={props.value}
        testID={props.testID || makeTestId("field", props.label)}
      />
    </View>
  );
}

function PrimaryButton({
  label,
  onPress,
  compact = false,
  testID,
}: {
  label: string;
  onPress: () => void;
  compact?: boolean;
  testID?: string;
}) {
  return (
    <Pressable onPress={onPress} style={[styles.button, compact && styles.compactButton]} testID={testID || makeTestId("button", label)}>
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

function MiniBar({ color, value }: { color: string; value: number }) {
  return <View style={[styles.bar, { backgroundColor: color, width: `${Math.min(100, Math.max(18, value / 2))}%` }]} />;
}

export default function App() {
  const providers = useMemo(
    () => (
      <QueryClientProvider client={queryClient}>
        <SafeAreaProvider>
          <AppProvider>
            <AppShell />
          </AppProvider>
        </SafeAreaProvider>
      </QueryClientProvider>
    ),
    [],
  );

  return providers;
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: palette.background },
  loadingWrap: { flex: 1, backgroundColor: palette.background, alignItems: "center", justifyContent: "center", gap: 14, padding: 24 },
  container: { padding: 18, gap: 16, paddingBottom: 120 },
  statusBanner: { backgroundColor: "#FFF4E8", borderRadius: 18, borderWidth: 1, borderColor: "#F0C48A", padding: 14, gap: 6 },
  statusBannerTitle: { color: "#9A5200", fontSize: 16, fontWeight: "800" },
  statusBannerText: { color: "#8A4B00", lineHeight: 20 },
  tabBar: { height: 74, paddingTop: 8, paddingBottom: 10, backgroundColor: palette.surface, borderTopColor: palette.line },
  hero: { borderRadius: 28, padding: 22, gap: 18 },
  heroEyebrow: { color: "#CDE9E9", fontSize: 12, letterSpacing: 1.4, textTransform: "uppercase" },
  heroTitle: { color: "#FFFFFF", fontSize: 30, fontWeight: "800", lineHeight: 34 },
  heroCopy: { color: "#D9ECEC", fontSize: 14, lineHeight: 20 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  metricCard: { width: "47%", backgroundColor: palette.surface, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: palette.line },
  metricLabel: { color: palette.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.1 },
  metricValue: { marginTop: 8, fontSize: 22, fontWeight: "800", color: palette.ink },
  dangerText: { color: palette.danger },
  warningText: { color: palette.warning },
  coolText: { color: palette.cool },
  header: { gap: 6, paddingTop: 8 },
  eyebrow: { color: palette.brand, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: "700" },
  headerTitle: { color: palette.ink, fontSize: 30, fontWeight: "800" },
  card: {
    backgroundColor: palette.surface,
    borderRadius: 24,
    padding: 18,
    borderWidth: 1,
    borderColor: palette.line,
    shadowColor: palette.shadow,
    shadowOpacity: 1,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 2,
    gap: 12,
  },
  cardEyebrow: { color: palette.muted, fontSize: 12, letterSpacing: 1.1, textTransform: "uppercase" },
  cardTitle: { color: palette.ink, fontSize: 22, fontWeight: "800" },
  alertCard: { flexDirection: "row", alignItems: "flex-start", gap: 10, backgroundColor: "#FFF4F2", padding: 12, borderRadius: 18 },
  alertText: { color: palette.ink, flex: 1, lineHeight: 20 },
  trendRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  trendDay: { width: 40, color: palette.ink, fontWeight: "700" },
  trendBars: { flex: 1, gap: 6 },
  bar: { height: 8, borderRadius: 999 },
  legend: { color: palette.muted, marginTop: 4 },
  listItem: { color: palette.ink, lineHeight: 22 },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  chip: { borderWidth: 1, borderColor: palette.line, backgroundColor: "#F9FBF7", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 999 },
  chipActive: { backgroundColor: palette.brand, borderColor: palette.brand },
  chipText: { color: palette.ink, fontWeight: "600" },
  chipTextActive: { color: "#FFFFFF" },
  fieldWrap: { gap: 6 },
  fieldLabel: { color: palette.ink, fontWeight: "700" },
  input: { backgroundColor: "#F8FAF6", borderWidth: 1, borderColor: palette.line, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 12, color: palette.ink },
  button: { backgroundColor: palette.brandDeep, paddingHorizontal: 16, paddingVertical: 14, borderRadius: 18, alignItems: "center", marginTop: 6 },
  compactButton: { alignSelf: "flex-start", minWidth: 100 },
  buttonText: { color: "#FFFFFF", fontWeight: "800", letterSpacing: 0.3 },
  helperText: { color: palette.muted, lineHeight: 20 },
  chatBubble: { padding: 14, borderRadius: 18 },
  assistantBubble: { backgroundColor: "#F0F6F4" },
  userBubble: { backgroundColor: palette.brandDeep },
  assistantText: { color: palette.ink, lineHeight: 20 },
  userText: { color: "#FFFFFF", lineHeight: 20 },
  chatInput: { backgroundColor: "#F8FAF6", borderWidth: 1, borderColor: palette.line, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 12, color: palette.ink, minHeight: 52 },
  careRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.line, gap: 12 },
  careTitle: { color: palette.ink, fontWeight: "700" },
});
