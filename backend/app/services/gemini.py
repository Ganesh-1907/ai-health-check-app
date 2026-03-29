from __future__ import annotations

import logging
from typing import Any

import google.generativeai as genai
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class GeminiService:
    _instance = None
    _current_key_index = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GeminiService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.settings = get_settings()
        self.keys = self.settings.gemini_keys
        self.model_name = self.settings.gemini_model
        self.chat_system_instruction = (
            "You are HeartGuard, a careful cardiovascular-health assistant. "
            "Answer with concise, evidence-based guidance; avoid diagnoses and drug dosing; "
            "and steer unrelated questions back to heart health. Use clear, reassuring language."
        )
        self.chat_generation_config = {
            "temperature": 0.45,
            "top_p": 0.9,
            "max_output_tokens": 400,
        }
        self._initialized = True
        
        if not self.keys:
            logger.warning("No Gemini API keys found in settings. Gemini features will be disabled.")

    def _get_next_key(self) -> str | None:
        if not self.keys:
            return None
        
        key = self.keys[GeminiService._current_key_index]
        # Round-robin increment
        GeminiService._current_key_index = (GeminiService._current_key_index + 1) % len(self.keys)
        return key

    async def generate_content(self, prompt: str, image_data: bytes | None = None, mime_type: str = "image/jpeg") -> str:
        # Try all keys before giving up
        for attempt in range(len(self.keys) or 1):
            key = self._get_next_key()
            if not key:
                return "Gemini service is not configured."

            try:
                genai.configure(api_key=key)
                # Try primary model first, fallback to gemini-1.5-flash if needed
                models_to_try = [self.model_name, "gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-pro"]
                last_err = None
                
                for model_id in models_to_try:
                    try:
                        model = genai.GenerativeModel(model_id)
                        if image_data:
                            response = await model.generate_content_async([
                                prompt,
                                {"mime_type": mime_type, "data": image_data}
                            ])
                        else:
                            response = await model.generate_content_async(prompt)
                        return response.text
                    except Exception as e:
                        last_err = e
                        # If model is not found or quota is 0/exceeded, try the next model in the list
                        if "404" in str(e) or "429" in str(e) or "quota" in str(e).lower():
                            continue # Try next model (e.g. fallback to 1.5-flash)
                        raise e # Other critical error, try next key
            except Exception as e:
                logger.error(f"Gemini Attempt {attempt + 1} failed with key: {e}")
                if attempt == len(self.keys) - 1:
                    return f"Gemini service exhausted all keys/models. Last error: {e}"
        
        return "Gemini service failed to generate content."

    async def chat(self, history: list[dict], message: str) -> str:
        # Streamlined model list based on what worked
        models_to_try = [self.settings.gemini_model, "gemini-flash-latest", "gemini-1.5-flash"]
        
        for attempt in range(len(self.keys) or 1):
            key = self._get_next_key()
            if not key:
                continue

            try:
                genai.configure(api_key=key)
                for model_id in models_to_try:
                    try:
                        logger.info(f"Gemini Chat Key {attempt + 1}: Trying {model_id}")
                        model = genai.GenerativeModel(model_id)
                        gemini_history = []
                        for entry in history:
                            role = "user" if entry["role"] == "user" else "model"
                            gemini_history.append({"role": role, "parts": [entry["content"]]})

                        chat_session = model.start_chat(history=gemini_history)
                        # Set a shorter sub-timeout for each attempt
                        response = await chat_session.send_message_async(message)
                        return response.text
                    except Exception as e:
                        # If 429 quota error, try next key immediately
                        if "429" in str(e) or "quota" in str(e).lower():
                            logger.warning(f"Quota exceeded for key {attempt + 1}, trying next key.")
                            break # Go to next key
                        # If 404 model error, try next model in same key
                        if "404" in str(e) or "not found" in str(e).lower():
                            continue
                        raise e
            except Exception as e:
                logger.error(f"Gemini Chat attempt {attempt + 1} failed: {e}")
                if attempt == len(self.keys) - 1:
                    return f"Gemini chat failed after trying all keys. Last error: {e}"
        
        return "Gemini chat service failed or timed out."
