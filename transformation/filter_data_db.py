import json
from datetime import datetime

from setup_database.setup_db import get_connection
from helpers.utils_db import merge_company_discussions_to_db


class FilterDB:

    def __init__(self, *, keywords, company_name):
        self.filter_data: list = []
        self.company_filtered_data: list = []
        self.company_name = company_name
        self.keywords = keywords

    def load_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM raw_discussions")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def load_updates(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM updated_raw_nodes")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _transform_row(self, row):
        """Shared transform logic for both full data and updates."""
        title = row["title"].lower()
        summary = (row["summary"] or "").lower()

        created_at = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%S.%f%z")
        updated_at = datetime.strptime(row["updated_at"], "%Y-%m-%dT%H:%M:%S.%f%z")

        tags = json.loads(row["tags_json"])
        flatten_tags = list(
            {v.lower() for d in tags for v in d.values() if isinstance(v, str)}
        )
        topic_id = row["topic_id"]
        slug = row["slug"]

        url = f"https://www.leetcode.com/discuss/post/{topic_id}/{slug}"

        return {
            "title": title,
            "summary": summary,
            "created_at": str(created_at),
            "updated_at": str(updated_at),
            "tags": flatten_tags,
            "url": url,
            "topic_id": topic_id,
        }

    def transform(self):
        data = self.load_data()
        for row in data:
            self.filter_data.append(self._transform_row(row))

    def transform_updates(self):
        data = self.load_updates()
        for row in data:
            self.filter_data.append(self._transform_row(row))

    def company_filter_data(self):

        for item in self.filter_data:

            for key in self.keywords:
                new_key = key.lower()
                if (
                    new_key in item["title"]
                    or new_key in item["summary"]
                    or new_key in item["tags"]
                ):
                    self.company_filtered_data.append(item)
                    break

    def save_company_data(self):
        changed = merge_company_discussions_to_db(
            self.company_name, self.company_filtered_data
        )
        print(f"{self.company_name}: {len(self.company_filtered_data)} filtered, {changed} new/updated")
