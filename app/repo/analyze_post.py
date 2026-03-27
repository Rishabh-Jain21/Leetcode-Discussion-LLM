"""
Analyze a single LeetCode discussion post via URL or topic ID.

Usage:
    python -m queries.analyze_post <url_or_topic_id>
    python -m queries.analyze_post https://leetcode.com/discuss/post/7178524/...
    python -m queries.analyze_post 7178524
"""

import json
import re
import sys
import time
import requests
import os
from app.llm_model.llm_worker import LLMWorker, IMAGE_INSTRUCTION


# ── GraphQL fetch ─────────────────────────────────────────────────

GRAPHQL_URL = "https://leetcode.com/graphql/"

HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://leetcode.com",
    "referer": "https://leetcode.com/discuss/",
    "user-agent": "Mozilla/5.0",
}

QUERY_FULL = """
query discussPostDetail($topicId: ID!) {
    ugcArticleDiscussionArticle(topicId: $topicId) {
        uuid
        title
        content
        createdAt
        author { userName }
    }
}"""


def fetch_post(topic_id):
    """Fetch a single discussion post from LeetCode GraphQL API."""
    payload = {
        "operationName": "discussPostDetail",
        "variables": {"topicId": topic_id},
        "query": QUERY_FULL,
    }
    resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    article = data.get("data", {}).get("ugcArticleDiscussionArticle")
    if not article:
        raise ValueError(f"Post {topic_id} not found or inaccessible")
    return article


# ── URL helpers ───────────────────────────────────────────────────


def extract_urls(text):
    """Extract and group URLs from post content."""
    md_urls = re.findall(r"\((https?://[^\s)]+)\)", text)
    all_urls = re.findall(r"(?:https?://)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s)\]]*", text)
    urls = list(set(md_urls + all_urls))

    assets, others = [], []
    for url in urls:
        if not url.startswith("http"):
            url = "https://" + url
        if "assets.leetcode.com" in url:
            assets.append(url)
        else:
            others.append(url)
    return assets, others


def extract_topic_id(input_str):
    """Extract topic ID from a URL or raw number."""
    input_str = input_str.strip()
    if input_str.isdigit():
        return int(input_str)
    m = re.search(
        r"leetcode\.com/discuss/(?:post|interview-experience|general-discussion)/(\d+)",
        input_str,
    )
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract topic ID from: {input_str}")


def download_images(asset_urls, max_images=5):
    """Download images and return list of (bytes, mime_type) tuples."""
    parts = []
    for url in asset_urls[:max_images]:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            ct = resp.headers.get("content-type", "")
            if not ct.startswith("image/"):
                continue
            parts.append((resp.content, ct.split(";")[0]))
        except Exception:
            continue
    return parts


def extract_leetcode_links(urls):
    """Extract LeetCode problem slugs and linked discussion IDs from URLs."""
    problem_links = []
    linked_post_ids = []

    for url in urls:
        pm = re.search(r"leetcode\.com/problems/([\w-]+)", url)
        if pm:
            full = f"https://leetcode.com/problems/{pm.group(1)}/"
            if full not in problem_links:
                problem_links.append(full)
            continue

        dm = re.search(
            r"leetcode\.com/discuss/(?:post|interview-experience|general-discussion)/(\d+)",
            url,
        )
        if dm:
            tid = int(dm.group(1))
            if tid not in linked_post_ids:
                linked_post_ids.append(tid)

    return problem_links, linked_post_ids


# ── Merge helper ──────────────────────────────────────────────────


def merge_results(parent, linked):
    """Merge linked post LLM result into parent."""
    parent_rounds = parent.get("rounds", [])
    linked_rounds = linked.get("rounds", [])

    if linked_rounds:
        max_round = max((r.get("round_number", 0) for r in parent_rounds), default=0)
        for r in linked_rounds:
            r["round_number"] = max_round + r.get("round_number", 1)
            r["round_type"] = f"[From Linked Post] {r.get('round_type', 'Unknown')}"
            parent_rounds.append(r)
        parent["rounds"] = parent_rounds

    # Fill empty parent fields from linked
    for key in linked:
        if key == "rounds":
            continue
        parent_val = parent.get(key)
        linked_val = linked.get(key)
        if not parent_val and linked_val:
            parent[key] = linked_val

    return parent


# ── Main analysis ─────────────────────────────────────────────────


