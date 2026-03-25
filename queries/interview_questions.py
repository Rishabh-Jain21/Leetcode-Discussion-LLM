import json
import re
from collections import defaultdict
from setup_database.setup_db import get_connection


def normalize_role(role):
    """Merge role variations into canonical names."""
    r = role.strip()
    if not r or r.lower() in ("unknown", "n/a", "na", ""):
        return "Unknown"

    # Strip level suffixes like (L60), (L5), (IC3), (E4), (T5), (P6)
    r = re.sub(r"\s*\(.*?\)\s*", " ", r).strip()

    # Lowercase for matching
    low = r.lower()
    low = re.sub(r"[^a-z0-9\s]", " ", low)  # remove special chars
    low = re.sub(r"\s+", " ", low).strip()    # collapse spaces

    # --- Experience levels mistakenly used as roles ---
    if low in ("fresher", "new grad", "new graduate", "entry level",
               "experienced", "senior", "junior", "0 yoe"):
        return "Unknown"

    # --- SDM = Software Development Manager ---
    if re.search(r"\b(sdm|software\s*dev(elopment)?\s*manager)\b", low):
        return "Software Development Manager"

    # --- Level-only strings: L60, L5, E4, IC3, T5, P6, SDE2, etc. ---
    level_only = re.match(r"^(l|e|ic|t|p|sde)\s*(\d+)$", low)
    if level_only:
        prefix, num = level_only.group(1), int(level_only.group(2))
        # Amazon levels: L4=SDE I, L5=SDE II, L6=SDE III, L7=Principal
        # Google levels: L3=SDE I, L4=SDE II, L5=Senior, L6=Staff
        # Meta levels: E3=SDE I, E4=SDE II, E5=Senior, E6=Staff
        # IC levels: IC1/IC2=Junior, IC3=SDE II, IC4=Senior
        if prefix in ("l", "t", "p"):
            if num <= 4: return "SDE I"
            if num == 5: return "SDE II"
            if num == 6: return "SDE III"
            if num >= 7: return "Principal / Staff Engineer"
        if prefix == "e":
            if num <= 3: return "SDE I"
            if num == 4: return "SDE II"
            if num == 5: return "SDE III"
            if num >= 6: return "Principal / Staff Engineer"
        if prefix == "ic":
            if num <= 2: return "SDE I"
            if num == 3: return "SDE II"
            if num == 4: return "SDE III"
            if num >= 5: return "Principal / Staff Engineer"
        if prefix == "sde":
            if num == 1: return "SDE I"
            if num == 2: return "SDE II"
            if num == 3: return "SDE III"

    # --- SDE levels ---
    if re.search(r"\b(sde|software\s*(dev(elopment)?\s*)?engineer)\s*(iii|3)\b", low):
        return "SDE III"
    if re.search(r"\b(sde|software\s*(dev(elopment)?\s*)?engineer)\s*(ii|2)\b", low):
        return "SDE II"
    if re.search(r"\b(sde|software\s*(dev(elopment)?\s*)?engineer)\s*(i|1)\b", low):
        return "SDE I"
    if re.search(r"\b(principal|staff)\b.*\b(sde|engineer)\b", low):
        return "Principal / Staff Engineer"
    if re.search(r"\b(senior|sr|lead)\b.*\b(sde|software\s*(dev(elopment)?\s*)?engineer)\b", low):
        return "Senior SDE"
    if re.search(r"\b(junior|jr|entry)\b.*\b(sde|software\s*(dev(elopment)?\s*)?engineer)\b", low):
        return "SDE I"
    if re.search(r"\b(sde|software\s*(dev(elopment)?\s*)?engineer)\b", low):
        return "SDE"

    # --- Frontend / Backend / Fullstack ---
    if re.search(r"\bfront\s*end\b", low):
        return "Frontend Engineer"
    if re.search(r"\bback\s*end\b", low):
        return "Backend Engineer"
    if re.search(r"\bfull\s*stack\b", low):
        return "Full Stack Engineer"
    if re.search(r"\b(web\s*dev|ui\s*engineer|ui\s*dev)\b", low):
        return "Frontend Engineer"
    if re.search(r"\b(mobile|android|ios)\s*(dev|engineer)?\b", low):
        return "Mobile Engineer"

    # --- Data roles ---
    if re.search(r"\bdata\s*scien", low):
        return "Data Scientist"
    if re.search(r"\bdata\s*engineer", low):
        return "Data Engineer"
    if re.search(r"\b(data\s*anal|business\s*anal|bi\s*anal)\b", low):
        return "Data Analyst"
    if re.search(r"\b(business\s*intel|bi\s*engineer)\b", low):
        return "BI Engineer"

    # --- ML / AI / Research ---
    if re.search(r"\b(ml|machine\s*learning|ai|deep\s*learning)\s*(engineer|dev)?\b", low):
        return "ML Engineer"
    if re.search(r"\bapplied\s*scien", low):
        return "Applied Scientist"
    if re.search(r"\bresearch\s*(scien|engineer)\b", low):
        return "Research Scientist"
    if re.search(r"\b(nlp|computer\s*vision|cv)\s*engineer\b", low):
        return "ML Engineer"

    # --- PM / TPM ---
    if re.search(r"\b(technical\s*program|tpm)\b", low):
        return "Technical Program Manager"
    if re.search(r"\b(product\s*manager|pm)\b", low):
        return "Product Manager"
    if re.search(r"\b(engineering\s*manager|em)\b", low):
        return "Engineering Manager"

    # --- DevOps / SRE / Infra ---
    if re.search(r"\b(sre|site\s*reliab)", low):
        return "SRE"
    if re.search(r"\bdevops\b", low):
        return "DevOps Engineer"
    if re.search(r"\bcloud\b", low):
        return "Cloud Engineer"
    if re.search(r"\b(platform|infra(structure)?)\s*engineer\b", low):
        return "Platform / Infra Engineer"
    if re.search(r"\b(system\s*engineer|systems\s*engineer)\b", low):
        return "Systems Engineer"
    if re.search(r"\bnetwork\s*engineer\b", low):
        return "Network Engineer"
    if re.search(r"\b(security|infosec|appsec)\b", low):
        return "Security Engineer"

    # --- QA / Test ---
    if re.search(r"\b(qa|sdet|test|quality|automation\s*engineer)\b", low):
        return "QA / SDET"

    # --- Intern ---
    if re.search(r"\bintern\b", low):
        return "Intern"

    # --- Solution Architect / Consultant ---
    if re.search(r"\b(solution|solutions)\s*architect\b", low):
        return "Solutions Architect"
    if re.search(r"\b(consultant|consult)\b", low):
        return "Consultant"
    if re.search(r"\barchitect\b", low):
        return "Software Architect"

    # --- Support / TAM ---
    if re.search(r"\b(support\s*engineer|technical\s*support)\b", low):
        return "Support Engineer"
    if re.search(r"\b(tam|technical\s*account)\b", low):
        return "Technical Account Manager"

    # --- Designer ---
    if re.search(r"\b(ux|ui|design)\b", low):
        return "UX / UI Designer"

    # Short unrecognized strings are likely garbage
    if len(low) <= 4:
        return "Unknown"

    return r.title()


