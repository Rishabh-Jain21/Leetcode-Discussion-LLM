import json
from datetime import datetime
import os

from helpers.utils import merge_topics, merge_topics_items


class Filter:

    def __init__(self, *, keywords, company_name):
        self.filter_data: list = []
        self.company_filtered_data: list = []
        self.company_name = company_name
        self.keywords = keywords
        self.old_data = []

    def load_data(
        self,
    ):
        with open("data.json") as f:
            return json.load(f)

    def load_updates(self):
        with open("updated.json") as f:
            return json.load(f)

    def transform(
        self,
    ):

        data = self.load_data()
        for item in data:
            json_data = dict()

            node = item["node"]
            title = node["title"].lower()
            summary = node["summary"].lower()

            created_at = datetime.strptime(node["createdAt"], "%Y-%m-%dT%H:%M:%S.%f%z")
            updated_at = datetime.strptime(node["updatedAt"], "%Y-%m-%dT%H:%M:%S.%f%z")

            tags = node["tags"]
            flatten_tags = list(
                {v.lower() for d in tags for v in d.values() if isinstance(v, str)}
            )
            topic_id = node["topicId"]
            slug = node["slug"]

            url = f"https://www.leetcode.com/discuss/post/{topic_id}/{slug}"

            json_data = {
                "title": title,
                "summary": summary,
                "created_at": str(created_at),
                "updated_at": str(updated_at),
                "tags": flatten_tags,
                "url": url,
                "topic_id": topic_id,
            }

            self.filter_data.append(json_data)

    def transform_updates(
        self,
    ):

        data = self.load_updates()
        for node in data:
            json_data = dict()
            topic_id = node["topicId"]
            title = node["title"].lower()
            summary = node["summary"].lower()

            created_at = datetime.strptime(node["createdAt"], "%Y-%m-%dT%H:%M:%S.%f%z")
            updated_at = datetime.strptime(node["updatedAt"], "%Y-%m-%dT%H:%M:%S.%f%z")

            tags = node["tags"]
            flatten_tags = list(
                {v.lower() for d in tags for v in d.values() if isinstance(v, str)}
            )

            slug = node["slug"]

            url = f"https://www.leetcode.com/discuss/post/{topic_id}/{slug}"

            json_data = {
                "title": title,
                "summary": summary,
                "created_at": str(created_at),
                "updated_at": str(updated_at),
                "tags": flatten_tags,
                "url": url,
                "topic_id": topic_id,
            }

            self.filter_data.append(json_data)

    def save_data(
        self,
    ):
        with open("data2.json", "w") as f:
            f.write(json.dumps(self.filter_data, indent=4))

    def get_company_old_data(
        self,
    ):
        if os.path.exists("data/{self.company_name}/{self.company_name}.json"):
            with open(f"data/{self.company_name}/{self.company_name}.json", "r") as f:
                self.old_data = json.load(f)

    def company_filter_data(self):

        for item in self.filter_data:

            for key in self.keywords:
                new_key = key.lower()
                if (
                    new_key.lower() in item["title"]
                    or new_key.lower() in item["summary"]
                    or new_key.lower() in item["tags"]
                ):
                    self.company_filtered_data.append(item)
                    break

    def save_company_data(self):

        os.makedirs(f"data/{self.company_name}", exist_ok=True)

        self.get_company_old_data()
        merged_data, updated_nodes = merge_topics_items(
            self.old_data, self.company_filtered_data
        )
        updates_json = []
        for node in updated_nodes:
            json_data = dict()
            topic_id = node["topic_id"]
            updated_at = node["updated_at"]
            json_data = {"topic_id": topic_id, "updated_at": updated_at}
            updates_json.append(json_data)

        with open(f"data/{self.company_name}/{self.company_name}.json", "w") as f:
            f.write(json.dumps(merged_data, indent=4))
        with open(f"data/{self.company_name}/updates.json", "w") as f:
            f.write(json.dumps(updates_json, indent=4))
        print(len(self.company_filtered_data))
