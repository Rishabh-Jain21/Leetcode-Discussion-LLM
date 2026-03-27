import json
import re
import sys
import time
import requests
from datetime import datetime, timezone

from app.setup_database.setup_db import get_connection
from app.llm_model.llm_worker import LLMWorker, IMAGE_INSTRUCTION


def _status(msg):
    # Strip non-ascii chars (emojis) to avoid cp1252 encoding errors on Windows
    safe = msg.encode("ascii", errors="ignore").decode("ascii")
    sys.stdout.write(f"\r\033[K{safe}")
    sys.stdout.flush()


class InterviewProcessor:

    def __init__(self, company_name, limit=50):
        self.company_name = company_name
        self.worker = LLMWorker()
        self.limit: int= limit

    # ------------------------------------------------------------------
    # Load posts that have content but haven't been processed yet
    # ------------------------------------------------------------------
    def load_unprocessed(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                cd.topic_id,
                d.title,
                d.created_at AS posted_at,
                cd.content,
                cd.assets_urls_json,
                cd.other_urls_json
            FROM company_discussion_content cd
            JOIN company_discussions d
                ON cd.company_name = d.company_name AND cd.topic_id = d.topic_id
            WHERE cd.company_name = %(company_name)s
              AND (cd.company_name, cd.topic_id) NOT IN (
                  SELECT company_name, topic_id FROM interview_experiences
                  WHERE company_name = %(company_name)s
              )
            """,
            {"company_name": self.company_name},
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def load_all(self):
        """Load ALL posts (including already-processed) for reprocessing."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                cd.topic_id,
                d.title,
                d.created_at AS posted_at,
                cd.content,
                cd.assets_urls_json,
                cd.other_urls_json
            FROM company_discussion_content cd
            JOIN company_discussions d
                ON cd.company_name = d.company_name AND cd.topic_id = d.topic_id
            WHERE cd.company_name = ?
            """,
            (self.company_name,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def _save_failed(self, topic_id, error):
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO failed_processing (company_name, topic_id, error, failed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(company_name, topic_id) DO UPDATE SET
                error = excluded.error,
                failed_at = excluded.failed_at
            """,
            (
                self.company_name,
                topic_id,
                error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    def reprocess_all(self):
        # ------------------------------------------------------------------
        # Main processing loop
        # ------------------------------------------------------------------
        """Re-run ALL posts through LLM (overwrites existing results)."""
        posts = self.load_all()
        total = len(posts)
        print(
            f"[{self.company_name}] REPROCESSING {total} posts (overwriting existing)"
        )

        done, failed, consecutive_fails = 0, 0, 0
        for i, post in enumerate(posts, 1):
            title = (post["title"] or "")[:40]
            try:
                self._process_single(post, i, total, title)
                done += 1
                consecutive_fails = 0
                _status(f"[{i}/{total}] Done: {title}...")
                print()
                if done == self.limit:
                    break
            except Exception as e:
                failed += 1
                consecutive_fails += 1
                self._save_failed(post["topic_id"], str(e))
                _status(f"[{i}/{total}] FAILED: {title} — {e}")
                print()
                if consecutive_fails >= 3:
                    print(f"\n3 consecutive failures — stopping early.")
                    break

        print(f"\nReprocess finished: {done} done, {failed} failed, {total} total")

    def process_all_updates(self):
        posts = self.load_unprocessed()
        total = len(posts)
        print(f"[{self.company_name}] {total} posts to process")

        done, failed, consecutive_fails = 0, 0, 0
        for i, post in enumerate(posts, 1):
            title = (post["title"] or "")[:40]
            try:
                self._process_single(post, i, total, title)
                done += 1
                consecutive_fails = 0
                _status(f"[{i}/{total}] Done: {title}...")
                if done == self.limit:
                    break
                print()
            except Exception as e:
                failed += 1
                consecutive_fails += 1
                self._save_failed(post["topic_id"], str(e))
                _status(f"[{i}/{total}] FAILED: {title} — {e}")
                print()
                if consecutive_fails >= 3:
                    print(f"\n3 consecutive failures — stopping early.")
                    break

        print(f"\nFinished: {done} done, {failed} failed, {total} total")

    def retry_failed(self):
        posts = self._load_failed()
        total = len(posts)
        if not total:
            print(f"[{self.company_name}] No failed posts to retry")
            return

        print(f"[{self.company_name}] Retrying {total} failed posts")

        done, still_failed, consecutive_fails = 0, 0, 0
        for i, post in enumerate(posts, 1):
            title = (post["title"] or "")[:40]
            try:
                self._process_single(post, i, total, title)
                done += 1
                consecutive_fails = 0
                self._clear_failed(post["topic_id"])
                _status(f"[retry {i}/{total}] Done: {title}...")
                print()
            except Exception as e:
                still_failed += 1
                consecutive_fails += 1
                self._save_failed(post["topic_id"], str(e))
                _status(f"[retry {i}/{total}] FAILED: {title} — {e}")
                print()
                if consecutive_fails >= 3:
                    print(f"\n3 consecutive failures — stopping early.")
                    break

        print(f"\nRetry finished: {done} done, {still_failed} still failed")

    def _clear_failed(self, topic_id):
        conn = get_connection()
        conn.execute(
            "DELETE FROM failed_processing WHERE company_name = ? AND topic_id = ?",
            (self.company_name, topic_id),
        )
        conn.commit()
        conn.close()

    def _load_failed(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                cd.topic_id,
                d.title,
                d.summary,
                d.created_at AS posted_at,
                cd.content,
                cd.assets_urls_json,
                cd.other_urls_json
            FROM failed_processing fp
            JOIN company_discussion_content cd
                ON fp.company_name = cd.company_name AND fp.topic_id = cd.topic_id
            JOIN company_discussions d
                ON cd.company_name = d.company_name AND cd.topic_id = d.topic_id
            WHERE fp.company_name = ?
            """,
            (self.company_name,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def _process_single(self, post, idx=0, total=0, short_title=""):
        tag = f"[{idx}/{total}]"
        topic_id = post["topic_id"]
        title = post["title"] or ""
        content = post["content"] or ""
        posted_at = post["posted_at"]
        assets_urls = json.loads(post["assets_urls_json"] or "[]")
        other_urls = json.loads(post["other_urls_json"] or "[]")

        # --- Step 1: Text-only LLM pass ---
        _status(f"{tag} Sending text to LLM: {short_title}...")
        t0 = time.time()
        prompt_text = f"Title: {title}\n\nContent:\n{content}"
        llm_result = self.worker.run(prompt_text)
        print(llm_result)
        elapsed = time.time() - t0
        _status(f"{tag} Text LLM responded in {elapsed:.1f}s: {short_title}...")

        if isinstance(llm_result, list):
            llm_result = llm_result[0] if llm_result else None
        if not isinstance(llm_result, dict):
            _status(f"{tag} Skipped (LLM failed): {short_title}")
            print()
            return

        # --- Step 2: Vision pass (separate model, only if images exist) ---
        if assets_urls:
            _status(f"{tag} Downloading {len(assets_urls)} image(s): {short_title}...")
            image_parts = self._download_images(assets_urls)
            if image_parts:
                _status(
                    f"{tag} Sending {len(image_parts)} image(s) to vision model: {short_title}..."
                )
                t0 = time.time()
                vision_result = self.worker.run(
                    f"Post title: {title}\nAnalyze these {len(image_parts)} image(s) from this interview discussion post.",
                    image_parts=image_parts,
                    system_instruction=IMAGE_INSTRUCTION,
                )
                elapsed = time.time() - t0
                _status(f"{tag} Vision responded in {elapsed:.1f}s: {short_title}...")
                if isinstance(vision_result, list):
                    vision_result = vision_result[0] if vision_result else None
                elif isinstance(vision_result, dict):
                    llm_result = self._merge_results(llm_result, vision_result)

        # --- Step 3: Process URLs ---
        _status(f"{tag} Processing URLs: {short_title}...")
        url_data = self.process_urls(assets_urls, other_urls)

        # --- Step 4: Add leetcode problem links to round questions ---
        if url_data["leetcode_problem_links"]:
            rounds = llm_result.get("rounds", [])
            for r in rounds:
                if "questions" not in r:
                    r["questions"] = []
            # Append problem links as a note to the last round or first if none
            if rounds:
                last_round = rounds[-1]
                for link in url_data["leetcode_problem_links"]:
                    last_round["questions"].append(f"[Linked Problem] {link}")
            else:
                llm_result["rounds"] = [
                    {
                        "round_number": 1,
                        "round_type": "Unknown",
                        "questions": [
                            f"[Linked Problem] {link}"
                            for link in url_data["leetcode_problem_links"]
                        ],
                    }
                ]

        # --- Step 5: Fetch linked leetcode discussion posts and merge ---
        linked_post_ids = url_data["linked_post_ids"]
        if linked_post_ids:
            _status(
                f"{tag} Fetching {len(linked_post_ids)} linked post(s): {short_title}..."
            )
            llm_result = self.fetch_and_merge_linked_posts(linked_post_ids, llm_result)

        # --- Step 6: Save to DB ---
        _status(f"{tag} Saving to DB: {short_title}...")
        self.save_result(
            topic_id=topic_id,
            posted_at=posted_at,
            llm_result=llm_result,
            url_data=url_data,
        )

    def process_urls(self, assets_urls, other_urls):
        # ------------------------------------------------------------------
        # URL processing: classify and extract info from URLs
        # ------------------------------------------------------------------
        has_images = len(assets_urls) > 0
        leetcode_problem_links = []
        linked_post_ids = []
        valid_external_urls = []

        all_urls = assets_urls + other_urls

        for url in all_urls:
            # LeetCode problem link (e.g. leetcode.com/problems/two-sum/)
            problem_match = re.search(r"leetcode\.com/problems/([\w-]+)", url)
            if problem_match:
                slug = problem_match.group(1)
                full_link = f"https://leetcode.com/problems/{slug}/"
                if full_link not in leetcode_problem_links:
                    leetcode_problem_links.append(full_link)
                continue

            # LeetCode discussion link (e.g. leetcode.com/discuss/post/1234/...)
            discuss_match = re.search(
                r"leetcode\.com/discuss/(?:post|interview-experience|general-discussion)/(\d+)",
                url,
            )
            if discuss_match:
                linked_tid = int(discuss_match.group(1))
                if linked_tid not in linked_post_ids:
                    linked_post_ids.append(linked_tid)
                continue

            # Skip asset URLs (images) — already flagged via has_images
            if "assets.leetcode.com" in url:
                continue

            # Other external URLs — validate with HEAD request
            validated = self._validate_url(url)
            if validated and validated not in valid_external_urls:
                valid_external_urls.append(validated)

        return {
            "has_images": has_images,
            "leetcode_problem_links": leetcode_problem_links,
            "linked_post_ids": linked_post_ids,
            "valid_external_urls": valid_external_urls,
        }

    def _download_images(self, asset_urls, max_images=10):
        parts = []
        for url in asset_urls[:max_images]:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    continue
                parts.append((resp.content, content_type.split(";")[0]))
            except Exception:
                continue
        return parts

    def _validate_url(self, url):
        if not url.startswith("http"):
            url = "https://" + url
        try:
            resp = requests.head(url, timeout=5, allow_redirects=True)
            if resp.status_code < 400:
                return url
        except Exception:
            pass
        return None

    def fetch_and_merge_linked_posts(self, linked_topic_ids, parent_result):
        # ------------------------------------------------------------------
        # Fetch linked leetcode discussion posts and merge into parent result
        # ------------------------------------------------------------------
        for tid in linked_topic_ids:
            try:
                # Try DB first (any company — linked post may be from a different one)
                db_row = self._find_post_in_db(tid)

                if db_row:
                    content = db_row["content"] or ""
                    assets_urls = json.loads(db_row["assets_urls_json"] or "[]")
                    title = db_row.get("title", "")
                else:
                    # Fallback: fetch via GraphQL (text only, no images)
                    content = self._fetch_discussion_content(tid)
                    assets_urls = []
                    title = ""

                if not content:
                    continue

                # Text pass
                linked_result = self.worker.run(
                    f"Content from linked post (topic {tid}):\n{content}"
                )
                if isinstance(linked_result, list):
                    linked_result = linked_result[0] if linked_result else None
                if not isinstance(linked_result, dict):
                    continue

                # Vision pass for linked post images
                if assets_urls:
                    image_parts = self._download_images(assets_urls)
                    if image_parts:
                        vision_result = self.worker.run(
                            f"Post title: {title}\nAnalyze these {len(image_parts)} image(s) from a linked interview discussion post.",
                            image_parts=image_parts,
                            system_instruction=IMAGE_INSTRUCTION,
                        )
                        if isinstance(vision_result, list):
                            vision_result = vision_result[0] if vision_result else None
                        if isinstance(vision_result, dict):
                            linked_result = self._merge_results(
                                linked_result, vision_result
                            )

                parent_result = self._merge_results(parent_result, linked_result)
            except Exception as e:
                print(f"    Failed to fetch linked post {tid}: {e}")

        return parent_result

    def _find_post_in_db(self, topic_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cd.content, cd.assets_urls_json, cd.other_urls_json,
                   d.title
            FROM company_discussion_content cd
            JOIN company_discussions d
                ON cd.company_name = d.company_name AND cd.topic_id = d.topic_id
            WHERE cd.topic_id = ?
            LIMIT 1
            """,
            (topic_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def _fetch_discussion_content(self, topic_id):
        url = "https://leetcode.com/graphql/"
        headers = {
            "accept": "/",
            "content-type": "application/json",
            "origin": "https://leetcode.com/",
            "referer": "https://leetcode.com/discuss/",
            "user-agent": "Mozilla/5.0",
            "x-csrftoken": "YOUR_CSRF_TOKEN",
        }
        cookies = {
            "csrftoken": "YOUR_CSRF_TOKEN",
            "LEETCODE_SESSION": "YOUR_SESSION_COOKIE",
        }
        payload = {
            "operationName": "discussPostDetail",
            "variables": {"topicId": topic_id},
            "query": """
            query discussPostDetail($topicId: ID!) {
                ugcArticleDiscussionArticle(topicId: $topicId) {
                    content
                }
            }""",
        }
        response = requests.post(url, json=payload, headers=headers, cookies=cookies)
        data = response.json()
        return data["data"]["ugcArticleDiscussionArticle"]["content"]

    def _merge_results(self, parent, linked):
        # Merge rounds from linked post into parent
        parent_rounds = parent.get("rounds", [])
        linked_rounds = linked.get("rounds", [])

        if linked_rounds:
            max_round = max(
                (r.get("round_number", 0) for r in parent_rounds), default=0
            )
            for r in linked_rounds:
                r["round_number"] = max_round + r.get("round_number", 1)
                r["round_type"] = f"[From Linked Post] {r.get('round_type', 'Unknown')}"
                parent_rounds.append(r)
            parent["rounds"] = parent_rounds

        # Merge topics covered
        parent_topics = parent.get("topics_covered", []) or []
        linked_topics = linked.get("topics_covered", []) or []
        merged_topics = list(set(parent_topics + linked_topics))
        if merged_topics:
            parent["topics_covered"] = merged_topics

        # Fill empty parent fields from linked post
        fill_fields = [
            "role",
            "location",
            "experience_level",
            "result",
            "offered_salary",
            "old_salary",
            "interview_type",
            "difficulty",
            "tips",
            "process_duration",
            "referral_used",
            "team_or_org",
        ]
        for field in fill_fields:
            if not parent.get(field) and linked.get(field):
                parent[field] = linked[field]

        # Merge compensation
        parent_comp = parent.get("compensation", {}) or {}
        linked_comp = linked.get("compensation", {}) or {}
        for k, v in linked_comp.items():
            if v and not parent_comp.get(k):
                parent_comp[k] = v
        if parent_comp:
            parent["compensation"] = parent_comp

        return parent

    def save_result(self, topic_id, posted_at, llm_result, url_data):
        # ------------------------------------------------------------------
        # Save extracted data to interview_experiences table
        # ------------------------------------------------------------------
        conn = get_connection()
        cursor = conn.cursor()

        rounds = llm_result.get("rounds", [])
        compensation = llm_result.get("compensation", {}) or {}

        cursor.execute(
            """
            INSERT INTO interview_experiences (
                company_name, topic_id, is_interview, posted_at,
                interview_date, location, role, experience_level,
                rounds_json, result, company_name_extracted,
                offered_salary, old_salary, compensation_json,
                interview_type, difficulty, topics_json,
                programming_langs_json, tips, process_duration,
                referral_used, team_or_org, has_images,
                linked_post_ids_json, processed_urls_json,
                other_details, raw_llm_response, processed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_name, topic_id) DO UPDATE SET
                is_interview = excluded.is_interview,
                interview_date = excluded.interview_date,
                location = excluded.location,
                role = excluded.role,
                experience_level = excluded.experience_level,
                rounds_json = excluded.rounds_json,
                result = excluded.result,
                company_name_extracted = excluded.company_name_extracted,
                offered_salary = excluded.offered_salary,
                old_salary = excluded.old_salary,
                compensation_json = excluded.compensation_json,
                interview_type = excluded.interview_type,
                difficulty = excluded.difficulty,
                topics_json = excluded.topics_json,
                programming_langs_json = excluded.programming_langs_json,
                tips = excluded.tips,
                process_duration = excluded.process_duration,
                referral_used = excluded.referral_used,
                team_or_org = excluded.team_or_org,
                has_images = excluded.has_images,
                linked_post_ids_json = excluded.linked_post_ids_json,
                processed_urls_json = excluded.processed_urls_json,
                other_details = excluded.other_details,
                raw_llm_response = excluded.raw_llm_response,
                processed_at = excluded.processed_at
            """,
            (
                self.company_name,
                topic_id,
                1 if llm_result.get("is_interview") else 0,
                posted_at,
                llm_result.get("interview_date", ""),
                llm_result.get("location", ""),
                llm_result.get("role", ""),
                llm_result.get("experience_level", ""),
                json.dumps(rounds),
                llm_result.get("result", "unknown"),
                llm_result.get("company_name", ""),
                llm_result.get("offered_salary", ""),
                llm_result.get("old_salary", ""),
                json.dumps(compensation),
                llm_result.get("interview_type", ""),
                llm_result.get("difficulty", ""),
                json.dumps(llm_result.get("topics_covered", []) or []),
                json.dumps(llm_result.get("programming_languages", []) or []),
                llm_result.get("tips", ""),
                llm_result.get("process_duration", ""),
                llm_result.get("referral_used", ""),
                llm_result.get("team_or_org", ""),
                1 if url_data["has_images"] else 0,
                json.dumps(url_data["linked_post_ids"]),
                json.dumps(url_data["valid_external_urls"]),
                llm_result.get("other_details", ""),
                json.dumps(llm_result),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        conn.commit()
        conn.close()


if __name__ == "__main__":

    company = sys.argv[1] if len(sys.argv) > 1 else "amazon"
    processor = InterviewProcessor(company)

    if "--retry" in sys.argv:
        processor.retry_failed()
    elif "--reprocess" in sys.argv:
        processor.reprocess_all()
    else:
        processor.process_all_updates()