# ── Generic-question filtering ────────────────────────────────────

_GENERIC_PATTERNS = [
    r"^(\d+\s+)?(dsa|coding|behavioral|behavioural|lp|leadership\s*principles?)\s*(based\s*)?(questions?|section|round|problems?)?(\s*\(.*\))?$",
    r"^(work\s*(style|simulation)\s*(assessment)?|workstyle)$",
    r"^(standard|basic|general|easy)\s*(oa|dsa|coding)?\s*(questions?|round|section|problems?)?$",
    r"^(coding|debugging|situational|behavioral|behavioural)\s*(section|round|questions?)?$",
    r"^\d+\s*(dsa|coding|medium|hard|easy|greedy|bitwise)[\s,]*(level\s*)?(questions?|problems?)?.*$",
    r"^(introduction|self[- ]introduction.*)$",
    r"^(discussion\s*(on|around|about)\s*(projects?|resume|experience))$",
    r"^(past\s*projects?|resume\s*deep\s*dive|project\s*discussion)$",
    r"^(general\s*questions?|follow[- ]?up\s*questions?.*)$",
    r"^problem\s*\d+.*(?:test\s*cases|approach|passed).*$",
    r"^\d+[./]\s*\d+(/\d+)?$",
    r"^(amazon\s*)?lp\s*(based\s*)?(scenario\s*)?(based\s*)?(questions?)?$",
    r"^(behavioral|behavioural)\s*(questions?|aspects?|section)?$",
    r"^(technical|cs)\s*(fundamentals?|questions?)?$",
    r"^(completed|solved)\s*\d+\s*(parts?|questions?|problems?)$",
    r"^(entities|implementation|challenges?\s*faced)$",
    r"^(spring|os|internal\s*implementations.*)$",
    r"^(two|2|one|1|three|3|four|4)\s*(medium|easy|hard)?\s*(level\s*)?(coding|dsa)?\s*(questions?|problems?)$",
    r"^(leadership\s*principles?|amazon\s*lp)\s*(questions?|discussion)?$",
    r"^(dsa|lp|hr|behavioral|behavioural)$",
    r"^(work\s*simulation|survey.*)$",
    r"^(coding\s*(challenge|section|round)|debugging\s*(round|section))$",
    r"^(lp\s*(scenario\s*based|principles?)\s*questions?)$",
    r"^(scenario[- ]based\s*.*questions?)$",
    r"^all\s*test\s*cases\s*passed.*$",
]


