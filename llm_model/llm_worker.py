import re
import json
import time
import requests as http_requests
from dotenv import load_dotenv
import os

# Load variables from .env
load_dotenv()

# JSON schema description passed to both Gemini and Ollama as text
JSON_SCHEMA = """{
  "is_interview": boolean,
  "company_name": "string",
  "role": "string (SDE I, SDE II, SRE, Data Analyst, ML Engineer, PM, etc. Include level like L4/L5/E4/IC3)",
  "interview_date": "string",
  "location": "string (city/country/remote/hybrid)",
  "experience_level": "string (fresher, 0 YOE, 2 years, 5+ years, senior)",
  "rounds": [{"round_number": int, "round_type": "string (OA/Technical/DSA/System Design/Behavioral/HLD/LLD/Machine Coding/HR/Bar Raiser)", "questions": ["string — FULL question text with complete problem statement, constraints, examples, and follow-ups. Never summarize."]}],
  "result": "string (selected/rejected/ghosted/pending/offer_received/offer_declined/unknown)",
  "offered_salary": "string (with currency: 45 LPA, $180k, 1.87L/month)",
  "old_salary": "string",
  "compensation": {"stock": "string", "bonus": "string", "benefits": "string", "joining_bonus": "string"},
  "interview_type": "string (onsite/virtual/phone/mixed)",
  "difficulty": "string (easy/medium/hard/LC Easy/LC Medium/LC Hard)",
  "topics_covered": ["string (Arrays, HashMap, Trees, Graphs, DP, BFS, DFS, Binary Search, System Design, HLD, LLD, OS, DBMS, etc.)"],
  "programming_languages": ["string"],
  "tips": "string",
  "process_duration": "string (2 weeks, 1 month, 3 days)",
  "referral_used": "string (yes/no/details)",
  "team_or_org": "string (AWS, Alexa, Uber Eats, Google Cloud, etc.)",
  "other_details": "string"
}"""

SYSTEM_INSTRUCTION = (
    "You are an expert at analyzing interview discussion posts from LeetCode. "
    "Your job is to extract structured interview data from the provided text.\n\n"
    "STEP 1 — CLASSIFICATION:\n"
    "Determine if this post describes a REAL interview experience, hiring process, "
    "or compensation/offer discussion at a specific company. Set is_interview=true "
    "ONLY for these. Set is_interview=false for:\n"
    "  - Generic preparation guides ('How to prepare for Amazon')\n"
    "  - Study plans or resource lists without interview context\n"
    "  - Motivational or career advice posts\n"
    "  - Posts asking for advice without sharing an experience\n\n"
    "STEP 2 — EXTRACTION:\n"
    "Extract ALL available information into the structured fields. "
    "For fields not mentioned in the text, return empty string or empty array.\n\n"
    "RULES:\n"
    "- Extract questions with FULL DETAIL — include the complete problem "
    "description, constraints, input/output format, and examples if mentioned. "
    "Do NOT summarize or paraphrase. Copy the question text as-is from the post. "
    "If the author describes a coding problem in multiple sentences, include ALL "
    "of those sentences as the question text, not just a one-line summary.\n"
    "- If the author mentions a LeetCode problem by name or number (e.g. 'Two Sum', "
    "'LRU Cache', '76. Minimum Window Substring'), include the exact name/number "
    "AND any additional details or variations they describe\n"
    "- Include follow-up questions as separate entries with all their details\n"
    "- For each round, classify its type (OA, Technical, System Design, "
    "Behavioral, HR, etc.)\n"
    "  - Question dumps without a described interview experience\n"
    "- Salary values must include currency/unit exactly as written "
    "(LPA, USD, monthly, stipend, CTC, etc.)\n"
    "- For result, distinguish between: selected, rejected, ghosted, "
    "pending, offer_received, offer_declined, unknown\n"
    "- Extract experience level from context clues: '2024 grad' = fresher, "
    "'working for 3 years' = 3 years, etc.\n"
    "- If multiple companies are discussed, focus on the PRIMARY company "
    "the interview is about\n"
    "- If images are attached, they are screenshots from the post. "
    "Extract any visible questions, code snippets, salary details, "
    "offer letters, or interview details from the images and include "
    "them in the relevant fields.\n\n"
    "Return ONLY valid JSON matching this schema:\n" + JSON_SCHEMA
)


