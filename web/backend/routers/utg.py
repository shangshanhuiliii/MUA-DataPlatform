from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Depends, Response

from ..schemas.utg import (
    EventCreate, EventUpdate, EventDelete, BatchDeleteRequest,
    BranchStatesResponse, BatchDeleteResponse, SetLabelsRequest, SetStateRequest,
    BatchRestoreRequest, BatchRestoreResponse
)
from ..services.utg_service_v2 import UTGServiceV2
from ..session_config import current_recording_from_header, current_recording_from_header_for_write

router = APIRouter(prefix="/api", tags=["UTG"])


@router.get("/utg")
async def get_utg(
    recording_name: str = Depends(current_recording_from_header)
) -> Dict[str, Any]:
    """获取当前UTG数据

    从用户会话中读取当前数据集
    """
    try:
        return await UTGServiceV2.get_utg(recording_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get UTG data: {str(e)}")

@router.put("/events/{edge_id}")
async def update_event(
    edge_id: str,
    event_update: EventUpdate,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """更新事件 - 支持状态改变

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.update_event(
            recording_name,
            edge_id,
            event_update.old_event_str,
            event_update.event_type,
            event_update.event_str,
            event_update.new_from_state,
            event_update.new_to_state
        )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.delete("/edges/{edge_id}/events")
async def delete_event(
    edge_id: str,
    event_delete: EventDelete,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """删除边上的特定事件

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.delete_event(
            recording_name,
            edge_id,
            event_delete.event_str
        )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: str,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """删除节点及其相关边

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.delete_node(recording_name, node_id)

        return {
            "message": "Node and related edges deleted successfully",
            "node_id": result.deleted_node_id
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/events")
async def create_event(
    event_create: EventCreate,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """创建新事件

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.create_event(
            recording_name,
            event_create.from_state,
            event_create.to,
            event_create.event_type,
            event_create.event_str
        )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.get("/nodes/{node_id}/branch", response_model=BranchStatesResponse)
async def get_branch_states(
    node_id: str,
    recording_name: str = Depends(current_recording_from_header)
) -> Dict[str, Any]:
    """获取从指定节点开始的分支中的所有状态

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.get_branch_states(recording_name, node_id)

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/nodes/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_nodes(
    delete_request: BatchDeleteRequest,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """批量删除节点及其相关边

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.batch_delete_nodes(
            recording_name,
            delete_request.node_ids
        )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.put("/utg/first-state")
async def set_first_state(
    request: SetStateRequest,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """设置 UTG 的 first_state 属性

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.set_first_state(recording_name, request.node_id)

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.put("/utg/last-state")
async def set_last_state(
    request: SetStateRequest,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """设置 UTG 的 last_state 属性

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.set_last_state(recording_name, request.node_id)

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.patch("/nodes/{node_id}/labels")
async def set_node_labels(
    node_id: str,
    labels_request: SetLabelsRequest,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> Dict[str, Any]:
    """设置节点的自定义标签列表

    从用户会话中读取当前数据集
    """
    try:
        result = await UTGServiceV2.set_node_labels(
            recording_name,
            node_id,
            labels_request.labels,
            labels_request.label_meta
        )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    
@router.get("/nodes/deleted_nodes")
async def get_deleted_nodes(
    recording_name: str = Depends(current_recording_from_header)
) -> List[Dict[str, Any]]:
    """
    获取被删除节点的state_str和image路径
    """
    try:
        result = await UTGServiceV2.get_deleted_nodes(recording_name)
            
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
 
@router.post("/nodes/batch_restore", response_model=BatchRestoreResponse)
async def batch_restore_nodes(
    req: BatchRestoreRequest,
    recording_name: str = Depends(current_recording_from_header_for_write)
) ->  Dict[str, Any]:
    """
    批量恢复节点
    """
    try:
        result = await UTGServiceV2.batch_restore_nodes(
            recording_name,
            req.state_list
        )

        # 返回信息
        return {
            "restored": result.get("restored", []),
            "failed": result.get("failed", []),
            "message": "Batch restore completed"
         }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
