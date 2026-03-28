import "react-native-gesture-handler";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
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
import { NavigationContainer, useNavigation } from "@react-navigation/native";
import { createBottomTabNavigator, BottomTabNavigationProp } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator, NativeStackNavigationProp } from "@react-navigation/native-stack";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import { LinearGradient } from "expo-linear-gradient";
import Svg, { Circle, Path, Line, Text as TextSvg } from "react-native-svg";
import * as DocumentPicker from "expo-document-picker";
import { File, Paths } from "expo-file-system";
import * as Location from "expo-location";

import { dashboardSnapshot, initialChat } from "./src/data/mock";
import { palette } from "./src/theme";
import { storage } from "./src/utils/storage";

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();
const queryClient = new QueryClient();
const backendHealthTimeoutMs = 5000;
const requestTimeoutMs = 12000;
const uploadRequestTimeoutMs = 20000;
const tokenKey = "heartguard-auth-token";
const userIdKey = "heartguard-user-id";
const isE2EMode = process.env.EXPO_PUBLIC_E2E_MODE === "1";

type RootStackParamList = { Login: undefined; Signup: undefined; Main: undefined };
type MainTabParamList = {
  Dashboard: undefined;
  Assessment: undefined;
  Reports: undefined;
  Tracking: undefined;
  Assistant: undefined;
  Care: undefined;
  Profile: undefined;
};
type AuthStackNav = NativeStackNavigationProp<RootStackParamList>;
type MainTabNav = BottomTabNavigationProp<MainTabParamList>;
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

  // On Web, default to the current host (good for both localhost and LAN IP access)
  if (Platform.OS === "web" && typeof window !== "undefined") {
    const host = window.location.hostname;
    return `http://${host}:8000/api/v1`;
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

type PastPrediction = {
  id: string;
  risk_score: number;
  risk_level: string;
  confidence: number;
  explanation: string[];
  created_at: string;
};

type DashboardPayload = {
  user: {
    id: string;
    name: string;
    age: number;
    gender: string;
    location: string;
    contact_number: string;
    email: string;
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
    created_at: string;
  } | null;
  latest_prediction?: PastPrediction | null;
  latest_recommendation?: {
    diet_plan: string[];
    foods_to_avoid: string[];
    medicine_guidance: string[];
    daily_tips: string[];
  } | null;
  active_alerts: Array<{
    id: string;
    title: string;
    message: string;
    severity?: string;
  }>;
  recent_daily_logs: Array<{
    id: string;
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
    id: string;
    report_type: string;
    file_name: string;
    extracted_findings: Record<string, unknown>;
    extraction_confidence: number;
  }>;
  past_predictions: Array<PastPrediction>;
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
  hasHistory: "no" | "yes";
  history: string;
  hasMedicines: "no" | "yes";
  medicines: string;
  hasFamilyHistory: "no" | "yes";
  familyHistory: string;
  smoking: "no" | "yes";
  alcohol: "no" | "yes";
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
  userId: string | null;
  dashboard: DashboardPayload | null;
  careResults: CareLocation[];
  messages: ChatMessage[];
  loading: boolean;
  syncing: boolean;
  backendIssue: string | null;
  latestReportMessage: string;
  isAuthenticated: boolean;
  refreshDashboard: () => Promise<void>;
  submitAssessment: (payload: AssessmentFormState, selectedSymptoms: string[], onSuccess?: () => void) => Promise<void>;
  submitDailyLog: (payload: DailyLogFormState, logDate: string) => Promise<void>;
  sendChat: (message: string) => Promise<void>;
  uploadReport: (reportType: string) => Promise<void>;
  searchCare: (latitude: number, longitude: number) => Promise<void>;
  loginUser: (email: string, password: string) => Promise<void>;
  signupUser: (data: SignupData) => Promise<void>;
  logoutUser: () => Promise<void>;
};

type SignupData = {
  email: string;
  password: string;
  name: string;
  age: string;
  gender: string;
  location: string;
  contact: string;
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

async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await storage.get(tokenKey);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const response = await fetchWithTimeout(`${apiBaseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders, ...(options?.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    let errorMessage = `Request failed with ${response.status}`;
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch {
      try {
        errorMessage = await response.text();
      } catch {
        // Fallback to default
      }
    }
    throw new Error(errorMessage);
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
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
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
  Alert.alert(title, message, [{ text: "OK" }]);
}

function HeartTrendGraph({ points }: { points: TrendPoint[] }) {
  if (!points || points.length < 2) return null;
  const maxVal = Math.max(...points.map((p) => Math.max(p.bp, p.sugar)), 160);
  const width = 300;
  const height = 100;
  const padding = 10;

  const getX = (i: number) => padding + (i * (width - 2 * padding)) / (points.length - 1);
  const getY = (v: number) => height - padding - (v / maxVal) * (height - 2 * padding);

  const bpPath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${getX(i)} ${getY(p.bp)}`).join(" ");
  const sugarPath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${getX(i)} ${getY(p.sugar)}`).join(" ");

  return (
    <View style={styles.trendGraph}>
      <Svg height={height} width={width}>
        <Path d={bpPath} fill="none" stroke={palette.brand} strokeWidth="3" />
        <Path d={sugarPath} fill="none" stroke={palette.accent} strokeWidth="3" />
        {points.map((p, i) => (
          <React.Fragment key={p.key}>
            <Circle cx={getX(i)} cy={getY(p.bp)} r="3" fill={palette.brand} />
            <Circle cx={getX(i)} cy={getY(p.sugar)} r="3" fill={palette.accent} />
          </React.Fragment>
        ))}
      </Svg>
    </View>
  );
}

function ProgressRing({ percent, color = palette.brand, size = 40 }: { percent: number; color?: string; size?: number }) {
  const radius = size / 2 - 4;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.min(percent, 100) / 100) * circumference;
  return (
    <Svg height={size} width={size}>
      <Circle cx={size / 2} cy={size / 2} r={radius} stroke="rgba(0,0,0,0.05)" strokeWidth="4" fill="none" />
      <Circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        stroke={color}
        strokeWidth="4"
        fill="none"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </Svg>
  );
}

function MiniBarChart({ value, max = 10, color = palette.cool }: { value: number; max?: number; color?: string }) {
  const width = 60;
  const height = 8;
  const barWidth = (Math.min(value, max) / max) * width;
  return (
    <View style={{ width, height, backgroundColor: "rgba(0,0,0,0.05)", borderRadius: 4, overflow: "hidden" }}>
      <View style={{ width: barWidth, height: "100%", backgroundColor: color }} />
    </View>
  );
}

function TrendSparkline({ points, color = palette.brand }: { points: number[]; color?: string }) {
  if (points.length < 2) return null;
  const width = 60;
  const height = 24;
  const max = Math.max(...points, 1);
  const min = Math.min(...points);
  const range = max - min || 1;
  const getX = (i: number) => (i * width) / (points.length - 1);
  const getY = (v: number) => height - ((v - min) / range) * height;
  const path = points.map((v, i) => `${i === 0 ? "M" : "L"} ${getX(i)} ${getY(v)}`).join(" ");
  return (
    <Svg height={height} width={width}>
      <Path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function TrendLineGraph({ points, color = palette.brand, height = 120, maxScale = 100, xLabels = [] }: { points: number[]; color?: string; height?: number; maxScale?: number; xLabels?: string[] }) {
  const width = 320;
  const paddingX = 40;
  const paddingY = 20;
  if (!points.length) return <Text style={styles.helperText}>No data for trend</Text>;
  
  const max = Math.max(...points, maxScale);
  const min = 0;
  const range = max - min || 1;
  
  const graphWidth = width - paddingX - 10;
  const graphHeight = height - paddingY * 2;
  
  const getX = (i: number) => paddingX + (i * graphWidth) / Math.max(points.length - 1, 1);
  const getY = (v: number) => height - paddingY - ((v - min) / range) * graphHeight;
  
  const linePath = points.map((v, i) => `${i === 0 ? "M" : "L"} ${getX(i)} ${getY(v)}`).join(" ");
  const areaPath = `${linePath} L ${getX(points.length - 1)} ${height - paddingY} L ${getX(0)} ${height - paddingY} Z`;
  
  const yAxisTicks = [0, Math.round(max / 2), Math.round(max)];

  return (
    <View style={{ height: height + 20, width, marginBottom: 10 }}>
      <Svg height={height + 20} width={width}>
        {/* Grid Lines */}
        {yAxisTicks.map((tick, i) => (
          <React.Fragment key={i}>
            <Line x1={paddingX} y1={getY(tick)} x2={width - 10} y2={getY(tick)} stroke="rgba(0,0,0,0.05)" strokeWidth="1" />
            <TextSvg x={5} y={getY(tick) + 4} fontSize="10" fill="rgba(0,0,0,0.4)" fontWeight="600">{tick}</TextSvg>
          </React.Fragment>
        ))}
        
        {/* Area Fill */}
        <Path d={areaPath} fill={color} opacity="0.1" />
        
        {/* Line Path */}
        <Path d={linePath} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        
        {/* Data Points */}
        {points.map((v, i) => (
          <React.Fragment key={i}>
            <Circle cx={getX(i)} cy={getY(v)} r="4" fill={color} />
            {/* Show label only for extremes or last point */}
            {(i === points.length - 1 || v === Math.max(...points)) && (
              <TextSvg x={getX(i) - 10} y={getY(v) - 10} fontSize="10" fill={color} fontWeight="bold">{v}</TextSvg>
            )}
            {/* X Axis Labels */}
            {xLabels[i] && (
              <TextSvg x={getX(i) - 10} y={height - 5} fontSize="9" fill="rgba(0,0,0,0.4)" fontWeight="600">{xLabels[i]}</TextSvg>
            )}
          </React.Fragment>
        ))}
      </Svg>
    </View>
  );
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
  const [userId, setUserId] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [careResults, setCareResults] = useState<CareLocation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>(initialChat);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [backendIssue, setBackendIssue] = useState<string | null>(null);
  const [latestReportMessage, setLatestReportMessage] = useState("No report uploaded yet.");

  const loadChatHistory = async (nextUserId: string) => {
    try {
      const history = await fetchJson<Array<{ id: string; role: "assistant" | "user"; content: string }>>(
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

  const loginUser = async (email: string, password: string): Promise<void> => {
    const payload = await fetchJson<{ access_token: string; user_id: string; name: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    await storage.set(tokenKey, payload.access_token);
    await storage.set(userIdKey, payload.user_id);
    setUserId(payload.user_id);
    setIsAuthenticated(true);
    const dashboard = await fetchJson<DashboardPayload>(`/users/${payload.user_id}/dashboard`);
    setDashboard(dashboard);
    setBackendIssue(null);
    showCriticalAlerts(dashboard);
    await loadChatHistory(payload.user_id);
  };

  const signupUser = async (data: SignupData): Promise<void> => {
    const payload = await fetchJson<{ access_token: string; user_id: string; name: string }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        email: data.email,
        password: data.password,
        name: data.name,
        age: Number(data.age) || 30,
        gender: data.gender || "Male",
        location: data.location,
        contact_number: data.contact,
      }),
    });
    await storage.set(tokenKey, payload.access_token);
    await storage.set(userIdKey, payload.user_id);
    setUserId(payload.user_id);
    setIsAuthenticated(true);
    setDashboard(null);
    setBackendIssue(null);
  };

  const logoutUser = async (): Promise<void> => {
    await storage.remove(tokenKey);
    await storage.set(userIdKey, "");
    setUserId(null);
    setIsAuthenticated(false);
    setDashboard(null);
    setMessages(initialChat);
  };

  const refreshDashboard = async () => {
    if (!userId) return;
    const nextDashboard = await fetchJson<DashboardPayload>(`/users/${userId}/dashboard`);
    setDashboard(nextDashboard);
    setBackendIssue(null);
    showCriticalAlerts(nextDashboard);
  };

  useEffect(() => {
    const bootstrap = async () => {
      try {
        await checkBackendHealth();
        const storedToken = await storage.get(tokenKey);
        const storedUserId = await storage.get(userIdKey);
        if (storedToken && storedUserId) {
          setUserId(storedUserId);
          setIsAuthenticated(true);
          try {
            const nextDashboard = await fetchJson<DashboardPayload>(`/users/${storedUserId}/dashboard`);
            setDashboard(nextDashboard);
            showCriticalAlerts(nextDashboard);
            await loadChatHistory(storedUserId);
          } catch {
            // Token may be expired — force re-login
            await storage.remove(tokenKey);
            setIsAuthenticated(false);
            setUserId(null);
          }
        }
      } catch (error) {
        setBackendIssue(formatAppError(error));
      } finally {
        setLoading(false);
      }
    };
    void bootstrap();
  }, []);

  const submitAssessment = async (
    payload: AssessmentFormState,
    selectedSymptoms: string[],
    onSuccess?: () => void,
  ) => {
    if (!userId) return;
    setSyncing(true);
    try {
      const activeUserId = userId;
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
            previous_heart_problems: payload.hasHistory === "yes",
            surgeries: payload.hasHistory === "yes" ? payload.history : "",
            current_medicines: payload.hasMedicines === "yes" ? payload.medicines : "",
            family_history: payload.hasFamilyHistory === "yes",
            family_history_details: payload.hasFamilyHistory === "yes" ? payload.familyHistory : "",
            diabetes: Number(payload.sugar) >= 126,
            hypertension: (bp.systolic || 0) >= 140 || (bp.diastolic || 0) >= 90,
          },
          lifestyle: {
            smoking: payload.smoking === "yes",
            alcohol: payload.alcohol === "yes",
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
      if (onSuccess) onSuccess();
    } catch (error) {
      showAppAlert("Assessment Error", formatAppError(error));
    } finally {
      setSyncing(false);
    }
  };

  const submitDailyLog = async (payload: DailyLogFormState, logDate: string) => {
    if (!userId) return;
    setSyncing(true);
    try {
      const activeUserId = userId;
      const bp = parseBp(payload.bp);
      const cleanNum = (val: string) => Number(val.replace(/[^0-9.]/g, "")) || null;

      const createdLog = await fetchJson<DailyLogEntry>(`/users/${activeUserId}/daily-logs`, {
        method: "POST",
        body: JSON.stringify({
          log_date: logDate,
          systolic_bp: bp.systolic,
          diastolic_bp: bp.diastolic,
          blood_sugar: cleanNum(payload.sugar),
          weight_kg: cleanNum(payload.weight),
          steps: cleanNum(payload.steps),
          sleep_hours: cleanNum(payload.sleep),
          notes: "Logged from mobile tracking screen.",
        }),
      });

      setDashboard((current) => {
        if (!current) return current;
        const recentDailyLogs = [createdLog, ...current.recent_daily_logs.filter((item) => item.id !== createdLog.id)]
          .sort(compareDailyLogs)
          .slice(0, 31);
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
    if (!message.trim() || !userId) return;
    const userMessage: ChatMessage = { id: `${Date.now()}-user`, role: "user", text: message.trim() };
    setMessages((current) => [...current, userMessage]);
    try {
      const activeUserId = userId;
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
    if (!userId) return;
    setSyncing(true);
    try {
      const activeUserId = userId;
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
      const authHeaders = await getAuthHeaders();
      const response = await fetchWithTimeout(
        `${apiBaseUrl}/users/${activeUserId}/reports/upload`,
        { method: "POST", body: form, headers: authHeaders },
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
    if (!userId) return;
    setSyncing(true);
    try {
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
      isAuthenticated,
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
      loginUser,
      signupUser,
      logoutUser,
    }),
    [userId, isAuthenticated, dashboard, careResults, messages, loading, syncing, backendIssue, latestReportMessage],
  );

  return <AppStateContext.Provider value={contextValue}>{children}</AppStateContext.Provider>;
}

function MainTabs() {
  return (
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
            Profile: "person-circle",
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
      <Tab.Screen component={ProfileScreen} name="Profile" />
    </Tab.Navigator>
  );
}

function AppShell() {
  const { loading, isAuthenticated } = useAppState();

  if (loading) {
    return (
      <SafeAreaView edges={["top"]} style={styles.loadingWrap} testID="app-loading">
        <ActivityIndicator color={palette.brand} size="large" testID="app-loading-spinner" />
        <Text style={styles.helperText}>Checking your session...</Text>
      </SafeAreaView>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar barStyle="dark-content" />
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {isAuthenticated ? (
          <Stack.Screen component={MainTabs} name="Main" />
        ) : (
          <>
            <Stack.Screen component={LoginScreen} name="Login" />
            <Stack.Screen component={SignupScreen} name="Signup" />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

// ─── Auth Screens ─────────────────────────────────────────────────────────────

function LoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { loginUser, backendIssue } = useAppState();
  const nav = useNavigation<AuthStackNav>();

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert("Missing fields", "Please enter your email and password.");
      return;
    }
    setBusy(true);
    try {
      await loginUser(email.trim().toLowerCase(), password);
    } catch (err) {
      Alert.alert("Login failed", formatAppError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.authContainer} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, justifyContent: "center" }}>
        <ScrollView contentContainerStyle={styles.authScroll} keyboardShouldPersistTaps="handled">
          <LinearGradient colors={["#0C6D70", "#0B4B54"]} style={styles.authHero}>
            <Ionicons color="#fff" name="heart" size={48} />
            <Text style={styles.authAppName}>HeartGuard AI</Text>
            <Text style={styles.authTagline}>Your personal heart health companion</Text>
          </LinearGradient>

          <View style={styles.authCard}>
            <Text style={styles.authTitle}>Welcome back</Text>
            {backendIssue ? <Text style={styles.authError}>{backendIssue}</Text> : null}
            <TextInput
              autoCapitalize="none"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="Email address"
              placeholderTextColor={palette.muted}
              style={styles.authInput}
              testID="login-email"
              value={email}
            />
            <TextInput
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor={palette.muted}
              secureTextEntry
              style={styles.authInput}
              testID="login-password"
              value={password}
            />
            <Pressable
              disabled={busy}
              onPress={() => void handleLogin()}
              style={({ pressed }) => [styles.authPrimaryBtn, pressed && { opacity: 0.8 }]}
              testID="login-submit"
            >
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.authPrimaryBtnText}>Sign In</Text>
              )}
            </Pressable>
            <Pressable onPress={() => nav.navigate("Signup")} style={styles.authSecondaryBtn} testID="go-signup">
              <Text style={styles.authSecondaryBtnText}>Don't have an account? <Text style={{ color: palette.brand, fontWeight: "700" }}>Sign Up</Text></Text>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function SignupScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("Male");
  const [location, setLocation] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const { signupUser } = useAppState();
  const nav = useNavigation<AuthStackNav>();

  const handleSignup = async () => {
    if (!email.trim() || !password.trim() || !name.trim()) {
      Alert.alert("Missing fields", "Name, email, and password are required.");
      return;
    }
    if (password !== confirmPassword) {
      Alert.alert("Password mismatch", "Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await signupUser({ email: email.trim().toLowerCase(), password, name: name.trim(), age, gender, location: location.trim(), contact: contact.trim() });
    } catch (err) {
      Alert.alert("Signup failed", formatAppError(err));
    } finally {
      setBusy(false);
    }
  };

  const genderOptions = ["Male", "Female", "Other"];

  return (
    <SafeAreaView style={styles.authContainer} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.authScroll} keyboardShouldPersistTaps="handled">
          <LinearGradient colors={["#0C6D70", "#0B4B54"]} style={[styles.authHero, { paddingVertical: 28 }]}>
            <Ionicons color="#fff" name="person-add" size={36} />
            <Text style={styles.authAppName}>Create Account</Text>
          </LinearGradient>

          <View style={styles.authCard}>
            <Text style={styles.authTitle}>Your health profile</Text>
            <Text style={styles.authSectionLabel}>Account Details</Text>
            {(["Full Name", "Email", "Password", "Confirm Password"] as const).map((label) => {
              const valueMap: Record<string, string> = { "Full Name": name, Email: email, Password: password, "Confirm Password": confirmPassword };
              const setterMap: Record<string, (v: string) => void> = { "Full Name": setName, Email: setEmail, Password: setPassword, "Confirm Password": setConfirmPassword };
              return (
                <TextInput
                  key={label}
                  autoCapitalize={label === "Full Name" ? "words" : "none"}
                  keyboardType={label === "Email" ? "email-address" : "default"}
                  onChangeText={setterMap[label]}
                  placeholder={label}
                  placeholderTextColor={palette.muted}
                  secureTextEntry={label === "Password" || label === "Confirm Password"}
                  style={styles.authInput}
                  testID={`signup-${label.toLowerCase().replace(/ /g, "-")}`}
                  value={valueMap[label]}
                />
              );
            })}

            <Text style={styles.authSectionLabel}>Personal Details</Text>
            <TextInput
              keyboardType="phone-pad"
              onChangeText={setAge}
              placeholder="Age"
              placeholderTextColor={palette.muted}
              style={styles.authInput}
              testID="signup-age"
              value={age}
            />
            <View style={styles.genderRow}>
              {genderOptions.map((opt) => (
                <Pressable
                  key={opt}
                  onPress={() => setGender(opt)}
                  style={[styles.genderBtn, gender === opt && styles.genderBtnActive]}
                  testID={`signup-gender-${opt.toLowerCase()}`}
                >
                  <Text style={[styles.genderBtnText, gender === opt && styles.genderBtnTextActive]}>{opt}</Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              onChangeText={setLocation}
              placeholder="City / Location"
              placeholderTextColor={palette.muted}
              style={styles.authInput}
              testID="signup-location"
              value={location}
            />
            <TextInput
              keyboardType="phone-pad"
              onChangeText={setContact}
              placeholder="Phone number (optional)"
              placeholderTextColor={palette.muted}
              style={styles.authInput}
              testID="signup-contact"
              value={contact}
            />

            <Pressable
              disabled={busy}
              onPress={() => void handleSignup()}
              style={({ pressed }) => [styles.authPrimaryBtn, pressed && { opacity: 0.8 }]}
              testID="signup-submit"
            >
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.authPrimaryBtnText}>Create Account</Text>
              )}
            </Pressable>
            <Pressable onPress={() => nav.goBack()} style={styles.authSecondaryBtn} testID="go-login">
              <Text style={styles.authSecondaryBtnText}>Already have an account? <Text style={{ color: palette.brand, fontWeight: "700" }}>Sign In</Text></Text>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function DashboardScreen() {
  const navigation = useNavigation<MainTabNav>();
  const { dashboard, refreshDashboard, syncing, logoutUser } = useAppState();
  const logs = dashboard?.recent_daily_logs || [];
  
  const calculateAverage = (key: keyof DailyLogEntry) => {
    const validLogs = logs.filter(l => l[key] !== undefined && l[key] !== null);
    if (!validLogs.length) return null;
    const sum = validLogs.reduce((acc, current) => acc + (Number(current[key]) || 0), 0);
    return Math.round(sum / validLogs.length);
  };

  const avgSys = calculateAverage("systolic_bp");
  const avgDia = calculateAverage("diastolic_bp");
  const avgSugar = calculateAverage("blood_sugar");
  const avgSleep = calculateAverage("sleep_hours");
  const avgSteps = calculateAverage("steps");

  const getStatusColor = (label: string, value: number | string | null) => {
    if (value === null || value === "--") return palette.ink;
    const num = Number(value);
    if (label === "BP") {
      const [sys, dia] = String(value).split("/").map(Number);
      if (sys > 140 || dia > 90) return palette.danger;
      if (sys < 120 && dia < 80) return "#2e7d32"; // Green
    }
    if (label === "Sugar") {
      if (num > 140) return palette.danger;
      if (num < 100) return "#2e7d32"; // Green
    }
    if (label === "BMI") {
      if (num > 30) return palette.danger;
      if (num >= 18.5 && num <= 24.9) return "#2e7d32"; // Green
    }
    return palette.ink;
  };

  const prediction = dashboard?.latest_prediction;
  const assessment = dashboard?.latest_assessment;
  const recommendation = dashboard?.latest_recommendation;
  const hasAssessment = !!assessment;

  const metricCards = [
    {
      label: "BP",
      value: (avgSys && avgDia) ? `${avgSys}/${avgDia}` : "--",
      tone: "danger",
      color: getStatusColor("BP", (avgSys && avgDia) ? `${avgSys}/${avgDia}` : null),
      viz: <TrendSparkline color={palette.danger} points={logs.map(l => l.systolic_bp || 120).reverse() || []} />
    },
    {
      label: "Sugar",
      value: avgSugar ? `${avgSugar}` : "--",
      tone: "warning",
      color: getStatusColor("Sugar", avgSugar),
      viz: <TrendSparkline color={palette.accent} points={logs.map(l => l.blood_sugar || 90).reverse() || []} />
    },
    { 
      label: "BMI", 
      value: assessment?.bmi ? `${Number(assessment.bmi).toFixed(2)}` : "--", 
      tone: "warning",
      color: getStatusColor("BMI", assessment?.bmi || null),
      viz: <MiniBarChart color={palette.accent} max={40} value={assessment?.bmi || 0} />
    },
    { 
      label: "Sleep", 
      value: avgSleep ? `${avgSleep}h` : "--", 
      tone: "cool",
      color: palette.ink,
      viz: <MiniBarChart color={palette.cool} max={12} value={avgSleep || 0} />
    },
    {
      label: "Steps",
      value: avgSteps ? `${avgSteps}` : "--",
      tone: "cool",
      color: palette.ink,
      viz: (
        <View style={{ alignItems: "center" }}>
          <ProgressRing percent={((avgSteps || 0) / 10000) * 100} size={48} />
          <View style={{ flexDirection: "row", gap: 8, marginTop: 4 }}>
             <Text style={{ fontSize: 9, color: "rgba(0,0,0,0.4)" }}>🔥 {Math.round((avgSteps || 0) * 0.04)} Kcal</Text>
             <Text style={{ fontSize: 9, color: "rgba(0,0,0,0.4)" }}>📍 {((avgSteps || 0) * 0.0005).toFixed(1)} Mi</Text>
          </View>
        </View>
      )
    }
  ];

  return (
    <Screen testID="screen-dashboard">
      <LinearGradient colors={[palette.brandDeep, palette.brand]} style={styles.hero}>
        <View style={{ flex: 1, gap: 12 }}>
          <Text style={styles.heroEyebrow}>{hasAssessment ? "HEART HEALTH OVERVIEW" : "GETTING STARTED"}</Text>
          <Text style={styles.heroTitle} testID="dashboard-hero-title">
            Hello, {dashboard?.user?.name || "User"} 👋
          </Text>
          <Text style={styles.heroCopy}>
            {hasAssessment
              ? "Your current AI risk profile and latest health metrics."
              : "Complete your first assessment to activate your personalized AI heart risk profile."}
          </Text>
          <PrimaryButton compact label="Refresh" onPress={() => void refreshDashboard()} testID="dashboard-refresh-button" />
        </View>
        <Pressable onPress={() => void logoutUser()} style={styles.logoutBtn} testID="dashboard-logout-button">
          <Ionicons color="rgba(255,255,255,0.85)" name="log-out-outline" size={16} />
        </Pressable>
      </LinearGradient>

      {!hasAssessment && (
        <View style={{ padding: 16 }}>
          <SectionCard title="Getting Started" subtitle="Follow these steps to activate your profile">
            <View style={{ gap: 12 }}>
              <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
                <Ionicons name="checkmark-circle-outline" size={24} color={palette.brand} />
                <Text style={styles.inkText}>Account Created</Text>
              </View>
              <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
                <Ionicons name="ellipse-outline" size={24} color={palette.line} />
                <Text style={styles.inkText}>Complete First Assessment</Text>
              </View>
               <PrimaryButton label="Take Assessment Now" onPress={() => navigation.navigate("Assessment")} />
            </View>
          </SectionCard>
        </View>
      )}

      {hasAssessment && (
        <>
          <View style={styles.metricGrid} testID="dashboard-metric-grid">
            {metricCards.map((metric: any) => (
              <View key={metric.label} style={styles.metricCard} testID={`dashboard-metric-${toTestIdSegment(metric.label)}`}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 8 }}>
                  <Text style={styles.metricLabel}>{metric.label}</Text>
                  {metric.viz}
                </View>
                <Text
                  style={[
                    styles.metricValue,
                    { color: metric.color },
                  ]}
                  testID={`dashboard-metric-value-${toTestIdSegment(metric.label)}`}
                >
                  {metric.value}
                </Text>
              </View>
            ))}
          </View>
        </>
      )}

      {hasAssessment && dashboard?.reports && dashboard.reports.length > 0 && (
        <SectionCard subtitle="Latest assessment from medical records" title="Report Extraction Result" testID="dashboard-report-result-card">
          <View style={styles.alertCard}>
            <Ionicons name="document-text" size={20} color={palette.brand} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: "700", color: palette.ink }}>{dashboard.reports[0].report_type}</Text>
              <Text style={styles.helperText} numberOfLines={2}>
                {JSON.stringify(dashboard.reports[0].extracted_findings)}
              </Text>
            </View>
          </View>
        </SectionCard>
      )}

      {hasAssessment && (
        <>
          <SectionCard subtitle="Dynamic guidance surface" title="Daily Tips" testID="dashboard-daily-tips-card">
            {(recommendation?.daily_tips || fallbackDietPlan).slice(0, 3).map((tip: string, index: number) => (
              <Text key={tip} style={styles.listItem} testID={`dashboard-daily-tip-${index + 1}`}>
                - {tip}
              </Text>
            ))}
          </SectionCard>

          <SectionCard subtitle="Personalized heart-friendly meals" title="Diet Plan" testID="dashboard-diet-plan-card">
            {(recommendation?.diet_plan || fallbackDietPlan).map((item: string, index: number) => (
              <Text key={item} style={styles.listItem} testID={`dashboard-diet-item-${index + 1}`}>
                - {item}
              </Text>
            ))}
          </SectionCard>

          <SectionCard subtitle="Reduce triggers that worsen the current profile" title="Foods To Avoid" testID="dashboard-foods-to-avoid-card">
            {(recommendation?.foods_to_avoid || fallbackFoodsToAvoid).map((item: string, index: number) => (
              <Text key={item} style={styles.listItem} testID={`dashboard-food-avoid-item-${index + 1}`}>
                - {item}
              </Text>
            ))}
          </SectionCard>
        </>
      )}
    </Screen>
  );
}


function AssessmentScreen() {
  const navigation = useNavigation<AuthStackNav>();
  const { dashboard, submitAssessment, syncing } = useAppState();
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [profile, setProfile] = useState<AssessmentFormState>({
    name: dashboard?.user.name || "",
    age: String(dashboard?.user.age || ""),
    gender: dashboard?.user.gender || "",
    location: dashboard?.user.location || "",
    contact: dashboard?.user.contact_number || "",
    bp: "",
    heartRate: "",
    sugar: "",
    cholesterol: "",
    height: "",
    weight: "",
    hasHistory: "no",
    history: "",
    hasMedicines: "no",
    medicines: "",
    hasFamilyHistory: "no",
    familyHistory: "",
    smoking: "no",
    alcohol: "no",
    exercise: "30 mins/day",
    foodHabits: "Normal",
    sleep: "8",
    stress: "Low",
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
      <SectionCard subtitle="Prefilled from your profile" title="Personal Details" testID="assessment-personal-details-card">
        <Field label="Full name" value={profile.name} onChangeText={(name) => setProfile({ ...profile, name })} testID="field-assessment-full-name" />
        <View style={{ flexDirection: "row", gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Field label="Age" value={profile.age} onChangeText={(age) => setProfile({ ...profile, age })} testID="field-assessment-age" />
          </View>
          <View style={{ flex: 1 }}>
            <Field label="Gender" value={profile.gender} onChangeText={(gender) => setProfile({ ...profile, gender })} testID="field-assessment-gender" />
          </View>
        </View>
      </SectionCard>

      <SectionCard subtitle="BP, heart rate, sugar, cholesterol, height, weight" title="Health Values" testID="assessment-health-values-card">
        <Field label="Blood pressure" placeholder="120/80" value={profile.bp} onChangeText={(bp) => setProfile({ ...profile, bp })} testID="field-assessment-blood-pressure" />
        <Field label="Heart rate" placeholder="e.g. 72 bpm" value={profile.heartRate} onChangeText={(heartRate) => setProfile({ ...profile, heartRate })} testID="field-assessment-heart-rate" />
        <Field label="Blood sugar" placeholder="e.g. 95 mg/dL" value={profile.sugar} onChangeText={(sugar) => setProfile({ ...profile, sugar })} testID="field-assessment-blood-sugar" />
        <Field label="Cholesterol" placeholder="e.g. 180 mg/dL" value={profile.cholesterol} onChangeText={(cholesterol) => setProfile({ ...profile, cholesterol })} testID="field-assessment-cholesterol" />
        <Field label="Height (cm)" value={profile.height} onChangeText={(height) => setProfile({ ...profile, height })} testID="field-assessment-height-cm" />
        <Field label="Weight (kg)" value={profile.weight} onChangeText={(weight) => setProfile({ ...profile, weight })} testID="field-assessment-weight-kg" />
      </SectionCard>

      <SectionCard subtitle="Tap every symptom that applies" title="Symptoms" testID="assessment-symptoms-card">
        <View style={styles.chipWrap}>
          {symptomChoices.map((symptom: string) => (
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
        <SelectionGroup
          label="Previous heart disease / surgeries?"
          options={[{ label: "No", value: "no" }, { label: "Yes", value: "yes" }]}
          onSelect={(val) => setProfile({ ...profile, hasHistory: val as any })}
          value={profile.hasHistory}
        />
        {profile.hasHistory === "yes" && (
          <Field label="History details" placeholder="e.g. Angioplasty 2022" value={profile.history} onChangeText={(history) => setProfile({ ...profile, history })} testID="field-assessment-history" />
        )}

        <SelectionGroup
          label="Taking current medicines?"
          options={[{ label: "No", value: "no" }, { label: "Yes", value: "yes" }]}
          onSelect={(val) => setProfile({ ...profile, hasMedicines: val as any })}
          value={profile.hasMedicines}
        />
        {profile.hasMedicines === "yes" && (
          <Field label="Medicine details" placeholder="e.g. Atorvastatin 20mg" value={profile.medicines} onChangeText={(medicines) => setProfile({ ...profile, medicines })} testID="field-assessment-current-medicines" />
        )}

        <SelectionGroup
          label="Family history of heart problems?"
          options={[{ label: "No", value: "no" }, { label: "Yes", value: "yes" }]}
          onSelect={(val) => setProfile({ ...profile, hasFamilyHistory: val as any })}
          value={profile.hasFamilyHistory}
        />
        {profile.hasFamilyHistory === "yes" && (
          <Field label="Family history details" placeholder="e.g. Father has hypertension" value={profile.familyHistory} onChangeText={(familyHistory) => setProfile({ ...profile, familyHistory })} testID="field-assessment-family-history" />
        )}
      </SectionCard>

      <SectionCard subtitle="Smoking, alcohol, exercise, food, sleep, stress" title="Lifestyle" testID="assessment-lifestyle-card">
        <SelectionGroup
          label="Smoking"
          options={[{ label: "No", value: "no" }, { label: "Yes", value: "yes" }]}
          onSelect={(val) => setProfile({ ...profile, smoking: val as any })}
          value={profile.smoking}
        />

        <SelectionGroup
          label="Alcohol"
          options={[{ label: "No", value: "no" }, { label: "Yes", value: "yes" }]}
          onSelect={(val) => setProfile({ ...profile, alcohol: val as any })}
          value={profile.alcohol}
        />

        <Field label="Exercise" placeholder="e.g. 30 min walk" value={profile.exercise} onChangeText={(exercise) => setProfile({ ...profile, exercise })} testID="field-assessment-exercise" />

        <SegmentedPicker
          label="Food habits"
          options={["Normal", "Vegetarian", "Non-Veg", "Balanced"]}
          value={profile.foodHabits}
          onSelect={(val) => setProfile({ ...profile, foodHabits: val })}
        />

        <Field label="Sleep hours" placeholder="e.g. 7-8" value={profile.sleep} onChangeText={(sleep) => setProfile({ ...profile, sleep })} testID="field-assessment-sleep-hours" />

        <SegmentedPicker
          label="Stress level"
          options={["Low", "Medium", "High"]}
          value={profile.stress}
          onSelect={(val) => setProfile({ ...profile, stress: val })}
        />
      </SectionCard>

      <PrimaryButton
        label={syncing ? "Submitting..." : "Submit Assessment"}
        onPress={() => {
          if (!profile.bp.includes("/")) {
            showAppAlert("Validation Error", "Please enter blood pressure in SYS/DIA format (e.g. 120/80)");
            return;
          }
          if (Number(profile.sugar) > 500 || Number(profile.sugar) < 30) {
            showAppAlert("Validation Error", "Please enter a realistic blood sugar value (30-500)");
            return;
          }
          void submitAssessment(profile, selectedSymptoms, () => navigation.navigate("Main"));
        }}
        testID="assessment-submit-button"
      />
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
        {["TMT report", "2D Echo", "Angiogram", "Lipid profile blood test"].map((item: string, index: number) => (
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
  const now = new Date();
  const [viewMonth, setViewMonth] = useState(now.getMonth());
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [selectedDate, setSelectedDate] = useState(now.toISOString().split("T")[0]);
  
  const [daily, setDaily] = useState<DailyLogFormState>({
    bp: "",
    sugar: "",
    weight: "",
    steps: "",
    sleep: "",
  });

  const logs = dashboard?.recent_daily_logs || [];
  
  useEffect(() => {
    const existing = logs.find(l => l.log_date === selectedDate);
    if (existing) {
      setDaily({
        bp: existing.systolic_bp && existing.diastolic_bp ? `${existing.systolic_bp}/${existing.diastolic_bp}` : "",
        sugar: existing.blood_sugar?.toString() || "",
        weight: existing.weight_kg?.toString() || "",
        steps: existing.steps?.toString() || "",
        sleep: existing.sleep_hours?.toString() || "",
      });
    } else {
      setDaily({ bp: "", sugar: "", weight: "", steps: "", sleep: "" });
    }
  }, [selectedDate, logs]);

  const getMonthDays = (m: number, y: number) => {
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    return Array.from({ length: daysInMonth }, (_, i) => i + 1);
  };

  const monthDays = getMonthDays(viewMonth, viewYear);
  const monthName = new Date(viewYear, viewMonth).toLocaleString("default", { month: "long" });

  const isFuture = (day: number) => {
    const d = new Date(viewYear, viewMonth, day);
    return d > now;
  };

  const isTooOld = (day: number) => {
    const d = new Date(viewYear, viewMonth, day);
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(now.getDate() - 30);
    return d < thirtyDaysAgo;
  };

  const changeMonth = (delta: number) => {
    let nextM = viewMonth + delta;
    let nextY = viewYear;
    if (nextM < 0) { nextM = 11; nextY--; }
    if (nextM > 11) { nextM = 0; nextY++; }
    
    // Limit to last 1 month
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(now.getDate() - 30);
    const d = new Date(nextY, nextM, 1);
    const monthStart = new Date(thirtyDaysAgo.getFullYear(), thirtyDaysAgo.getMonth(), 1);
    if (d > now || d < monthStart) return;

    setViewMonth(nextM);
    setViewYear(nextY);
  };

  const handleSave = async () => {
    await submitDailyLog(daily, selectedDate);
  };

  const weeklyStats = useMemo(() => {
    // Get unique logs per day to avoid duplicates showing up in the graph
    const uniqueLogsMap = new Map();
    logs.forEach(l => {
      const date = l.log_date?.slice(0, 10);
      if (date && !uniqueLogsMap.has(date)) {
        uniqueLogsMap.set(date, l);
      }
    });
    
    const uniqueLogs = Array.from(uniqueLogsMap.values())
      .sort((a, b) => b.log_date.localeCompare(a.log_date))
      .slice(0, 7)
      .reverse();

    if (!uniqueLogs.length) return null;
    return {
      steps: uniqueLogs.map(l => l.steps || 0),
      sys: uniqueLogs.map(l => l.systolic_bp || 120),
      sleep: uniqueLogs.map(l => l.sleep_hours || 0),
      dates: uniqueLogs.map(l => l.log_date?.split("-")[2] || "?"), 
    };
  }, [logs]);

  return (
    <Screen testID="screen-tracking">
      <Header eyebrow="Database-backed daily records" title="Daily Tracking" testID="tracking-header" />
      
      <SectionCard subtitle="Select a date to view or enter records" title="Monthly Tracker" testID="tracking-progress-graph-card">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <Pressable onPress={() => changeMonth(-1)} style={{ padding: 8 }}><Ionicons name="chevron-back" size={24} color={palette.brand} /></Pressable>
          <Text style={{ fontSize: 18, fontWeight: "800", color: palette.ink }}>{monthName} {viewYear}</Text>
          <Pressable onPress={() => changeMonth(1)} style={{ padding: 8 }}><Ionicons name="chevron-forward" size={24} color={palette.brand} /></Pressable>
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
          {monthDays.map(day => {
            const dayStr = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
            const logEntry = logs.find(l => l.log_date?.slice(0, 10) === dayStr);
            const future = isFuture(day);
            const selected = selectedDate === dayStr;
            const tooOld = isTooOld(day);

            return (
              <Pressable 
                key={day} 
                disabled={future || tooOld}
                onPress={() => setSelectedDate(dayStr)}
                style={{ 
                  width: 44, height: 44, borderRadius: 22, 
                  backgroundColor: selected ? palette.brand : logEntry ? "rgba(46,125,50,0.15)" : "rgba(0,0,0,0.05)", 
                  alignItems: "center", justifyContent: "center", 
                  borderWidth: selected ? 0 : 1, 
                  borderColor: future || tooOld ? "transparent" : selected ? "transparent" : "rgba(0,0,0,0.1)",
                  elevation: selected ? 4 : 0,
                  shadowColor: palette.brand,
                  shadowOffset: { width: 0, height: 2 },
                  shadowOpacity: selected ? 0.3 : 0,
                  shadowRadius: 4,
                  opacity: future || tooOld ? 0.3 : 1
                }}
              >
                <Text style={{ color: selected ? "#fff" : logEntry ? "#2e7d32" : palette.ink, fontSize: 14, fontWeight: "700" }}>{day}</Text>
              </Pressable>
            );
          })}
        </View>
      </SectionCard>

      <SectionCard subtitle={logs.some(l => l.log_date?.slice(0, 10) === selectedDate) ? "Record is locked and cannot be edited" : `Editing record for ${selectedDate}`} title="Log Entry" testID="tracking-todays-log-card">
        {(() => {
          const entry = logs.find(l => l.log_date?.slice(0, 10) === selectedDate);
          if (entry) {
            return (
              <View style={{ gap: 16, padding: 16, backgroundColor: "rgba(46,125,50,0.05)", borderRadius: 12, borderLeftWidth: 4, borderLeftColor: "#2e7d32" }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={[styles.inkText, { fontSize: 16 }]}>Blood Pressure</Text>
                  <Text style={{ fontWeight: "800", fontSize: 18, color: "#2e7d32" }}>{entry.systolic_bp && entry.diastolic_bp ? `${entry.systolic_bp}/${entry.diastolic_bp}` : "--"}</Text>
                </View>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={[styles.inkText, { fontSize: 16 }]}>Blood Sugar</Text>
                  <Text style={{ fontWeight: "800", fontSize: 18, color: "#2e7d32" }}>{entry.blood_sugar?.toString() || "--"} mg/dL</Text>
                </View>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={[styles.inkText, { fontSize: 16 }]}>Daily Steps</Text>
                  <Text style={{ fontWeight: "800", fontSize: 18, color: "#2e7d32" }}>{entry.steps?.toLocaleString() || "--"}</Text>
                </View>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={[styles.inkText, { fontSize: 16 }]}>Sleep Hours</Text>
                  <Text style={{ fontWeight: "800", fontSize: 18, color: "#2e7d32" }}>{entry.sleep_hours?.toString() || "--"}h</Text>
                </View>
                <View style={{ height: 1, backgroundColor: "rgba(0,0,0,0.1)", marginVertical: 4 }} />
                <Text style={{ color: "#2e7d32", fontWeight: "700", textAlign: "center", fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Recorded on {selectedDate} ✅</Text>
              </View>
            );
          }
          return (
            <>
              <Field label="Blood pressure" placeholder="e.g. 120/80" value={daily.bp} onChangeText={(bp) => setDaily({ ...daily, bp })} testID="field-tracking-blood-pressure" />
              <Field label="Blood sugar" placeholder="e.g. 95 mg/dL" value={daily.sugar} onChangeText={(sugar) => setDaily({ ...daily, sugar })} testID="field-tracking-blood-sugar" />
              <Field label="Weight" placeholder="e.g. 70 kg" value={daily.weight} onChangeText={(weight) => setDaily({ ...daily, weight })} testID="field-tracking-weight" />
              <Field label="Steps" placeholder="e.g. 8000" value={daily.steps} onChangeText={(steps) => setDaily({ ...daily, steps })} testID="field-tracking-steps" />
              <Field label="Sleep hours" placeholder="e.g. 8" value={daily.sleep} onChangeText={(sleep) => setDaily({ ...daily, sleep })} testID="field-tracking-sleep-hours" />
              <PrimaryButton label={syncing ? "Saving..." : "Save Record"} onPress={handleSave} testID="tracking-save-daily-record-button" />
            </>
          );
        })()}
      </SectionCard>

      <SectionCard subtitle="Weekly health variations & trends" title="Trend Analytics" testID="tracking-recent-logs-card">
        {weeklyStats ? (
          <View style={{ gap: 24, paddingVertical: 10 }}>
            <View>
              <Text style={{ fontWeight: "800", fontSize: 16, marginBottom: 8, color: palette.brand }}>Daily Steps</Text>
              <TrendLineGraph color={palette.brand} points={weeklyStats.steps} maxScale={10000} xLabels={weeklyStats.dates} />
            </View>
            <View>
              <Text style={{ fontWeight: "800", fontSize: 16, marginBottom: 8, color: palette.danger }}>Systolic Blood Pressure</Text>
              <TrendLineGraph color={palette.danger} points={weeklyStats.sys} maxScale={200} xLabels={weeklyStats.dates} />
            </View>
            <View>
              <Text style={{ fontWeight: "800", fontSize: 16, marginBottom: 8, color: palette.cool }}>Sleep Duration (Hrs)</Text>
              <TrendLineGraph color={palette.cool} points={weeklyStats.sleep} maxScale={12} xLabels={weeklyStats.dates} />
            </View>
          </View>
        ) : (
          <Text style={styles.helperText}>Add logs to unlock premium trend analytics.</Text>
        )}
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
        {messages.map((message: any, index: number) => (
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
          careResults.map((item: any, index: number) => (
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

function ProfileScreen() {
  const { dashboard, logoutUser } = useAppState();
  const user = dashboard?.user;
  const prediction = dashboard?.latest_prediction;
  const history = dashboard?.past_predictions || [];

  const mergedHistory = useMemo(() => {
    const list = [...history];
    if (prediction && !list.find(h => h.id === prediction?.id)) {
      list.unshift(prediction);
    }
    return list.sort((a,b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
  }, [history, prediction]);

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea} testID="screen-profile">
      <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
        <LinearGradient colors={[palette.brandDeep, palette.brand]} style={[styles.hero, { paddingBottom: 40 }]}>
           <View style={{ alignItems: "center", marginBottom: 20 }}>
              <View style={{ backgroundColor: "rgba(255,255,255,0.2)", width: 80, height: 80, borderRadius: 40, alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
                <Ionicons name="person-circle" size={80} color="#fff" />
              </View>
              <Text style={{ color: "#fff", fontSize: 28, fontWeight: "900", letterSpacing: 0.5 }}>{user?.name || "Premium User"}</Text>
              <Text style={{ color: "rgba(255,255,255,0.8)", fontSize: 16, fontWeight: "600" }}>{user?.email}</Text>
           </View>
           
           <View style={{ flexDirection: "row", justifyContent: "center", gap: 12, marginTop: 8 }}>
              <View style={{ backgroundColor: "rgba(255,255,255,0.15)", paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>{user?.age} Yrs</Text>
              </View>
              <View style={{ backgroundColor: "rgba(255,255,255,0.15)", paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>{user?.gender}</Text>
              </View>
              <View style={{ backgroundColor: "rgba(255,255,255,0.15)", paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>📍 {user?.location?.split(",")[0]}</Text>
              </View>
           </View>
        </LinearGradient>

        <View style={{ marginTop: 20, paddingHorizontal: 20, gap: 20 }}>
          <SectionCard subtitle="Contact and identity details" title="Member Information" testID="profile-details-card">
            <View style={{ gap: 16 }}>
              {[
                { icon: "person", label: "Full Name", val: user?.name, color: palette.brand },
                { icon: "card", label: "Member ID", val: user?.id?.slice(-8).toUpperCase(), color: palette.accent },
                { icon: "call", label: "Contact", val: user?.contact_number, color: palette.danger },
                { icon: "location", label: "City/Region", val: user?.location, color: palette.cool },
              ].map((item, i) => (
                <View key={i} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                    <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: `${item.color}15`, alignItems: "center", justifyContent: "center" }}>
                      <Ionicons name={item.icon as any} size={16} color={item.color} />
                    </View>
                    <Text style={[styles.inkText, { fontWeight: "600" }]}>{item.label}</Text>
                  </View>
                  <Text style={{ fontWeight: "700", color: palette.ink }}>{item.val || "--"}</Text>
                </View>
              ))}
            </View>
          </SectionCard>

          <SectionCard subtitle="Previous AI analysis records" title="Assessment History" testID="profile-history-card">
            {mergedHistory.length > 0 ? (
              <View style={{ gap: 12 }}>
                {mergedHistory.map((p, idx: number) => (
                  <View key={p.id} style={{ 
                    padding: 12, backgroundColor: "rgba(0,0,0,0.03)", borderRadius: 12,
                    borderLeftWidth: 4, borderLeftColor: p.risk_level === "High" ? palette.danger : palette.brand
                  }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <Text style={{ fontWeight: "800", color: palette.ink, fontSize: 16 }}>
                        {Math.round(p.risk_score)}% Risk
                        {idx === 0 && <Text style={{ fontSize: 10, color: palette.muted }}> (LATEST)</Text>}
                      </Text>
                      <View style={{ backgroundColor: p.risk_level === "High" ? `${palette.danger}15` : `${palette.brand}15`, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 }}>
                        <Text style={{ fontSize: 11, fontWeight: "700", color: p.risk_level === "High" ? palette.danger : palette.brand }}>{p.risk_level.toUpperCase()}</Text>
                      </View>
                    </View>
                    <Text style={[styles.helperText, { marginBottom: 8 }]}>Assessment on {new Date(p.created_at).toLocaleDateString()}</Text>
                    {!!p.explanation?.length && (
                      <View style={{ marginTop: 4 }}>
                        {p.explanation.slice(0, 3).map((f: string) => (
                          <Text key={f} style={[styles.listItem, { fontSize: 12, marginBottom: 2 }]}>• {f}</Text>
                        ))}
                      </View>
                    )}
                  </View>
                ))}
              </View>
            ) : (
              <View style={{ padding: 20, alignItems: "center" }}>
                <Ionicons name="time" size={32} color={palette.muted} />
                <Text style={[styles.helperText, { marginTop: 8 }]}>Your future assessments will appear here.</Text>
              </View>
            )}
          </SectionCard>

          <View style={{ marginVertical: 20 }}>
            <PrimaryButton label="Sign Out" onPress={() => void logoutUser()} testID="profile-logout-button" />
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
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

function SelectionGroup({
  label,
  options,
  value,
  onSelect,
}: {
  label: string;
  options: { label: string; value: string }[];
  value: string;
  onSelect: (val: string) => void;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={{ flexDirection: "row", gap: 8, marginTop: 4 }}>
        {options.map((opt: { label: string; value: string }) => (
          <Pressable
            key={opt.value}
            onPress={() => onSelect(opt.value)}
            style={[styles.genderBtn, value === opt.value && styles.genderBtnActive]}
          >
            <Text style={[styles.genderBtnText, value === opt.value && styles.genderBtnTextActive]}>
              {opt.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function SegmentedPicker({
  label,
  options,
  value,
  onSelect,
}: {
  label: string;
  options: string[];
  value: string;
  onSelect: (val: string) => void;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.chipWrap}>
        {options.map((opt) => (
          <Pressable
            key={opt}
            onPress={() => onSelect(opt)}
            style={[styles.chip, value === opt && styles.chipActive]}
          >
            <Text style={[styles.chipText, value === opt && styles.chipTextActive]}>
              {opt}
            </Text>
          </Pressable>
        ))}
      </View>
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
  trendGraph: { height: 100, alignItems: "center", justifyContent: "center", backgroundColor: "#f9fbf9", borderRadius: 12, overflow: "hidden" },
  inkText: { color: palette.ink, fontSize: 15 },
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
  // ─── Auth styles ──────────────────────────────────────────────────
  authContainer: { flex: 1, backgroundColor: palette.background },
  authScroll: { flexGrow: 1 },
  authHero: { alignItems: "center", justifyContent: "center", paddingVertical: 48, paddingHorizontal: 24, gap: 8 },
  authAppName: { color: "#fff", fontSize: 26, fontWeight: "800", letterSpacing: 0.5 },
  authTagline: { color: "rgba(255,255,255,0.75)", fontSize: 14, textAlign: "center" },
  authCard: { backgroundColor: "#fff", margin: 16, borderRadius: 20, padding: 24, gap: 12, shadowColor: "#000", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 8, elevation: 4 },
  authTitle: { fontSize: 20, fontWeight: "700", color: palette.ink, marginBottom: 4 },
  authSectionLabel: { fontSize: 13, fontWeight: "600", color: palette.muted, textTransform: "uppercase", letterSpacing: 0.5, marginTop: 8 },
  authInput: { backgroundColor: "#F7F9F8", borderWidth: 1, borderColor: palette.line, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, color: palette.ink, fontSize: 15 },
  authPrimaryBtn: { backgroundColor: palette.brand, borderRadius: 14, paddingVertical: 15, alignItems: "center" },
  authPrimaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  authSecondaryBtn: { alignItems: "center", paddingVertical: 8 },
  authSecondaryBtnText: { color: palette.muted, fontSize: 14 },
  authError: { color: palette.danger, fontSize: 13, backgroundColor: "#FFF0F0", borderRadius: 10, padding: 10 },
  genderRow: { flexDirection: "row", gap: 8 },
  genderBtn: { flex: 1, borderWidth: 1.5, borderColor: palette.line, borderRadius: 12, paddingVertical: 10, alignItems: "center" },
  genderBtnActive: { borderColor: palette.brand, backgroundColor: `${palette.brand}15` },
  genderBtnText: { color: palette.muted, fontWeight: "600", fontSize: 14 },
  genderBtnTextActive: { color: palette.brand },
  // ─── Logout button ────────────────────────────────────────────────
  logoutBtn: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-end", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10, backgroundColor: "rgba(255,255,255,0.15)" },
  logoutBtnText: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontWeight: "600" },
});

