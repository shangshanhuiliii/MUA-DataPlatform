import logging
import ipaddress
from typing import Optional

from fastapi import APIRouter, Body, Depends, Request

from backend.auth.dependencies import get_optional_current_user
from backend.errors import app_error
from backend.models.user import User
from backend.session_config import get_workspace_data, workspace_state_manager

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])
logger = logging.getLogger(__name__)


def _workspace_response_payload(workspace):
    return {
        "workspace_id": workspace.workspace_id,
        "current_recording": workspace.current_recording,
        "current_view": workspace.current_view,
        "status": workspace.status,
        "expires_at": workspace_state_manager.workspace_expires_at(workspace),
    }


def _ensure_matching_workspace_ids(header_workspace_id: str, path_workspace_id: str) -> None:
    if header_workspace_id != path_workspace_id:
        logger.warning("Workspace header/path mismatch: %s != %s", header_workspace_id, path_workspace_id)
        raise app_error(409, "WORKSPACE_EXPIRED", "Workspace context is out of sync, please reload the current tab")


def _extract_client_ip(request: Request) -> Optional[str]:
    client = request.client
    if client and client.host:
        try:
            return str(ipaddress.ip_address(client.host))
        except ValueError:
            return None
    return None


@router.post("/bootstrap")
async def bootstrap_workspace(
    request: Request,
    payload: Optional[dict] = Body(default=None),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    payload = payload or {}
    workspace = await workspace_state_manager.bootstrap_workspace(
        payload.get("workspace_id"),
        user_id=current_user.id if current_user else None,
        username=current_user.username if current_user else None,
        client_shortcode=request.headers.get("X-Client-Shortcode"),
        client_ip=_extract_client_ip(request),
        client_user_agent=request.headers.get("User-Agent"),
        current_view=payload.get("current_view"),
    )
    return _workspace_response_payload(workspace)


@router.post("/{workspace_id}/activity")
async def report_workspace_activity(
    workspace_id: str,
    request: Request,
    payload: Optional[dict] = Body(default=None),
    workspace=Depends(get_workspace_data),
):
    payload = payload or {}
    _ensure_matching_workspace_ids(workspace.workspace_id, workspace_id)
    workspace = await workspace_state_manager.touch_workspace_activity(
        workspace.workspace_id,
        user_id=workspace.user_id,
        client_shortcode=request.headers.get("X-Client-Shortcode"),
        client_ip=_extract_client_ip(request),
        client_user_agent=request.headers.get("User-Agent"),
        current_view=payload.get("current_view"),
    )
    return _workspace_response_payload(workspace)


@router.delete("/{workspace_id}")
async def release_workspace(
    workspace_id: str,
    workspace=Depends(get_workspace_data),
):
    _ensure_matching_workspace_ids(workspace.workspace_id, workspace_id)
    await workspace_state_manager.release_workspace(workspace.workspace_id)
    return {"message": "Workspace released", "workspace_id": workspace.workspace_id}
