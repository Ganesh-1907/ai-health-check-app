from __future__ import annotations

import re

from app.models.entities import Assessment, MedicalReport, RiskPrediction, User


class RecommendationEngine:
    def build(
        self,
        user: User,
        assessment: Assessment,
        prediction: RiskPrediction,
        reports: list[MedicalReport] | None = None,
    ) -> dict:
        report_metrics = self._aggregate_report_metrics(reports or [])
        effective_systolic_bp = self._first_number(report_metrics.get("systolic_bp")) or assessment.systolic_bp or 0
        effective_diastolic_bp = self._first_number(report_metrics.get("diastolic_bp")) or assessment.diastolic_bp or 0
        effective_sugar = self._first_number(report_metrics.get("glucose")) or assessment.blood_sugar or 0
        effective_cholesterol = self._first_number(report_metrics.get("cholesterol")) or assessment.cholesterol or 0
        effective_ldl = self._first_number(report_metrics.get("ldl")) or 0
        effective_hdl = self._first_number(report_metrics.get("hdl")) or 0
        effective_triglycerides = self._first_number(report_metrics.get("triglycerides")) or 0

        active_tags: set[str] = {"heart"}
        diet_plan: list[str] = [
            "Breakfast: oats or another whole grain with fruit and unsalted nuts or seeds.",
            "Lunch: dal, beans, or lean protein with vegetables and a whole grain such as brown rice or roti in controlled portions.",
            "Dinner: grilled fish, tofu, or pulses with cooked vegetables and a lighter carbohydrate portion.",
            "Snacks: fruit, curd, sprouts, or a small handful of unsalted nuts instead of packaged snacks.",
        ]
        foods_to_avoid: list[str] = [
            "Deep-fried foods",
            "Processed snacks with excess salt",
            "Sugary drinks",
        ]
        medicine_guidance = [
            "If you already take prescribed medicines, continue them exactly as your doctor advised.",
            "Do not start, stop, or change prescription heart or diabetes medicines without consulting a doctor.",
            "Any chest pain, fainting, severe breathlessness, or rapidly worsening values should trigger urgent medical review.",
        ]
        daily_tips = [
            "Check and log blood pressure at the same time each day.",
            "Keep water intake regular through the day.",
            "Aim for a short daily walk unless a doctor has restricted exertion.",
        ]
        hydration_goal = round(min(3.0, max(1.8, ((assessment.weight_kg or 70) * 0.03))), 1)

        if effective_systolic_bp >= 130 or effective_diastolic_bp >= 85:
            active_tags.update({"bp", "sodium"})
            diet_plan.append("Priority: follow a low-sodium DASH-style meal pattern with fresh foods over packaged foods.")
            foods_to_avoid.extend(["Pickles", "Packaged soups", "Processed meats"])
            daily_tips.append("Reduce added salt and compare food labels before buying.")
            medicine_guidance.append(
                "If blood pressure remains elevated, a doctor may review whether medicines such as ACE inhibitors, ARBs, calcium-channel blockers, beta-blockers, or diuretics are appropriate."
            )

        if effective_sugar >= 126:
            active_tags.update({"sugar", "fiber"})
            diet_plan.append("Priority: pair carbohydrates with protein and fiber to reduce post-meal sugar spikes.")
            foods_to_avoid.extend(["Sweets", "Bakery desserts", "Refined flour snacks"])
            daily_tips.append("Track fasting or post-meal sugar consistently.")
            medicine_guidance.append(
                "If sugar remains high, a doctor may review diabetes medicines or insulin strategy based on your diagnosis and reports."
            )

        if effective_cholesterol >= 200 or effective_ldl >= 130 or effective_triglycerides >= 200 or (effective_hdl and effective_hdl < 40):
            active_tags.update({"lipids", "fiber"})
            diet_plan.append("Priority: increase oats, beans, flax or chia, vegetables, and unsaturated fats to improve lipid balance.")
            foods_to_avoid.extend(["Trans-fat foods", "High-fat red meat"])
            daily_tips.append("Choose grilled or steamed meals more often than fried foods.")
            medicine_guidance.append(
                "If LDL or total cholesterol stays high, your doctor may discuss lipid-lowering therapy such as statins or other agents."
            )

        if assessment.bmi and assessment.bmi >= 25:
            active_tags.add("weight")
            diet_plan.append("Portion control matters: keep dinner lighter and avoid repeated calorie-dense snacks.")
            daily_tips.append("Track weekly weight trend instead of reacting only to a single day.")

        if assessment.lifestyle.get("smoking"):
            active_tags.add("smoking")
            daily_tips.append("Make smoking cessation a priority; even gradual reduction helps.")
            foods_to_avoid.append("Tobacco in all forms")

        if str(assessment.lifestyle.get("stress_level", "")).lower() in {"high", "severe"}:
            active_tags.add("stress")
            daily_tips.append("Use 5-10 minutes of breathing or relaxation practice twice daily.")

        if assessment.lifestyle.get("sleep_hours") and float(assessment.lifestyle.get("sleep_hours", 0)) < 6:
            active_tags.add("sleep")
            daily_tips.append("Protect 7-8 hours of sleep as part of heart-risk reduction.")

        if str(assessment.lifestyle.get("exercise", "")).lower() in {"none", "low", "sedentary"}:
            active_tags.add("exercise")
            daily_tips.append("Increase steps gradually and avoid sudden spikes in exertion.")

        if prediction.risk_level == "High":
            medicine_guidance.append("Because your current profile is high risk, doctor review should not be delayed.")
            daily_tips.append("Keep emergency contacts and nearest hospital options ready.")
            hydration_goal = max(hydration_goal, 2.3)
        elif prediction.risk_level == "Medium":
            daily_tips.append("Review your weekly trend chart and act early if numbers worsen.")

        if user.age >= 60:
            daily_tips.append("Avoid sudden exertion spikes; increase activity gradually and safely.")

        if reports:
            diet_plan.append("Uploaded report findings were included while shaping these recommendations.")

        diet_plan = self._prioritize_diet_plan(diet_plan, active_tags)

        return {
            "diet_plan": list(dict.fromkeys(diet_plan)),
            "foods_to_avoid": list(dict.fromkeys(foods_to_avoid)),
            "medicine_guidance": list(dict.fromkeys(medicine_guidance)),
            "daily_tips": list(dict.fromkeys(daily_tips)),
            "hydration_goal_liters": hydration_goal,
        }

    @staticmethod
    def _aggregate_report_metrics(reports: list[MedicalReport]) -> dict[str, str]:
        aggregated: dict[str, str] = {}
        for report in reports:
            findings = report.extracted_findings or {}
            metrics = findings.get("metrics", {}) if isinstance(findings, dict) else {}
            if not isinstance(metrics, dict):
                continue
            if "blood_pressure" in metrics:
                bp_match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", str(metrics["blood_pressure"]))
                if bp_match:
                    aggregated["systolic_bp"] = bp_match.group(1)
                    aggregated["diastolic_bp"] = bp_match.group(2)
            for key in ["ldl", "hdl", "triglycerides", "cholesterol", "glucose", "heart_rate"]:
                if key in metrics and key not in aggregated:
                    aggregated[key] = str(metrics[key])
        return aggregated

    @staticmethod
    def _first_number(value: object) -> float | None:
        if value is None:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        return float(match.group(1))

    @staticmethod
    def _prioritize_diet_plan(diet_plan: list[str], active_tags: set[str]) -> list[str]:
        prioritized = list(diet_plan)
        if "bp" in active_tags:
            prioritized.insert(0, "Focus on sodium control first because blood pressure is one of the main current concerns.")
        if "sugar" in active_tags:
            prioritized.insert(0, "Keep meal timing steady and avoid sugar-heavy beverages or desserts.")
        if "lipids" in active_tags:
            prioritized.insert(0, "Favor soluble fiber and unsaturated fats to support cholesterol improvement.")
        return prioritized
