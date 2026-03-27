export const dashboardSnapshot = {
  riskScore: 72,
  riskLevel: "High",
  confidence: 0.82,
  alerts: [
    "Chest pain with sweating requires urgent medical review.",
    "Recent BP pattern is above the safe target range.",
  ],
  metrics: [
    { label: "BP", value: "148/96", tone: "danger" },
    { label: "Sugar", value: "164", tone: "warning" },
    { label: "BMI", value: "29.1", tone: "warning" },
    { label: "Sleep", value: "5.8h", tone: "cool" },
  ],
  tips: [
    "Use a low-sodium meal plan for the next 7 days.",
    "Take a 15-minute walk after lunch if there is no exertion restriction.",
    "Log morning BP before caffeine.",
  ],
  hospitals: [
    { name: "City Heart Institute", distance: "2.4 km", kind: "Hospital" },
    { name: "Dr. Mehta Cardiology Clinic", distance: "3.1 km", kind: "Specialist" },
    { name: "Metro Emergency Center", distance: "4.2 km", kind: "Emergency" },
  ],
  trends: [
    { day: "M", bp: 132, sugar: 124, weight: 79.4 },
    { day: "T", bp: 136, sugar: 130, weight: 79.0 },
    { day: "W", bp: 142, sugar: 139, weight: 78.8 },
    { day: "T", bp: 145, sugar: 152, weight: 78.7 },
    { day: "F", bp: 148, sugar: 164, weight: 78.5 },
  ],
};

export const initialChat = [
  {
    id: "welcome",
    role: "assistant" as const,
    text: "I can help with heart-risk questions, report understanding, daily tracking, diet suggestions, and urgent warning patterns.",
  },
];
