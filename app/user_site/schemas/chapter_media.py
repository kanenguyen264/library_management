from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

class ChapterMediaBase(BaseModel):
    chapter_id: int
    media_type: str = Field(..., description="Loại media: 'image', 'audio', 'video'")
    url: str
    position: int = Field(..., description="Vị trí trong chương")
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None  # Thời lượng (giây) cho audio/video
    alt_text: Optional[str] = None

class ChapterMediaCreate(ChapterMediaBase):
    pass

class ChapterMediaUpdate(BaseModel):
    media_type: Optional[str] = Field(None, description="Loại media: 'image', 'audio', 'video'")
    url: Optional[str] = None
    position: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    alt_text: Optional[str] = None

class ChapterMediaResponse(ChapterMediaBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ChapterMediaListResponse(BaseModel):
    items: List[ChapterMediaResponse]
    total: int
    
    class Config:
        from_attributes = True
