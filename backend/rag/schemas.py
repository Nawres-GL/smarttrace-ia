from pydantic import BaseModel, Field
from typing import Literal


class QuestionIn(BaseModel):
    question: str = Field(min_length=8, max_length=800)


class ExploreIn(BaseModel):
    dataset: str = Field(min_length=3, max_length=60)
    metric: str = Field(min_length=2, max_length=60)
    group_by: str | None = Field(default=None, max_length=60)
    filters: dict[str, str] = Field(default_factory=dict)
    order: Literal['asc', 'desc'] = 'desc'
    threshold: float | None = None
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=5000)
