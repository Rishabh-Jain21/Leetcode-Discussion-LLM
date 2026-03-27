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
    "You are an expert at analyzing LeetCode interview discussion posts. "
    "Your task is to extract structured interview data ONLY from explicitly provided content.\n\n"
    "STEP 1 — CLASSIFICATION:\n"
    "Determine if the post describes a REAL interview experience, hiring process, "
    "or compensation/offer discussion at a specific company.\n"
    "Set is_interview=true ONLY if clearly stated.\n"
    "Set is_interview=false for:\n"
    "  - Preparation guides\n"
    "  - Study plans\n"
    "  - General advice\n"
    "  - Questions asking for help\n"
    "  - Question dumps without interview context\n"
    "If unsure, set is_interview=false.\n\n"
    "STEP 2 — EXTRACTION:\n"
    "Extract ONLY explicitly stated information. Do NOT infer or assume anything.\n\n"
    "CRITICAL ANTI-HALLUCINATION RULES:\n"
    "- Do NOT make up any questions, rounds, company details, or outcomes\n"
    "- Do NOT infer missing information\n"
    "- Do NOT paraphrase or summarize questions\n"
    "- If a field is not explicitly mentioned, return empty values:\n"
    '    - Use "" for strings\n'
    "    - Use [] for arrays\n\n"
    "IMAGE-ONLY RULE (VERY IMPORTANT):\n"
    "If the post contains ONLY image URLs OR images with no readable text:\n"
    "- Return a completely blank JSON (all fields empty/default)\n"
    "- Do NOT generate or guess any questions or details\n\n"
    "QUESTION EXTRACTION RULES:\n"
    "- Copy questions EXACTLY as written\n"
    "- Include full details: description, constraints, examples\n"
    "- If question spans multiple sentences, include ALL of them\n"
    "- If a LeetCode problem is mentioned (e.g., 'Two Sum', '146. LRU Cache'), "
    "include the exact name/number AND any described variation\n"
    "- Treat follow-up questions as separate entries\n"
    "- Do NOT summarize or shorten questions\n\n"
    "ROUND CLASSIFICATION:\n"
    "Classify rounds ONLY if clearly mentioned:\n"
    "  - OA\n"
    "  - Technical\n"
    "  - System Design\n"
    "  - Behavioral\n"
    "  - HR\n"
    "If unclear, leave empty.\n\n"
    "SALARY RULES:\n"
    "- Extract salary EXACTLY as written (e.g., '20 LPA', '120k USD', '₹50k/month')\n"
    "- Do NOT convert or estimate\n\n"
    "RESULT FIELD:\n"
    "Use ONLY one of:\n"
    "  - selected\n"
    "  - rejected\n"
    "  - ghosted\n"
    "  - pending\n"
    "  - offer_received\n"
    "  - offer_declined\n"
    "  - unknown\n"
    "If not explicitly mentioned, use 'unknown'.\n\n"
    "EXPERIENCE LEVEL:\n"
    "Extract ONLY if clearly stated (e.g., '3 years experience').\n"
    "Otherwise return empty string.\n\n"
    "MULTIPLE COMPANIES:\n"
    "Focus ONLY on the primary company discussed.\n\n"
    "FINAL OUTPUT:\n"
    "Return ONLY valid JSON matching this schema:\n" + JSON_SCHEMA
)


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
                print(
                    f"\n  JSON parse error (attempt {attempt}/{self.MAX_RETRIES}): {e}"
                )
                if attempt == self.MAX_RETRIES:
                    return None
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait = self._parse_retry_delay(err_str, default=15)
                    print(
                        f"\n  Rate limited (attempt {attempt}/{self.MAX_RETRIES}), waiting {wait}s..."
                    )
                    time.sleep(wait)
                elif "503" in err_str or "UNAVAILABLE" in err_str:
                    wait = 5 * attempt
                    print(
                        f"\n  Service unavailable (attempt {attempt}/{self.MAX_RETRIES}), waiting {wait}s..."
                    )
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

        clean = re.sub(r"```(?:json)?\n?|```", "", response.text).strip()  # type: ignore
        clean = clean.replace("\\'", "'")
        return json.loads(clean)


# =====================================================================
# Image-only system instruction (hallucination-resistant version)
# =====================================================================
IMAGE_INSTRUCTION = (
    "You are analyzing screenshots(given as bytes) attached to a LeetCode interview discussion post. "
    "These images may contain: offer letters, salary breakdowns, interview questions, "
    "code snippets, coding problems, email screenshots, or other interview-related content.\n\n"
    "Extract ALL visible information and return JSON matching this schema:\n"
    + JSON_SCHEMA
    + "\n\n"
    "STRICT RULES (NO HALLUCINATION):\n"
    "- ONLY extract information that is explicitly visible in the images\n"
    "- DO NOT infer, assume, or guess any missing information\n"
    "- If a round/question is not shown, DO NOT create or assume it\n"
    "- If later rounds (e.g., Round 2/3) are visible but earlier rounds are NOT shown, leave earlier rounds EMPTY\n"
    "- Do NOT assume any standard interview structure (e.g., DSA, System Design, HR rounds)\n"
    "- If text is partially visible or cut off, extract only the visible portion without guessing\n\n"
    "INTERVIEW DETECTION:\n"
    "- Set is_interview = true ONLY if the image clearly indicates an interview process\n"
    "- Otherwise set is_interview = false\n\n"
    "EXTRACTION RULES:\n"
    "- Extract salary/compensation numbers EXACTLY as shown (with currency)\n"
    "- Copy any visible code, questions, or text word-for-word\n"
    "- Do NOT paraphrase or summarize\n"
    "- If you see an offer letter, extract: role, salary, stock, bonus, location, team\n"
    "- Add questions to rounds ONLY if the round is explicitly labeled in the image\n\n"
    "MISSING DATA RULES:\n"
    "- For fields not visible in images, return empty string or empty array\n"
    "- Do NOT fabricate or fill placeholder values\n\n"
    "OUTPUT:\n"
    "- Return ONLY valid JSON, no explanation"
)


def LLMWorker(backend=None, **kwargs) -> GeminiWorker:
    backend = backend or os.getenv("LLM_BACKEND", "gemini")
    return GeminiWorker(**kwargs)
