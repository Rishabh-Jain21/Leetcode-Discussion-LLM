import requests
import json
import os
from datetime import datetime

from helpers.utils import merge_topics


def get_links(skip: int = 0, first: int = 1000, tag_slugs: list[str] = ["interview"]):

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
        "operationName": "discussPostItems",
        "variables": {
            "orderBy": "HOT",
            "keywords": [""],
            "tagSlugs": tag_slugs,
            "skip": skip,
            "first": first,
        },
        "query": """
        query discussPostItems($orderBy: ArticleOrderByEnum, $keywords: [String]!, $tagSlugs: [String!], $skip: Int, $first: Int) {
  ugcArticleDiscussionArticles(
    orderBy: $orderBy
    keywords: $keywords
    tagSlugs: $tagSlugs
    skip: $skip
    first: $first
  ) {
    totalNum
    pageInfo {
      hasNextPage
    }
    edges {
      node {
        uuid
        title
        slug
        summary
        author {
          realName
          userAvatar
          userSlug
          userName
          nameColor
          certificationLevel
          activeBadge {
            icon
            displayName
          }
        }
        isOwner
        isAnonymous
        isSerialized
        scoreInfo {
          scoreCoefficient
        }
        articleType
        thumbnail
        summary
        createdAt
        updatedAt
        status
        isLeetcode
        canSee
        canEdit
        isMyFavorite
        myReactionType
        topicId
        hitCount
        reactions {
          count
          reactionType
        }
        tags {
          name
          slug
          tagType
        }
        topic {
          id
          topLevelCommentCount
                }
            }
            }
        }
        }
        """,
    }

    response = requests.post(url, json=payload, headers=headers, cookies=cookies)

    # print(response.status_code)
    json_response = response.json()
    # print(json_response)
    return json_response["data"]["ugcArticleDiscussionArticles"]["edges"]


all_data = []

for high in range(1000, 4001, 1000):
    skip = high - 1000

    data = get_links(skip, high)
    print(len(data))

    all_data.extend(data)

merged_list = all_data
updated_topic_ids_list = []

if os.path.exists("data.json"):
    with open("data.json", "r") as reader_obj:
        read_data = json.load(reader_obj)

    merged_list, updated_topic_ids_list = merge_topics(read_data, all_data)


with open("data_merged.json", "w") as f:
    f.write(json.dumps(merged_list, indent=4))

with open("updated.json", "w") as f:
    f.write(json.dumps(updated_topic_ids_list, indent=4))
print(len(updated_topic_ids_list))
