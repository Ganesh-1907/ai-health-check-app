from __future__ import annotations

import base64
import re
from pathlib import Path

import requests
from PIL import Image
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR

from app.core.config import get_settings


class ReportParser:
    vision_timeout_seconds = 4.0

    def __init__(self) -> None:
        self.settings = get_settings()
        self.ocr_engine = RapidOCR()

    def parse(self, file_path: Path, report_type: str, content_type: str) -> tuple[str, dict, float]:
        text = ""
        findings: dict[str, str | list[str] | dict[str, str]] = {"report_type": report_type}
        confidence = 0.15

        suffix = file_path.suffix.lower()
        try:
            if suffix == ".pdf":
                text = self._extract_pdf_text(file_path)
                confidence = 0.58 if text else 0.2
                if not text:
                    findings["note"] = "PDF text could not be extracted reliably, but the file was stored."
            elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                text = self._extract_image_text_with_ocr(file_path)
                confidence = 0.62 if text else 0.14
                if not text:
                    text = self._extract_image_text_with_vision(file_path)
                    confidence = 0.46 if text else 0.14
                if not text:
                    findings["note"] = "Image text could not be extracted reliably, but the file was stored."
            elif suffix in {".txt", ".csv", ".tsv", ".log"} or content_type.startswith("text/"):
                text = self._extract_plain_text(file_path)
                confidence = 0.68 if text else 0.18
                if not text:
                    findings["note"] = "Text report was stored, but no readable content was found."
            else:
                findings["note"] = "Unsupported file type for extraction, but file is stored."
        except Exception as exc:
            findings["note"] = f"Extraction issue: {exc}. The file was stored for later review."

        metrics = self._extract_metrics(text)
        markers = self._detect_keywords(text)
        if metrics:
            findings["metrics"] = metrics
            confidence = max(confidence, 0.72)
        if markers:
            findings["detected_markers"] = markers
            confidence = max(confidence, 0.64)

        if not text and "note" not in findings:
            findings["note"] = "No reliable text was extracted from the uploaded report."

        return text, findings, confidence

    @staticmethod
    def _extract_pdf_text(file_path: Path) -> str:
        chunks: list[str] = []
        with file_path.open("rb") as handle:
            reader = PdfReader(handle)
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
        return "\n".join(chunks).strip()

    @staticmethod
    def _extract_plain_text(file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8", errors="ignore").strip()

    def _extract_image_text_with_vision(self, file_path: Path) -> str:
        try:
            with Image.open(file_path) as image:
                image.thumbnail((1800, 1800))
                temp_path = file_path.with_suffix(".vision.jpg")
                image.convert("RGB").save(temp_path, format="JPEG", quality=85)
            encoded = base64.b64encode(temp_path.read_bytes()).decode("utf-8")
            temp_path.unlink(missing_ok=True)
        except Exception:
            return ""

        prompt = (
            "Read this medical report image carefully. Extract the visible text as faithfully as possible. "
            "If values such as LDL, HDL, triglycerides, ejection fraction, blockage percentage, BP, heart rate, glucose, "
            "cholesterol, TMT result, ischemia, or angiogram findings are visible, include them clearly. Return plain text only."
        )
        try:
            response = requests.post(
                f"{self.settings.ollama_base_url}/api/chat",
                json={
                    "model": self.settings.ollama_vision_model,
                    "stream": False,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [encoded],
                        }
                    ],
                },
                timeout=(1.5, self.vision_timeout_seconds),
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("message", {}).get("content", "").strip()
        except Exception:
            return ""

    def _extract_image_text_with_ocr(self, file_path: Path) -> str:
        try:
            result, _ = self.ocr_engine(str(file_path))
            if not result:
                return ""
            lines = [item[1].strip() for item in result if len(item) >= 2 and str(item[1]).strip()]
            return "\n".join(lines).strip()
        except Exception:
            return ""

    @staticmethod
    def _detect_keywords(text: str) -> list[str]:
        lowered = text.lower()
        keywords = []
        for marker in [
            "ldl",
            "hdl",
            "triglycerides",
            "ejection fraction",
            "angiogram",
            "blockage",
            "tmt",
            "echo",
            "cholesterol",
            "glucose",
            "ischemia",
            "stenosis",
        ]:
            if marker in lowered:
                keywords.append(marker)
        return keywords

    @staticmethod
    def _extract_metrics(text: str) -> dict[str, str]:
        extracted: dict[str, str] = {}
        lowered = text.lower()
        patterns = {
            "ldl": r"ldl[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "hdl": r"hdl[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "triglycerides": r"triglycerides[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "cholesterol": r"(?:total cholesterol|cholesterol)[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "glucose": r"(?:glucose|blood sugar)[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "ejection_fraction": r"(?:ejection fraction|ef)[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "heart_rate": r"(?:heart rate|pulse)[^0-9]{0,12}(\d+(?:\.\d+)?)",
            "blood_pressure": r"(\d{2,3}\s*/\s*\d{2,3})",
            "blockage_percent": r"(?:blockage|stenosis|narrowing)[^0-9]{0,20}(\d{1,3}(?:\.\d+)?)\s*%",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                extracted[key] = match.group(1).strip()
        if "blockage_percent" not in extracted:
            reverse_match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:blockage|stenosis|narrowing)", lowered, re.IGNORECASE)
            if reverse_match:
                extracted["blockage_percent"] = reverse_match.group(1).strip()
        tmt_match = re.search(r"(?:tmt|treadmill test|stress test)[^a-z]{0,20}(positive|negative|equivocal)", lowered, re.IGNORECASE)
        if tmt_match:
            extracted["tmt_result"] = tmt_match.group(1).strip().lower()
        elif "positive for ischemia" in lowered or "ischemic changes" in lowered:
            extracted["tmt_result"] = "positive"
        if "ischemia" in lowered or "ischemic" in lowered:
            extracted["ischemia"] = "present"
        if "wall motion abnormality" in lowered:
            extracted["wall_motion_abnormality"] = "present"
        return extracted
