"""Workspace, device-session, and runtime state schemas."""
from __future__ import annotations

import time
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _workspace_id() -> str:
    return str(uuid4())


def _device_session_id() -> str:
    return f"device-{uuid4()}"


def _runtime_id() -> str:
    return f"runtime-{uuid4()}"


class WorkspaceState(BaseModel):
    workspace_id: str = Field(default_factory=_workspace_id)
    user_id: Optional[int] = None
    username: Optional[str] = None
    client_shortcode: Optional[str] = None
    client_ip: Optional[str] = None
    client_user_agent: Optional[str] = None
    current_view: Optional[str] = None
    current_recording: Optional[str] = None
    last_user_activity_at: float = Field(default_factory=time.time)
    last_server_touch_at: float = Field(default_factory=time.time)
    status: Literal["active", "expired", "released"] = "active"


class RecordingLease(BaseModel):
    resource_id: str
    owner_id: str
    owner_type: Literal["workspace"] = "workspace"
    holder_user_id: Optional[int] = None
    holder_username: Optional[str] = None
    holder_view: Optional[str] = None
    holder_client_shortcode: Optional[str] = None
    holder_ip: Optional[str] = None
    holder_user_agent: Optional[str] = None
    holder_browser_name: Optional[str] = None
    holder_browser_version: Optional[str] = None
    holder_os_name: Optional[str] = None
    holder_os_version: Optional[str] = None
    locked_at: float = Field(default_factory=time.time)
    expires_at: float
    renewed_at: float = Field(default_factory=time.time)
    renewal_count: int = 0


class DeviceSessionState(BaseModel):
    device_session_id: str = Field(default_factory=_device_session_id)
    workspace_id: str
    user_id: Optional[int] = None
    device_serial: str
    state: Literal["connecting", "connected", "disconnected", "expired"] = "connecting"
    last_transport_alive_at: float = Field(default_factory=time.time)
    last_user_activity_at: float = Field(default_factory=time.time)


class RecordingRuntimeState(BaseModel):
    recording_runtime_id: str = Field(default_factory=_runtime_id)
    device_session_id: str
    workspace_id: str
    task_id: Optional[str] = None
    directory_name: str
    recorded_by: Optional[int] = None
    state: Literal["starting", "recording", "paused", "stopping", "stopped", "failed", "expired"] = "starting"
    last_user_action_at: float = Field(default_factory=time.time)
