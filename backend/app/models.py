from typing import Optional, Any, Literal
import uuid
from pydantic import BaseModel, Field

OutputType = Literal["kpi", "table", "line_chart", "bar_chart", "pie_chart", "list", "text"]

class Chart(BaseModel):
    type: Literal["bar", "line", "pie", "none"] = "none"
    title: Optional[str] = None
    xAxis: Optional[str] = Field(default=None, serialization_alias="xAxis")
    yAxis: Optional[str] = Field(default=None, serialization_alias="yAxis")
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    data: list[dict[str, Any]] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.xAxis and not self.x_key:
            self.x_key = self.xAxis
        elif self.x_key and not self.xAxis:
            self.xAxis = self.x_key
        if self.yAxis and not self.y_key:
            self.y_key = self.yAxis
        elif self.y_key and not self.yAxis:
            self.yAxis = self.y_key

class Meta(BaseModel):
    requestId: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:10]}")
    rowCount: int = 0
    executionMs: int = 0
    llmMs: Optional[int] = None
    sqlMs: Optional[int] = None

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User inventory question")
    conversation_id: Optional[str] = Field(default="default", description="Conversation session ID")
    is_admin: Optional[bool] = Field(default=False, description="Whether caller is authorized for admin debug view")

class ChatResponse(BaseModel):
    answer: str
    data: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    chart: Chart = Field(default_factory=Chart)
    meta: Meta = Field(default_factory=Meta)
    sql: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    intent: Optional[str] = None
    output_type: OutputType = "text"
    metric: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    time_range: Optional[str] = None

class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: Optional[str] = None
    rating: Literal["up", "down"]
    comment: Optional[str] = None
    sql: Optional[str] = None

class FeedbackResponse(BaseModel):
    status: str = "recorded"
    message: str = "Thank you for your feedback!"
