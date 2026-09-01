import requests
import json
import logging
from typing import Dict, List

from django.conf import settings

from .prompts import BASE_PROMPT


logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
            "ru": "russian",
            "en": "english",
            "es": "spanish",
            "fr": "french",
            "de": "german",
            "zh": "chinese",
            "ja": "japanese",
        }

class DeepSeekService:
    def __init__(self):
        self.api_key = getattr(settings, "DEEPSEEK_API_KEY", None)
        self.api_url = getattr(settings, "DEEPSEEK_API_URL")
        self.model = getattr(settings, "DEEPSEEK_MODEL")
        self.session = requests.Session()

    def _parse_response(self, raw_response: dict) -> dict:
        content = raw_response["choices"][0]["message"]["content"]
        if not content:
            raise ValueError("Empty content from DeepSeek")
        
        content = content.strip()
        
        if content.startswith("```"):
            content = (
                content
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(
                "DeepSeek returned invalid JSON: %s",
                raw_response,
            )
            raise ValueError("Invalid JSON returned by DeepSeek") from e

        if not isinstance(data, dict):
            logger.warning(
                "DeepSeek returned non-dict JSON: %r",
                data,
            )
            raise ValueError("DeepSeek response must be a JSON object")

        # text
        text = data.get("text")

        if not isinstance(text, str) or not text.strip():
            raise ValueError("Invalid 'text' field")

        # corrected_text
        corrected_text = data.get("corrected_text")

        if corrected_text is not None and not isinstance(corrected_text, str):
            raise ValueError("Invalid 'corrected_text' field")

        # translations
        translations = data.get("translations")

        if not isinstance(translations, list):
            raise ValueError("'translations' must be a list")

        if not all(isinstance(item, str) and item.strip() for item in translations):
            raise ValueError("'translations' must contain only non-empty strings")

        # examples
        examples = data.get("examples")

        if not isinstance(examples, list):
            raise ValueError("'examples' must be a list")

        if not all(isinstance(item, str) and item.strip() for item in examples):
            raise ValueError("'examples' must contain only non-empty strings")

        return {
            "text": text.strip(),
            "corrected_text": (
                corrected_text.strip()
                if corrected_text is not None
                else None
            ),
            "translations": [
                item.strip()
                for item in translations
            ],
            "examples": [
                item.strip()
                for item in examples
            ],
        }


    def build_system_prompt(self, language_pair) -> str:
        native_lang = LANGUAGE_NAMES.get(language_pair.native_language, language_pair.native_language)
        learning_lang = LANGUAGE_NAMES.get(language_pair.learning_language, language_pair.learning_language)

        system_prompt = BASE_PROMPT.format(native_language=native_lang, learning_language=learning_lang)

        return system_prompt

    def translate(self, text: str, language_pair):

        if not self.api_key:
            raise ValueError("DeepSeek API ключ не найден")
        try:
            system_prompt = self.build_system_prompt(language_pair)
            messages_payload = [{"role": "system", "content": system_prompt},
                                {"role": "user", "content": text}]
            data = {
                "model": self.model,
                "messages": messages_payload,
                "max_tokens": 1500,
                "temperature": 0.3,
                "thinking": {
                    "type": "disabled"
                }
            }
            logger.info(f"Payload: {data}")

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            response = self.session.post(
                self.api_url,
                json=data,
                headers=headers,
                timeout=(5, 30)
            )
            response.raise_for_status()
            raw_response = response.json()
            logger.info(f"Raw resulf from AI: {raw_response}")
            return self._parse_response(raw_response)
        except requests.exceptions.Timeout:
            logger.error(
                "DeepSeek API timeout for user_id=%s, language_pair_id=%s",
                language_pair.user_id,
                language_pair.id,
            )
            raise
                    
        except requests.exceptions.RequestException as e:
            logger.exception(f"HTTP error during AI generation: {e}")
            raise
                    
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            logger.exception(f"Unexpected response format from DeepSeek API: {e}")
            raise 
                    




