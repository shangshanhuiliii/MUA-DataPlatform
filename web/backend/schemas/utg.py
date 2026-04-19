from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class EventUpdate(BaseModel):
    """事件更新模型 - 支持状态改变"""
    old_event_str: str = Field(..., description="要更新的原事件字符串")
    event_type: str = Field(..., description="新事件类型")
    event_str: str = Field(..., description="新事件字符串")
    # 新增字段: 支持修改源和目标状态
    new_from_state: Optional[str] = Field(None, description="新源状态ID(可选,不提供则保持不变)")
    new_to_state: Optional[str] = Field(None, description="新目标状态ID(可选,不提供则保持不变)")

class EventCreate(BaseModel):
    """事件创建模型"""
    from_state: str = Field(..., alias='from', description="源状态ID")
    to: str = Field(..., description="目标状态ID")
    event_type: str = Field(..., description="事件类型")
    event_str: str = Field(..., description="事件字符串")
    
    class Config:
        allow_population_by_field_name = True

class EventDelete(BaseModel):
    """事件删除请求模型"""
    event_str: str = Field(..., description="要删除的事件字符串")

class NodeDelete(BaseModel):
    """节点删除响应模型"""
    deleted_node_id: str = Field(..., description="被删除的节点ID")

class UTGData(BaseModel):
    """UTG数据模型"""
    nodes: List[Dict[str, Any]] = Field(default=[], description="节点列表")
    edges: List[Dict[str, Any]] = Field(default=[], description="边列表")
    
class SearchResult(BaseModel):
    """搜索结果模型"""
    nodes: List[Dict[str, Any]] = Field(default=[], description="匹配的节点")
    edges: List[Dict[str, Any]] = Field(default=[], description="匹配的边")
    total_matches: int = Field(0, description="总匹配数量")

class BranchStatesResponse(BaseModel):
    """分支状态响应模型"""
    node_id: str = Field(..., description="查询的节点ID")
    branch_states: List[str] = Field(default=[], description="分支中的所有状态ID列表")
    count: int = Field(0, description="分支中的状态数量")

class BatchDeleteRequest(BaseModel):
    """批量删除请求模型"""
    node_ids: List[str] = Field(..., description="要删除的节点ID列表")

class BatchDeleteResponse(BaseModel):
    """批量删除响应模型"""
    deleted_nodes: List[str] = Field(default=[], description="成功删除的节点ID列表")
    failed_nodes: List[Dict[str, str]] = Field(default=[], description="删除失败的节点及原因")

class SetLabelsRequest(BaseModel):
    """设置节点自定义标签请求模型"""
    labels: List[str] = Field(..., description="自定义标签列表")
    label_meta: Optional[Dict[str, Any]] = Field(
        default=None,
        description="标签元数据（例如 NEED_FEEDBACK 的 assistant_question/user_feedback 或 FINISH 的 score/assistant_final_message）"
    )

class SetStateRequest(BaseModel):
    """设置 UTG 状态请求模型 - 用于设置 first_state 或 last_state"""
    node_id: str = Field(..., description="节点ID")

class BatchRestoreRequest(BaseModel):
    """批量恢复请求模型"""
    state_list: List[str] = Field(..., description="要恢复的节点ID列表")

class BatchRestoreResponse(BaseModel):
    """批量恢复响应模型"""
    restored: List[str] = Field(default=[], description="成功恢复的节点ID列表")
    failed: List[Dict[str, str]] = Field(default=[], description="恢复失败的节点及原因")
    message: str = Field("Batch restore completed", description="提示信息")
