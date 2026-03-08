from datetime import datetime


def merge_topics(list1, list2):
    merged = {item["node"]["topic"]["id"]: item for item in list1}
    changed_nodes = []

    for item in list2:
        node = item["node"]
        topic_id = node["topic"]["id"]
        updated_at = datetime.fromisoformat(node["updatedAt"])

        if topic_id not in merged:
            merged[topic_id] = item
            changed_nodes.append(node)

        else:
            existing_updated = datetime.fromisoformat(
                merged[topic_id]["node"]["updatedAt"]
            )

            if updated_at > existing_updated:
                merged[topic_id] = item
                changed_nodes.append(node)

    return list(merged.values()), changed_nodes


def merge_topics_items(list1, list2):
    merged = {item["topic_id"]: item for item in list1}
    changed_nodes = []

    for item in list2:
        print(item)
        topic_id = item["topic_id"]
        updated_at = datetime.fromisoformat(item["updated_at"])

        if topic_id not in merged:
            merged[topic_id] = item
            changed_nodes.append(item)

        else:
            existing_updated = datetime.fromisoformat(merged[topic_id]["updated_at"])

            if updated_at > existing_updated:
                merged[topic_id] = item
                changed_nodes.append(item)

    return list(merged.values()), changed_nodes
