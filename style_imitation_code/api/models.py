from pydantic import BaseModel

class ChatRequest(BaseModel):
    api_key: str
    model: str
    messages: list
    system_prompt: str
    temperature: float
    top_p: float

class ProjectCreate(BaseModel):
    name: str
    branch: str = "原创"  # 选项：原创 | 同人 | 默认
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