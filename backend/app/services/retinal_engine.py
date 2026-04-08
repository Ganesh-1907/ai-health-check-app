from __future__ import annotations

import base64
from io import BytesIO

import cv2
import numpy as np
from PIL import Image


class RetinalAnalysisEngine:
    """Generate retinal cardiovascular screening output similar to the OptiHeart demo."""

    def predict(self, image_bytes: BytesIO) -> dict:
        try:
            image = Image.open(image_bytes).convert("RGB")
            image_array = np.array(image)
            enhanced, binary = self._preprocess_retinal_image(image_array)
            features = self._extract_features(enhanced, binary)
            risk_factors = self._analyze_risk(features)
            overall_risk = float(np.clip(np.mean(list(risk_factors.values())), 0.0, 1.0))
            risk_level = self._risk_level(overall_risk)

            return {
                "overall_risk_score": round(overall_risk, 4),
                "overall_risk_percent": round(overall_risk * 100, 1),
                "risk_level": risk_level,
                "risk_factors": {key: round(value, 4) for key, value in risk_factors.items()},
                "features": {key: round(value, 4) for key, value in features.items()},
                "enhanced_image": self._to_base64(enhanced),
                "binary_image": self._to_base64(binary),
            }
        except Exception as exc:
            return {"error": f"Retinal analysis failed: {exc}"}

    def _preprocess_retinal_image(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            21,
            6,
        )
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        return enhanced, binary

    def _extract_features(self, enhanced: np.ndarray, binary: np.ndarray) -> dict[str, float]:
        binary_mask = binary > 0
        vessel_ratio = float(binary_mask.mean())
        contrast = float(np.std(enhanced))
        edge_density = float((cv2.Canny(enhanced, 35, 120) > 0).mean())
        bright_fraction = float((enhanced >= np.percentile(enhanced, 97)).mean())

        if binary_mask.any():
            distance = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
            avg_width_raw = float(distance[binary_mask].mean() * 2.0)
        else:
            avg_width_raw = 1.5

        vessel_density = float(np.clip(0.22 + vessel_ratio * 1.55 + contrast / 900.0, 0.18, 0.62))
        avg_vessel_width = float(np.clip(1.9 + avg_width_raw * 0.85 + vessel_ratio * 1.2, 1.5, 5.4))
        tortuosity = float(np.clip(0.9 + edge_density * 5.0 + vessel_density * 0.25, 0.85, 2.6))
        disc_area = float(np.clip(8500 + bright_fraction * 90000 + contrast * 18.0, 7000, 18000))
        disc_diameter = float(np.clip(np.sqrt((4.0 * disc_area) / np.pi), 90, 160))

        return {
            "Vessel Density": vessel_density,
            "Avg Vessel Width": avg_vessel_width,
            "Tortuosity": tortuosity,
            "Disc Area": disc_area,
            "Disc Diameter": disc_diameter,
        }

    def _analyze_risk(self, features: dict[str, float]) -> dict[str, float]:
        raw_risk_factors = {
            "Vessel Density Risk": 1.0 - (features["Vessel Density"] / 0.4),
            "Vessel Width Risk": features["Avg Vessel Width"] / 5.0,
            "Tortuosity Risk": features["Tortuosity"] / 2.0,
            "Disc Area Risk": features["Disc Area"] / 15000.0,
        }
        return {
            key: float(np.clip(value, -0.25, 1.0))
            for key, value in raw_risk_factors.items()
        }

    def _risk_level(self, overall_risk: float) -> str:
        if overall_risk < 0.33:
            return "Low"
        if overall_risk < 0.66:
            return "Moderate"
        return "High"

    def _to_base64(self, image_array: np.ndarray) -> str:
        resized = cv2.resize(image_array, (288, 288), interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", resized)
        if not ok:
            raise ValueError("Failed to encode image preview")
        return base64.b64encode(buffer).decode("utf-8")
