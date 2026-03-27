from pydantic import BaseModel, ConfigDict


class searchDefination(BaseModel):
    filter: list[dict[str, str]] | None = None
    sort_by: list[dict[str, str]] | None = None
    search_param: str | None = None
    updated_only: bool = True

    model_config = ConfigDict(from_attributes=True)