def analyze_post(input_str):
    """Full pipeline: fetch → extract → LLM → return structured JSON."""
    topic_id = extract_topic_id(input_str)
    print(f"Fetching post {topic_id}...")

    article = fetch_post(topic_id)
    title = article.get("title", "")
    content = article.get("content", "")
    created_at = article.get("createdAt", "")
    author = (article.get("author") or {}).get("userName", "")

    print(f"  Title: {title}")
    print(f"  Author: {author}  |  Created: {created_at}")

    # Extract URLs
    asset_urls, other_urls = extract_urls(content)
    all_urls = asset_urls + other_urls
    problem_links, linked_post_ids = extract_leetcode_links(all_urls)

    print(
        f"  Images: {len(asset_urls)}  |  Links: {len(other_urls)}  |  Linked posts: {len(linked_post_ids)}"
    )

    # Step 1: Text LLM
    worker = LLMWorker()
    print("  Running text analysis...")
    t0 = time.time()
    prompt = f"Title: {title}\n\nContent:\n{content}"
    result = worker.run(prompt)
    print(f"  Text LLM responded in {time.time() - t0:.1f}s")

    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        print("  ERROR: LLM did not return valid JSON")
        return None

    # Step 2: Vision pass
    if asset_urls:
        print(f"  Downloading {len(asset_urls)} image(s)...")
        image_parts = download_images(asset_urls)
        if image_parts:
            vision_worker = LLMWorker()
            print(f"  Running vision analysis on {len(image_parts)} image(s)...")
            t0 = time.time()
            vision_result = vision_worker.run(
                f"Post title: {title}\nAnalyze these {len(image_parts)} image(s) from this interview discussion post.",
                image_parts=image_parts,
                system_instruction=IMAGE_INSTRUCTION,
            )
            print(f"  Vision LLM responded in {time.time() - t0:.1f}s")
            if isinstance(vision_result, list):
                vision_result = vision_result[0] if vision_result else None
            if isinstance(vision_result, dict):
                result = merge_results(result, vision_result)

    # Step 3: Add problem links
    if problem_links:
        rounds = result.get("rounds", [])
        if rounds:
            for link in problem_links:
                rounds[-1].setdefault("questions", []).append(
                    f"[Linked Problem] {link}"
                )
        else:
            result["rounds"] = [
                {
                    "round_number": 1,
                    "round_type": "Unknown",
                    "questions": [f"[Linked Problem] {link}" for link in problem_links],
                }
            ]

    # Step 4: Fetch and merge linked discussion posts
    if linked_post_ids:
        print(f"  Processing {len(linked_post_ids)} linked discussion post(s)...")
        for tid in linked_post_ids:
            try:
                print(f"    Fetching linked post {tid}...")
                linked_article = fetch_post(tid)
                linked_content = linked_article.get("content", "")
                linked_title = linked_article.get("title", "")
                if not linked_content:
                    continue

                linked_result = worker.run(
                    f"Content from linked post (topic {tid}):\n{linked_content}"
                )
                if isinstance(linked_result, list):
                    linked_result = linked_result[0] if linked_result else None
                if not isinstance(linked_result, dict):
                    continue

                # Vision for linked post images
                linked_assets, _ = extract_urls(linked_content)
                if linked_assets:
                    linked_images = download_images(linked_assets)
                    if linked_images:
                        if not hasattr(analyze_post, "_vision_worker"):
                            analyze_post._vision_worker = LLMWorker()
                        vr = analyze_post._vision_worker.run(
                            f"Post title: {linked_title}\nAnalyze these {len(linked_images)} image(s).",
                            image_parts=linked_images,
                            system_instruction=IMAGE_INSTRUCTION,
                        )
                        if isinstance(vr, list):
                            vr = vr[0] if vr else None
                        if isinstance(vr, dict):
                            linked_result = merge_results(linked_result, vr)

                result = merge_results(result, linked_result)
                print(f"    Merged linked post {tid}")
            except Exception as e:
                print(f"    Failed linked post {tid}: {e}")

    return result


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m queries.analyze_post <url_or_topic_id>")
        print(
            "  e.g. python -m queries.analyze_post https://leetcode.com/discuss/post/7178524/..."
        )
        print("  e.g. python -m queries.analyze_post 7178524")
        sys.exit(1)

    input_arg = sys.argv[1]
    result = analyze_post(input_arg)

    if result:
        print("\n" + "=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # Optionally save
        if len(sys.argv) > 2 and sys.argv[2] == "--save":

            out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(out_dir, exist_ok=True)
            topic_id = extract_topic_id(input_arg)
            out_path = os.path.join(out_dir, f"post_{topic_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\nSaved to: {out_path}")
    else:
        print("\nFailed to analyze post.")
        sys.exit(1)
