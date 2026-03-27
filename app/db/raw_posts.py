import json
from datetime import datetime

from app.setup_database.setup_db import get_connection


def merge_topics_to_db(new_api_data):
    """
    Takes raw API edges, upserts into raw_short_discussions,
    and populates updated_raw_short_discussions with changed/new entries.
    Returns count of changed nodes.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Clear previous run's updated nodes
    cursor.execute("DELETE FROM updated_raw_short_discussions")

    changed_count = 0

    for item in new_api_data:
        node = item["node"]
        topic_id = node["topic"]["id"]
        updated_at = node["updatedAt"]
        tags_json = json.dumps(node.get("tags", []))

        # Check if this topic already exists
        cursor.execute(
            "SELECT updated_at FROM raw_short_discussions WHERE topic_id = ?",
            (topic_id,),
        )
        row = cursor.fetchone()

        is_new = row is None
        is_newer = False
        if not is_new:
            existing_updated = datetime.fromisoformat(row["updated_at"])
            incoming_updated = datetime.fromisoformat(updated_at)
            is_newer = incoming_updated > existing_updated

        if is_new or is_newer:
            # Upsert into raw_short_discussions
            cursor.execute(
                """
                INSERT INTO raw_short_discussions
                    (topic_id, uuid, title, slug, summary, created_at, updated_at, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    uuid = excluded.uuid,
                    title = excluded.title,
                    slug = excluded.slug,
                    summary = excluded.summary,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    tags_json = excluded.tags_json
                """,
                (
                    topic_id,
                    node.get("uuid", ""),
                    node["title"],
                    node["slug"],
                    node.get("summary", ""),
                    node["createdAt"],
                    updated_at,
                    tags_json,
                ),
            )

            # Record as changed node
            cursor.execute(
                """
                INSERT INTO updated_raw_short_discussions
                    (topic_id, title, slug, summary, created_at, updated_at, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    title = excluded.title,
                    slug = excluded.slug,
                    summary = excluded.summary,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    tags_json = excluded.tags_json
                """,
                (
                    topic_id,
                    node["title"],
                    node["slug"],
                    node.get("summary", ""),
                    node["createdAt"],
                    updated_at,
                    tags_json,
                ),
            )
            changed_count += 1

    conn.commit()
    conn.close()
    return changed_count


def merge_company_discussions_to_db(company_name, new_items):
    """
    Upserts into company_discussions and tracks changed items
    in company_pending_updates.
    Returns count of changed nodes.
    """
    conn = get_connection()
    cursor = conn.cursor()

    changed_count = 0

    for item in new_items:
        topic_id = item["topic_id"]
        updated_at = item["updated_at"]

        # Check existing
        cursor.execute(
            "SELECT updated_at FROM company_discussions WHERE company_name = ? AND topic_id = ?",
            (company_name, topic_id),
        )
        row = cursor.fetchone()

        is_new = row is None
        is_newer = False
        if not is_new:
            existing_updated = datetime.fromisoformat(row["updated_at"])
            incoming_updated = datetime.fromisoformat(updated_at)
            is_newer = incoming_updated > existing_updated

        if is_new or is_newer:
            tags_json = json.dumps(item.get("tags", []))

            # Upsert into company_discussions
            cursor.execute(
                """
                INSERT INTO company_discussions
                    (company_name, topic_id, title, summary, created_at, updated_at, tags_json, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_name, topic_id) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    tags_json = excluded.tags_json,
                    url = excluded.url
                """,
                (
                    company_name,
                    topic_id,
                    item["title"],
                    item.get("summary", ""),
                    item["created_at"],
                    updated_at,
                    tags_json,
                    item["url"],
                ),
            )

            # Track as pending update
            cursor.execute(
                """
                INSERT INTO company_pending_updates (company_name, topic_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(company_name, topic_id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (company_name, topic_id, updated_at),
            )
            changed_count += 1

    conn.commit()
    conn.close()
    return changed_count
