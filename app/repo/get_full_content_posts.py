import time

import requests
import json
import re
from datetime import datetime

from app.setup_database.setup_db import get_connection


class Discussion:
    def __init__(self, company_name):
        self.company_name = company_name
        self.all_content_json: list = []

    def get_discussion_detail(self, topic_id):

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
		uuid
		title
		content
		createdAt
		author {
		userName
		}
		}
		}""",
        }
        response = requests.post(url, json=payload, headers=headers, cookies=cookies)

        json_response = response.json()

        return json_response["data"]["ugcArticleDiscussionArticle"]["content"]

    def load_company_discussions(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT topic_id, updated_at FROM company_discussions WHERE company_name = ?",
            (self.company_name,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def load_company_pending_updates(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT topic_id, updated_at FROM company_pending_updates WHERE company_name = ?",
            (self.company_name,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_all_discussions(self):

        c_data = self.load_company_discussions()

        for post in c_data:
            topic_id = post["topic_id"]
            contains_url = False
            updated_at = post["updated_at"]
            try:
                content = self.get_discussion_detail(topic_id)
                time.sleep(2)
                url_groups = self.extract_and_group_urls(content)

                if (
                    len(url_groups["assets_urls"]) > 0
                    or len(url_groups["other_urls"]) > 0
                ):
                    contains_url = True

                content_json = {
                    "topic_id": topic_id,
                    "content": content,
                    "contains_url": contains_url,
                    "assets_urls": url_groups["assets_urls"],
                    "other_urls": url_groups["other_urls"],
                    "updated_at": updated_at,
                }
                self.all_content_json.append(content_json)
                print(f"success for {topic_id}")
            except:
                print("Failed for topic id", topic_id)

    def get_all_discussions_updates(self):

        c_data = self.load_company_pending_updates()

        for post in c_data:
            topic_id = post["topic_id"]
            updated_at = post["updated_at"]
            contains_url = False
            try:
                content = self.get_discussion_detail(topic_id)
                url_groups = self.extract_and_group_urls(content)

                if (
                    len(url_groups["assets_urls"]) > 0
                    or len(url_groups["other_urls"]) > 0
                ):
                    contains_url = True

                content_json = {
                    "topic_id": topic_id,
                    "content": content,
                    "contains_url": contains_url,
                    "assets_urls": url_groups["assets_urls"],
                    "other_urls": url_groups["other_urls"],
                    "updated_at": updated_at,
                }
                self.all_content_json.append(content_json)
                print(f"success for {topic_id}")
            except:
                print("Failed for topic id", topic_id)

    def save_data(self):
        conn = get_connection()
        cursor = conn.cursor()

        for item in self.all_content_json:
            topic_id = item["topic_id"]
            updated_at = item["updated_at"]

            # Check if content already exists and compare updated_at
            cursor.execute(
                "SELECT updated_at FROM company_discussion_content WHERE company_name = ? AND topic_id = ?",
                (self.company_name, topic_id),
            )
            row = cursor.fetchone()

            is_new = row is None
            is_newer = False
            if not is_new:
                existing_updated = datetime.fromisoformat(row["updated_at"])
                incoming_updated = datetime.fromisoformat(updated_at)
                is_newer = incoming_updated > existing_updated

            if is_new or is_newer:
                cursor.execute(
                    """
                    INSERT INTO company_discussion_content
                        (company_name, topic_id, content, contains_url,
                         assets_urls_json, other_urls_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(company_name, topic_id) DO UPDATE SET
                        content = excluded.content,
                        contains_url = excluded.contains_url,
                        assets_urls_json = excluded.assets_urls_json,
                        other_urls_json = excluded.other_urls_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self.company_name,
                        topic_id,
                        item["content"],
                        1 if item["contains_url"] else 0,
                        json.dumps(item["assets_urls"]),
                        json.dumps(item["other_urls"]),
                        updated_at,
                    ),
                )

        # Clear pending updates for this company (mirrors os.remove("updates.json"))
        cursor.execute(
            "DELETE FROM company_pending_updates WHERE company_name = ?",
            (self.company_name,),
        )

        conn.commit()
        conn.close()

    def extract_and_group_urls(self, text, normalize=True):
        assets_urls = []
        other_urls = []

        md_urls = re.findall(r"\((https?://[^\s)]+)\)", text)

        all_urls = re.findall(
            r"(?:https?://)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s)\]]*", text
        )

        urls = list(set(md_urls + all_urls))

        for url in urls:
            if normalize and not url.startswith("http"):
                url = "https://" + url

            if "assets.leetcode.com" in url:
                assets_urls.append(url)
            else:
                other_urls.append(url)

        return {"assets_urls": assets_urls, "other_urls": other_urls}
