from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator


class SearchLogBase(BaseModel):
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    query: str
    filters: Optional[Dict[str, Any]] = None
    results_count: Optional[int] = 0
    category: Optional[str] = None
    source: Optional[str] = None
    search_duration: Optional[float] = None
    clicked_results: Optional[List[str]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SearchLogCreate(SearchLogBase):
    timestamp: Optional[datetime] = None


class SearchLog(SearchLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class SearchLogRead(SearchLog):
    user_username: Optional[str] = None
    user_email: Optional[str] = None
    formatted_timestamp: Optional[str] = None
    display_filters: Optional[str] = None

    class Config:
        from_attributes = True


class SearchLogList(BaseModel):
    items: List[SearchLog]
    total: int
    page: int
    size: int
    pages: int


class SearchLogFilter(BaseModel):
    user_id: Optional[int] = None
    query: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_results: Optional[int] = None
    max_results: Optional[int] = None