# =====================================================================
# Backend: Ollama (local, unlimited, no API key needed)
# =====================================================================
class OllamaWorker:

    MAX_RETRIES = 3

    def __init__(self, model="qwen2.5:7b-instruct", base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def run(self, text, image_parts=None, system_instruction=None):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self.call_llm(text, image_parts, system_instruction)
            except json.JSONDecodeError as e:
                print(f"\n  JSON parse error (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt == self.MAX_RETRIES:
                    return None
            except Exception as e:
                print(f"\n  Ollama error (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt == self.MAX_RETRIES:
                    return None
                time.sleep(2 * attempt)
        return None

    def call_llm(self, text, image_parts=None, system_instruction=None):
        import base64

        messages = [
            {"role": "system", "content": system_instruction or SYSTEM_INSTRUCTION},
            {"role": "user", "content": text},
        ]

        # image_parts = list of (bytes, mime_type) tuples
        if image_parts:
            images_b64 = []
            for data, mime_type in image_parts:
                images_b64.append(base64.b64encode(data).decode())
            if images_b64:
                messages[-1]["images"] = images_b64

        resp = http_requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192},
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]

        clean = re.sub(r"```(?:json)?\n?|```", "", content).strip()
        return json.loads(clean)


# =====================================================================
# Backend: Gemini (cloud, rate-limited, supports native schema + vision)
# =====================================================================
class GeminiWorker:

    MAX_RETRIES = 3
    MIN_REQUEST_GAP = 5  # 15 RPM on 3.1 Flash Lite → 60/15 = 4s + buffer
    _shared_last_request_time = 0.0  # shared across all instances (same API key)

    def __init__(self, api_key=None):
        from google import genai
        self.genai = genai
        self.client = genai.Client(api_key=api_key or os.getenv("API_KEY"))

    def _throttle(self):
        elapsed = time.time() - GeminiWorker._shared_last_request_time
        if elapsed < self.MIN_REQUEST_GAP:
            time.sleep(self.MIN_REQUEST_GAP - elapsed)
        GeminiWorker._shared_last_request_time = time.time()

    def run(self, text, image_parts=None, system_instruction=None):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._throttle()
                return self.call_llm(text, image_parts, system_instruction)
            except json.JSONDecodeError as e:
                print(f"\n  JSON parse error (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt == self.MAX_RETRIES:
                    return None
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait = self._parse_retry_delay(err_str, default=15)
                    print(f"\n  Rate limited (attempt {attempt}/{self.MAX_RETRIES}), waiting {wait}s...")
                    time.sleep(wait)
                elif "503" in err_str or "UNAVAILABLE" in err_str:
                    wait = 5 * attempt
                    print(f"\n  Service unavailable (attempt {attempt}/{self.MAX_RETRIES}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"\n  LLM error: {e}")
                    return None
        return None

    def _parse_retry_delay(self, err_str, default=15):
        match = re.search(r"retry\s*in\s*([\d.]+)s", err_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) + 1
        return default

    def call_llm(self, text, image_parts=None, system_instruction=None):
        from google.genai import types

        contents = [text]
        # image_parts = list of (bytes, mime_type) tuples
        if image_parts:
            for data, mime_type in image_parts:
                contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))

        response = self.client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
                system_instruction=system_instruction or SYSTEM_INSTRUCTION,
            ),
            contents=contents,
        )

        clean = re.sub(r"```(?:json)?\n?|```", "", response.text).strip()
        clean = clean.replace("\\'", "'")
        return json.loads(clean)


# =====================================================================
# Image-only system instruction (shorter, focused on visual extraction)
# =====================================================================
IMAGE_INSTRUCTION = (
    "You are analyzing screenshots attached to a LeetCode interview discussion post. "
    "These images may contain: offer letters, salary breakdowns, interview questions, "
    "code snippets, coding problems, email screenshots, or other interview-related content.\n\n"
    "Extract ALL visible information and return JSON matching this schema:\n" + JSON_SCHEMA + "\n\n"
    "RULES:\n"
    "- Set is_interview based on what you see in the images\n"
    "- Extract salary/compensation numbers EXACTLY as shown (with currency)\n"
    "- Copy any visible code or questions word-for-word\n"
    "- For fields not visible in images, return empty string or empty array\n"
    "- If you see an offer letter, extract: role, salary, stock, bonus, location, team\n"
    "- If you see coding questions, add them to the rounds array\n"
    "- Return ONLY valid JSON, no explanation"
)


# =====================================================================
# Factory: picks backend based on LLM_BACKEND env var
# Set LLM_BACKEND=ollama in .env for local, or LLM_BACKEND=gemini for cloud
# =====================================================================
def InterviewWorker(backend=None, **kwargs):
    backend = backend or os.getenv("LLM_BACKEND", "gemini")

    if backend == "ollama":
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        return OllamaWorker(model=model, base_url=base_url, **kwargs)
    else:
        return GeminiWorker(**kwargs)


# =====================================================================
# Factory: picks vision backend for image-only pass
# IMAGE_BACKEND env var: "gemini" (default, free vision) or "ollama"
# =====================================================================
def ImageWorker(backend=None, **kwargs):
    backend = backend or os.getenv("IMAGE_BACKEND", "gemini")

    if backend == "ollama":
        model = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        return OllamaWorker(model=model, base_url=base_url, **kwargs)
    else:
        return GeminiWorker(**kwargs)
