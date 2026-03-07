import re
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

# Load variables from .env
load_dotenv()

# Extended response schema for interview discussions
response_schema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "Company Name": types.Schema(
            type=types.Type.STRING, description="Full name of the company"
        ),
        "Role / Position": types.Schema(
            type=types.Type.STRING, description="Job title or role"
        ),
        "Dates of Posting": types.Schema(
            type=types.Type.STRING, description="Date the job was posted"
        ),
        "Dates of Interview": types.Schema(
            type=types.Type.STRING, description="Date(s) of the interview"
        ),
        "Rounds": types.Schema(
            type=types.Type.ARRAY,
            description="Details of each interview round",
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "Round Number": types.Schema(
                        type=types.Type.NUMBER, description="Round count"
                    ),
                    "Questions": types.Schema(
                        type=types.Type.ARRAY,
                        description="List of questions for the round",
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "Similar Questions": types.Schema(
                        type=types.Type.ARRAY,
                        description="Links to similar questions/problems online, if found",
                        items=types.Schema(type=types.Type.STRING),
                    ),
                },
                required=["Round Number", "Questions", "Similar Questions"],
            ),
        ),
        "Offered Salary Description": types.Schema(
            type=types.Type.STRING, description="Salary offered, if mentioned"
        ),
        "Old Salary": types.Schema(
            type=types.Type.STRING, description="Previous salary, if mentioned"
        ),
        "Interview Outcome": types.Schema(
            type=types.Type.STRING,
            description="Result of interview, e.g., Accepted/Rejected",
        ),
        "Interview Experience Details": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "Interview Type": types.Schema(
                    type=types.Type.STRING, description="Onsite, Remote, Phone, etc."
                ),
                "Difficulty": types.Schema(
                    type=types.Type.STRING, description="Easy/Medium/Hard or rating"
                ),
                "Interviewer Feedback": types.Schema(
                    type=types.Type.STRING, description="Feedback if mentioned"
                ),
            },
            required=["Interview Type", "Difficulty"],
        ),
        "Technical Specifics": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "Programming Languages": types.Schema(
                    type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
                ),
                "Topics Covered": types.Schema(
                    type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
                ),
                "Coding Platform": types.Schema(type=types.Type.STRING),
            },
        ),
        "Timing & Logistics": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "Duration per Round": types.Schema(type=types.Type.STRING),
                "Waiting Time Between Rounds": types.Schema(type=types.Type.STRING),
                "Total Process Duration": types.Schema(type=types.Type.STRING),
            },
        ),
        "Extras": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "Tips": types.Schema(type=types.Type.STRING),
                "Notes on Company Culture": types.Schema(type=types.Type.STRING),
                "Referrals / Recruiter Info": types.Schema(type=types.Type.STRING),
            },
        ),
    },
    required=["Company Name", "Role / Position", "Rounds"],
)


class InterviewWorker:

    def __init__(self, api_key=os.getenv("API_KEY")):
        self.client = genai.Client(api_key=api_key)

    def run(self, text):
        """
        Main function to extract structured interview data from provided text.
        """
        try:
            return [self.call_llm(text)]
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return []

    def call_llm(self, text):
        """
        Calls LLM to extract interview discussion info and link questions to known problems online.
        """
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
                response_schema=response_schema,
                system_instruction=(
                    "Extract structured interview data from the provided text. "
                    "For each round, if any coding or technical question is mentioned, "
                    "provide links to similar problems online if known. "
                    "Return clean JSON only without extra formatting."
                ),
            ),
            contents=text,
        )

        # Clean response and parse as JSON
        try:
            clean = re.sub(r"```(?:json)?\\n?|```", "", response.text).strip()  # type: ignore
            clean = clean.replace("'", '"')
            return json.loads(clean)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return None
