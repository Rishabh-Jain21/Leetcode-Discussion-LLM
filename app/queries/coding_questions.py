"""
Extract only coding/DSA questions from interview experiences.

Usage:
    python -m queries.coding_questions <company>
    python -m queries.coding_questions google
    python -m queries.coding_questions amazon --role "SDE II"
"""
import json
import re
import sys
from collections import defaultdict
from setup_database.setup_db import get_connection
from queries.interview_questions import normalize_role, _is_generic, _normalize_qkey


# ── Round-type classification ────────────────────────────────────

_CODING_ROUND_TYPES = {
    "dsa", "coding", "dsa/coding", "dsa/lld", "technical", "technical/dsa",
    "oa", "machine coding", "programming", "phone screen", "phone screening",
    "screening", "psds", "bug squash", "assignment", "onsite",
    "integration", "integration round", "logic and maintainable code",
    "dsa + behavioral", "behavioral/dsa", "algorithmic coding",
}

_NON_CODING_ROUND_TYPES = {
    "behavioral", "bar raiser", "behavioral/bar raiser", "hr",
    "hm", "hm round", "hiring manager", "managerial round",
    "team fit", "team match", "team matching",
    "gnl", "googliness", "tps",
    "system design", "hld", "design",
    "resume shortlisting", "unknown",
    "ai/ml", "ml domain", "android domain", "gen ai fluency",
    "technical/behavioral",
}


def _is_coding_round(round_type):
    """Return True if the round type is coding/DSA-related."""
    low = round_type.strip().lower()
    # Strip "[From Linked Post] " prefix
    low = re.sub(r"^\[from linked post\]\s*", "", low)

    if low in _CODING_ROUND_TYPES:
        return True
    if low in _NON_CODING_ROUND_TYPES:
        return False

    # Heuristic: if it contains coding/dsa/oa keywords, include it
    if re.search(r"\b(dsa|coding|oa|algorithm|machine\s*coding|programming|technical)\b", low):
        return True

    return False


# ── Question-level filter ────────────────────────────────────────

_NON_CODING_Q_PATTERNS = [
    r"^(tell\s*me\s*about\s*(yourself|your)|introduce\s*yourself|self[- ]introduction)",
    r"^(why\s*(this|our|do you want)|what\s*motivates|where\s*do\s*you\s*see)",
    r"^(describe\s*a\s*time|give\s*(me\s*)?an?\s*example|tell\s*me\s*about\s*a\s*time)",
    r"^(what\s*are\s*your\s*(strengths|weaknesses|hobbies))",
    r"^(leadership\s*principle|lp\s*|amazon\s*lp|behavioral)",
    r"^(discuss(ion)?\s*(of|on|about)\s*(project|resume|experience))",
    r"^(a\s*challenging\s*project|projects?\s*(discussion|deep\s*dive))",
    r"^(how\s*(you|do you)\s*(learn|handle|deal|manage|approach)\s*(new\s*tech|conflict|stress|pressure|failure))",
    r"^(academics?|cgpa|backlogs?|college\s*details)",
    r"^(preferred\s*programming\s*language|coding\s*profile)",
    r"^(preparation\s*strategy|number\s*of\s*problems?\s*solved)",
    r"^(salary\s*expect|compensation|notice\s*period|joining\s*date|relocation)",
    r"^(oops?\s*concepts?|core\s*java\s*concepts?|teach\s*a\s*dsa\s*topic)",
]


def _is_non_coding_question(q):
    """Return True if the question is behavioral/HR, not a coding question."""
    low = q.strip().lower()
    low = re.sub(r"[^a-z0-9\s/]", "", low).strip()
    for pat in _NON_CODING_Q_PATTERNS:
        if re.match(pat, low):
            return True
    return False


# ── Main query ───────────────────────────────────────────────────

def get_coding_questions(company, role_filter=None):
    conn = get_connection()
    rows = conn.execute(
        "SELECT topic_id, role, rounds_json FROM interview_experiences WHERE company_name = ? AND is_interview = 1",
        (company,),
    ).fetchall()
    conn.close()

    # role -> round_type -> {norm_key: [display_question, count, topic_ids]}
    data = defaultdict(lambda: defaultdict(dict))

    for row in rows:
        role = normalize_role(row["role"] or "")
        if role_filter and role.lower() != role_filter.lower():
            continue

        topic_id = row["topic_id"]
        rounds = json.loads(row["rounds_json"] or "[]")
        seen_in_post = set()

        for r in rounds:
            round_type = r.get("round_type", "Unknown").strip()
            # Strip linked post prefix for classification
            clean_rt = re.sub(r"^\[From Linked Post\]\s*", "", round_type)

            if not _is_coding_round(clean_rt):
                continue

            for q in r.get("questions", []):
                q = q.strip()
                if not q or q.startswith("[Linked"):
                    continue
                if _is_generic(q) or _is_non_coding_question(q):
                    continue

                key = _normalize_qkey(q)
                dedup = (role, clean_rt, key)
                if dedup in seen_in_post:
                    continue
                seen_in_post.add(dedup)

                bucket = data[role][clean_rt]
                if key in bucket:
                    bucket[key][1] += 1
                    bucket[key][2].add(topic_id)
                else:
                    bucket[key] = [q, 1, {topic_id}]

    # Build output sorted by count desc
    result = {}
    for role in sorted(data.keys()):
        result[role] = {}
        for round_type in sorted(data[role].keys()):
            items = data[role][round_type]
            sorted_items = sorted(items.values(), key=lambda x: (-x[1], x[0]))
            result[role][round_type] = [
                {"question": q, "count": c, "topic_ids": sorted(tids)}
                if c > 1
                else {"question": q, "topic_id": sorted(tids)[0]}
                for q, c, tids in sorted_items
            ]

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m queries.coding_questions <company> [--role <role>]")
        sys.exit(1)

    company = sys.argv[1]
    role_filter = None
    if "--role" in sys.argv:
        idx = sys.argv.index("--role")
        if idx + 1 < len(sys.argv):
            role_filter = sys.argv[idx + 1]

    result = get_coding_questions(company, role_filter)

    # Save to JSON
    import os
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(out_dir, exist_ok=True)
    suffix = f"_{role_filter.replace(' ', '_').lower()}" if role_filter else ""
    out_path = os.path.join(out_dir, f"{company}_coding_questions{suffix}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total_q = sum(len(qs) for role in result.values() for qs in role.values())
    repeated = []
    for role, rounds in result.items():
        for rt, questions in rounds.items():
            for item in questions:
                if "count" in item:
                    repeated.append((item["count"], item["question"], role, rt))
    repeated.sort(key=lambda x: -x[0])

    print(f"{company}: {total_q} coding questions | {len(result)} roles")
    if role_filter:
        print(f"  Filtered to role: {role_filter}")
    if repeated:
        print(f"\nTop repeated coding questions:")
        for count, q, role, rt in repeated[:15]:
            print(f"  [{count}x] ({role} / {rt}) {q}")
    print(f"\nSaved to: {out_path}")
