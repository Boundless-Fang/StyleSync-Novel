from typing import List, Literal

from pydantic import BaseModel, Field, confloat, validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=20000)

    @validator("content")
    def validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message content cannot be empty")
        return cleaned


class ChatRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    model: str = Field(default="deepseek-chat", min_length=1, max_length=100)
    messages: List[ChatMessage] = Field(..., min_items=1)
    system_prompt: str = Field(default="", max_length=20000)
    temperature: confloat(ge=0.0, le=2.0) = 0.5
    top_p: confloat(gt=0.0, le=1.0) = 1.0

    @validator("api_key", "model", pre=True)
    def validate_required_text(cls, value: str) -> str:
        if value is None:
            raise ValueError("field is required")
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("field cannot be empty")
        return cleaned

    @validator("system_prompt", pre=True, always=True)
    def validate_system_prompt(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()


class ProjectCreate(BaseModel):
    name: str
    branch: str = "原创"
    reference_style: str = ""


class ChapterUpdate(BaseModel):
    content: str


class AppendContent(BaseModel):
    content: str


class SettingUpdate(BaseModel):
    content: str


class SettingCompletionRequest(BaseModel):
    target_file: str
    mode: str
    project_name: str = ""
    form_data: dict
    model: str = "deepseek-chat"


class ChapterOutlineRequest(BaseModel):
    project_name: str
    chapter_name: str
    chapter_brief: str
    model: str = "deepseek-chat"


class NovelGenerationRequest(BaseModel):
    project_name: str
    chapter_name: str
    model: str = "deepseek-chat"
