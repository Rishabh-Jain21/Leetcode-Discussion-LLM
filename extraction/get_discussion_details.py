import requests
import json
from time import sleep
import re
import os

from helpers.utils import merge_topics, merge_topics_items


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

    def load_company_json(self, company_name: str):

        with open(f"data/{company_name}/{company_name}.json", "r") as f:
            comp_data = json.load(f)

        return comp_data

    def load_company_updates_json(self, company_name: str):

        with open(f"data/{company_name}/updates.json", "r") as f:
            comp_data = json.load(f)

        return comp_data

    def get_all_discussions(self):

        c_data = self.load_company_json(self.company_name)

        for post in c_data[:10]:
            topic_id = post["topic_id"]
            contains_url = False
            updated_at = post["updated_at"]
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

    def get_all_discussions_updates(self):

        c_data = self.load_company_updates_json(self.company_name)

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
        os.makedirs(f"data/{self.company_name}", exist_ok=True)
        c_data = self.load_company_json(self.company_name)
        merged_data, _ = merge_topics_items(c_data, self.all_content_json)
        with open(
            f"data/{self.company_name}/{self.company_name}_content.json", "w"
        ) as f:
            f.write(json.dumps(merged_data, indent=4))

        os.remove(f"data/{self.company_name}/updates.json")

    def extract_and_group_urls(self, text, normalize=True):
        assets_urls = []
        other_urls = []

        # 1️⃣ Extract URLs inside Markdown parentheses
        md_urls = re.findall(r"\((https?://[^\s)]+)\)", text)

        # 2️⃣ Extract standalone full or partial URLs (ignore ones already in md_urls)
        all_urls = re.findall(
            r"(?:https?://)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s)\]]*", text
        )

        # Combine and deduplicate
        urls = list(set(md_urls + all_urls))

        for url in urls:
            if normalize and not url.startswith("http"):
                url = "https://" + url

            if "assets.leetcode.com" in url:
                assets_urls.append(url)
            else:
                other_urls.append(url)

        return {"assets_urls": assets_urls, "other_urls": other_urls}