def _is_generic(q):
    """Return True if the question is too vague/generic to be useful."""
    low = q.strip().lower()
    low = re.sub(r"[^a-z0-9\s/]", "", low).strip()
    low = re.sub(r"\s+", " ", low)

    if len(low) < 8:
        return True

    for pat in _GENERIC_PATTERNS:
        if re.match(pat, low):
            return True

    return False


def _normalize_qkey(q):
    """Normalized key for deduplication."""
    q = q.strip().lower()
    q = re.sub(r"https?://\S+", "", q)
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


# ── Main query ────────────────────────────────────────────────────

def get_unique_questions(company):
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, rounds_json FROM interview_experiences WHERE company_name = ? AND is_interview = 1",
        (company,),
    ).fetchall()
    conn.close()

    # role -> round_type -> {norm_key: [display_question, count]}
    data = defaultdict(lambda: defaultdict(dict))

    for row in rows:
        role = normalize_role(row["role"] or "")
        rounds = json.loads(row["rounds_json"] or "[]")

        # Track per-post to avoid double-counting within one interview
        seen_in_post = set()

        for r in rounds:
            round_type = r.get("round_type", "Unknown").strip()
            if round_type.startswith("[From Linked Post] "):
                round_type = round_type.replace("[From Linked Post] ", "")
            for q in r.get("questions", []):
                q = q.strip()
                if not q or q.startswith("[Linked") or _is_generic(q):
                    continue

                key = _normalize_qkey(q)
                dedup = (role, round_type, key)
                if dedup in seen_in_post:
                    continue
                seen_in_post.add(dedup)

                bucket = data[role][round_type]
                if key in bucket:
                    bucket[key][1] += 1
                else:
                    bucket[key] = [q, 1]

    # Build output sorted by count desc, then alphabetically
    result = {}
    for role in sorted(data.keys()):
        result[role] = {}
        for round_type in sorted(data[role].keys()):
            items = data[role][round_type]
            sorted_items = sorted(items.values(), key=lambda x: (-x[1], x[0]))
            result[role][round_type] = [
                {"question": q, "count": c} if c > 1 else q
                for q, c in sorted_items
            ]

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m queries.interview_questions <company>")
        sys.exit(1)

    company = sys.argv[1]
    result = get_unique_questions(company)

    # Save to JSON file
    import os
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{company}_questions.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total_q = sum(len(qs) for role in result.values() for qs in role.values())
    top_asked = []
    for role, rounds in result.items():
        for rt, questions in rounds.items():
            for item in questions:
                if isinstance(item, dict):
                    top_asked.append((item["count"], item["question"], role, rt))
    top_asked.sort(key=lambda x: -x[0])

    print(f"{company}: {total_q} unique questions | {len(result)} roles")
    if top_asked:
        print(f"\nTop repeated questions:")
        for count, q, role, rt in top_asked[:15]:
            print(f"  [{count}x] ({role} / {rt}) {q}")
    print(f"\nSaved to: {out_path}")
