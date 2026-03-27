from sqlite3 import Connection

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from app.repo.get_full_content_posts import Discussion
from app.repo.llm_discussion_processor import InterviewProcessor
from app.setup_database.setup_db import get_connection
from typing import Annotated
from app.db.raw_posts import merge_topics_to_db
from app.db.db_helpers import query_builder
from app.repo.analyze_post import analyze_post
from app.repo.get_all_new_short_posts import get_links
from app.data_processing.transform_data import TransformData
from app.schemas.search_schema import searchDefination

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/get-new-posts")
def get_new_posts():

    all_data = []

    for high in range(1000, 4001, 1000):
        skip = high - 1000

        data = get_links(skip, high)
        all_data.extend(data)

    changed_count = merge_topics_to_db(all_data)

    return_json = {"new_posts_count": changed_count, "total_fetched": len(all_data)}
    return return_json


@router.get("/transform-posts")
def transform_posts(
    column_name: Annotated[str | None, Query()] = None,
    column_value: Annotated[str | None, Query()] = None,
    updated_only: Annotated[bool | None, Query()] = None,
):
    td = TransformData(keywords=[column_value], company_name=column_value)

    if updated_only:
        td.transform_updates()
    else:
        td.transform()

    td.company_filter_data()
    td.save_company_data()

    return {"status": len(td.company_filtered_data)}


@router.post("/filter-processed-posts")
def filter_processed_posts(
    data_json: searchDefination, conn: Annotated[Connection, Depends(get_connection)]
):
    """
    If update only
        Sql query to get using the json filters from company pending updates
    else
        same thing from company discussions
    """
    table_name = "company_discussion_content"

    query, values = query_builder(search=data_json, table_name=table_name)

    cursor = conn.cursor()

    cursor.execute(query, values)

    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


@router.get("/get-full-posts-data")
def get_full_posts_data(
    column_name: Annotated[str | None, Query()] = None,
    column_value: Annotated[str | None, Query()] = None,
    updated_only: Annotated[bool | None, Query()] = None,
):

    ds = Discussion(column_value)

    if updated_only:

        ds.get_all_discussions_updates()
    else:
        ds.get_all_discussions()

    ds.save_data()

    return {"count": len(ds.all_content_json)}


@router.get("/llm-parsing")
def llm_parsing(
    updated_only: Annotated[bool | None, Query()] = None,
    column_name: Annotated[str | None, Query()] = None,
    column_value: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(gt=0)] = 50,
):
    interview = InterviewProcessor(column_value, limit=limit)

    if updated_only:
        interview.process_all_updates()
    else:
        interview.reprocess_all()


@router.post("/process-link")
def process_link(data_body=Body()):
    return analyze_post(data_body.get("link", None))


@router.get("/filter-processed_posts")
def filtered_processed_posts(
    data_json: searchDefination, conn: Annotated[Connection, Depends(get_connection)]
):
    table_name = "interview_experiences"

    query, values = query_builder(search=data_json, table_name=table_name)

    cursor = conn.cursor()

    cursor.execute(query, values)

    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result
