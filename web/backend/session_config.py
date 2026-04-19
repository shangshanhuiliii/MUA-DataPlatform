"""Unified workspace / device session / recording runtime state management."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from fastapi import Depends, Header

from .auth.dependencies import get_current_active_user
from .errors import app_error
from .models.user import User
from .schemas.session import (
    DeviceSessionState,
    RecordingLease,
    RecordingRuntimeState,
    WorkspaceState,
)

logger = logging.getLogger(__name__)


WORKSPACE_IDLE_TIMEOUT_SECONDS = int(os.getenv("WORKSPACE_IDLE_TIMEOUT_SECONDS", "1800"))
DEVICE_SESSION_IDLE_TIMEOUT_SECONDS = int(os.getenv("DEVICE_SESSION_IDLE_TIMEOUT_SECONDS", "300"))
RECORDING_RUNTIME_LEASE_SECONDS = int(os.getenv("RECORDING_RUNTIME_LEASE_SECONDS", "90"))
SESSION_CLEANUP_INTERVAL = int(os.getenv("SESSION_CLEANUP_INTERVAL", "20"))
WEBSOCKET_PING_INTERVAL = int(os.getenv("WEBSOCKET_PING_INTERVAL_SECONDS", "15"))
WEBSOCKET_PONG_TIMEOUT = int(os.getenv("WEBSOCKET_PONG_TIMEOUT_SECONDS", "10"))

# Backward-compatible alias used by legacy callers/logging.
SESSION_IDLE_TIMEOUT = WORKSPACE_IDLE_TIMEOUT_SECONDS


class WorkspaceStateManager:
    def __init__(self) -> None:
        self._workspaces: Dict[str, WorkspaceState] = {}
        self._recording_leases: Dict[str, RecordingLease] = {}
        self._device_sessions: Dict[str, DeviceSessionState] = {}
        self._runtime_sessions: Dict[str, RecordingRuntimeState] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return time.time()

    def _workspace_expired(self, workspace: WorkspaceState, now: Optional[float] = None) -> bool:
        return (now or self._now()) - workspace.last_user_activity_at > WORKSPACE_IDLE_TIMEOUT_SECONDS

    def _device_expired(self, device_session: DeviceSessionState, now: Optional[float] = None) -> bool:
        return (now or self._now()) - device_session.last_user_activity_at > DEVICE_SESSION_IDLE_TIMEOUT_SECONDS

    def _runtime_expired(self, runtime: RecordingRuntimeState, now: Optional[float] = None) -> bool:
        return (now or self._now()) - runtime.last_user_action_at > RECORDING_RUNTIME_LEASE_SECONDS

    def _recording_lease_expired(self, lease: RecordingLease, now: Optional[float] = None) -> bool:
        return lease.expires_at <= (now or self._now())

    def workspace_expires_at(self, workspace: WorkspaceState) -> float:
        return workspace.last_user_activity_at + WORKSPACE_IDLE_TIMEOUT_SECONDS

    def _workspace_owned_by(self, workspace: WorkspaceState, user_id: Optional[int]) -> bool:
        return workspace.user_id == user_id

    def _normalize_client_shortcode(self, client_shortcode: Optional[str]) -> Optional[str]:
        if not client_shortcode or not isinstance(client_shortcode, str):
            return None
        normalized = client_shortcode.strip().upper()
        return normalized[:12] or None

    def _normalize_client_ip(self, client_ip: Optional[str]) -> Optional[str]:
        if not client_ip or not isinstance(client_ip, str):
            return None
        normalized = client_ip.strip()
        if not normalized:
            return None
        try:
            return str(ipaddress.ip_address(normalized))
        except ValueError:
            return None

    def _normalize_client_user_agent(self, client_user_agent: Optional[str]) -> Optional[str]:
        if not client_user_agent or not isinstance(client_user_agent, str):
            return None
        normalized = client_user_agent.strip()
        return normalized[:1024] or None

    def _extract_user_agent_version(self, client_user_agent: str, marker: str) -> Optional[str]:
        match = re.search(re.escape(marker) + r"([^\s;()]+)", client_user_agent, flags=re.IGNORECASE)
        if not match:
            return None
        version = match.group(1).strip()
        return version or None

    def _parse_browser_info(self, client_user_agent: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if not client_user_agent:
            return None, None

        lowered = client_user_agent.lower()
        if "edg/" in lowered:
            return "Edge", self._extract_user_agent_version(client_user_agent, "Edg/")
        if "chrome/" in lowered and "edg/" not in lowered:
            return "Chrome", self._extract_user_agent_version(client_user_agent, "Chrome/")
        if "firefox/" in lowered:
            return "Firefox", self._extract_user_agent_version(client_user_agent, "Firefox/")
        if "safari/" in lowered and "chrome/" not in lowered and "chromium/" not in lowered:
            version = self._extract_user_agent_version(client_user_agent, "Version/")
            if version is None:
                version = self._extract_user_agent_version(client_user_agent, "Safari/")
            return "Safari", version
        return "Other", None

    def _parse_os_info(self, client_user_agent: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if not client_user_agent:
            return None, None

        if "Windows NT 10.0" in client_user_agent:
            return "Windows", "10"
        if "Windows NT 6.3" in client_user_agent:
            return "Windows", "8.1"
        if "Windows NT 6.2" in client_user_agent:
            return "Windows", "8"
        if "Windows NT 6.1" in client_user_agent:
            return "Windows", "7"

        mac_match = re.search(r"Mac OS X ([0-9_]+)", client_user_agent)
        if mac_match:
            return "macOS", mac_match.group(1).replace("_", ".")

        ios_match = re.search(r"(?:iPhone|CPU(?: iPhone)?) OS ([0-9_]+)", client_user_agent)
        if ios_match:
            return "iOS", ios_match.group(1).replace("_", ".")

        android_match = re.search(r"Android ([0-9.]+)", client_user_agent)
        if android_match:
            return "Android", android_match.group(1)

        if "Linux" in client_user_agent:
            return "Linux", None

        return None, None

    def _mask_client_ip(self, client_ip: Optional[str]) -> Optional[str]:
        if not client_ip:
            return None
        if ":" in client_ip:
            parts = [part for part in client_ip.split(":") if part]
            if not parts:
                return None
            if len(parts) == 1:
                return f"{parts[0]}:*"
            return f"{parts[0]}:{parts[1]}:*"

        segments = client_ip.split(".")
        if len(segments) != 4:
            return client_ip
        return f"{segments[0]}.{segments[1]}.*.*"

    def _build_recording_lock_conflict_payload(self, directory_name: str, lease: RecordingLease) -> dict:
        payload = {
            "directory_name": directory_name,
            "holder_username": lease.holder_username,
            "holder_user_id": lease.holder_user_id,
            "holder_view": lease.holder_view,
            "holder_client_shortcode": lease.holder_client_shortcode,
            "holder_ip_full": lease.holder_ip,
            "holder_ip_masked": self._mask_client_ip(lease.holder_ip),
            "holder_user_agent": lease.holder_user_agent,
            "holder_browser_name": lease.holder_browser_name,
            "holder_browser_version": lease.holder_browser_version,
            "holder_os_name": lease.holder_os_name,
            "holder_os_version": lease.holder_os_version,
            "owner_workspace_id": lease.owner_id,
            "locked_at": lease.locked_at,
            "expires_at": lease.expires_at,
        }

        missing_fields = []
        primary_missing_fields = []

        if lease.holder_username is None:
            if lease.holder_user_id is None:
                payload["holder_username_reason"] = "anonymous_workspace"
            else:
                payload["holder_username_reason"] = "workspace_username_not_captured"
            missing_fields.append("username")
            primary_missing_fields.append("username")

        if lease.holder_view is None:
            payload["holder_view_reason"] = (
                "view_lost_on_renewal"
                if lease.renewal_count > 0
                else "view_not_reported"
            )
            missing_fields.append("view")
            primary_missing_fields.append("view")

        if lease.holder_client_shortcode is None:
            payload["holder_client_shortcode_reason"] = "client_shortcode_not_sent"
            missing_fields.append("client_shortcode")
            primary_missing_fields.append("client_shortcode")

        if lease.holder_ip is None:
            payload["holder_ip_reason"] = "client_ip_unavailable"
            missing_fields.append("ip")
            primary_missing_fields.append("ip")

        if lease.holder_user_agent is None:
            payload["holder_user_agent_reason"] = (
                "user_agent_not_captured"
                if lease.renewal_count > 0
                else "user_agent_unavailable"
            )
            missing_fields.append("user_agent")

        if len(primary_missing_fields) >= 3:
            payload["diagnostic_reason_summary"] = "legacy_client_or_incomplete_session_metadata"
            payload["lock_diagnostic_level"] = "suspicious"
            payload["lock_diagnostic_message"] = "锁存在，但占用者元数据采集不完整，可能为旧版本会话遗留。"
        elif missing_fields:
            payload["diagnostic_reason_summary"] = (
                "state_capture_gap"
                if missing_fields == ["view"]
                else "legacy_client_or_incomplete_session_metadata"
            )
            payload["lock_diagnostic_level"] = "degraded"
            payload["lock_diagnostic_message"] = "锁存在，但部分占用者信息缺失，可根据缺失原因继续排查。"
        else:
            payload["lock_diagnostic_level"] = "normal"

        return payload

    async def bootstrap_workspace(
        self,
        requested_workspace_id: Optional[str],
        *,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        client_shortcode: Optional[str] = None,
        client_ip: Optional[str] = None,
        client_user_agent: Optional[str] = None,
        current_view: Optional[str] = None,
    ) -> WorkspaceState:
        now = self._now()
        normalized_shortcode = self._normalize_client_shortcode(client_shortcode)
        normalized_ip = self._normalize_client_ip(client_ip)
        normalized_user_agent = self._normalize_client_user_agent(client_user_agent)
        async with self._lock:
            if requested_workspace_id:
                workspace = self._workspaces.get(requested_workspace_id)
                if workspace is None:
                    raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please restore a new tab workspace")
                if self._workspace_expired(workspace, now):
                    await self._release_workspace_locked(requested_workspace_id, status="expired")
                    raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please restore a new tab workspace")
                if not self._workspace_owned_by(workspace, user_id):
                    raise app_error(409, "WORKSPACE_EXPIRED", "Workspace belongs to another login session")

                workspace.last_user_activity_at = now
                if username is not None:
                    workspace.username = username
                if normalized_shortcode is not None:
                    workspace.client_shortcode = normalized_shortcode
                if normalized_ip is not None:
                    workspace.client_ip = normalized_ip
                if normalized_user_agent is not None:
                    workspace.client_user_agent = normalized_user_agent
                if current_view is not None:
                    workspace.current_view = current_view
                workspace.status = "active"
                workspace.last_server_touch_at = now
                return workspace

            workspace = WorkspaceState(
                user_id=user_id,
                username=username,
                client_shortcode=normalized_shortcode,
                client_ip=normalized_ip,
                client_user_agent=normalized_user_agent,
                current_view=current_view,
            )
            workspace.last_user_activity_at = now
            workspace.last_server_touch_at = now
            self._workspaces[workspace.workspace_id] = workspace
            return workspace

    async def require_workspace(self, workspace_id: Optional[str], *, user_id: Optional[int] = None) -> WorkspaceState:
        if not workspace_id:
            raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please reload and restore the tab workspace")

        now = self._now()
        async with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please re-select recording")
            if self._workspace_expired(workspace, now):
                await self._release_workspace_locked(workspace_id, status="expired")
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please re-select recording")
            if workspace.status != "active":
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace is no longer active")
            if not self._workspace_owned_by(workspace, user_id):
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace belongs to another login session")
            workspace.last_server_touch_at = now
            return workspace

    async def touch_workspace_activity(
        self,
        workspace_id: str,
        *,
        user_id: Optional[int] = None,
        client_shortcode: Optional[str] = None,
        client_ip: Optional[str] = None,
        client_user_agent: Optional[str] = None,
        current_view: Optional[str] = None,
    ) -> WorkspaceState:
        now = self._now()
        normalized_shortcode = self._normalize_client_shortcode(client_shortcode)
        normalized_ip = self._normalize_client_ip(client_ip)
        normalized_user_agent = self._normalize_client_user_agent(client_user_agent)
        async with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None or self._workspace_expired(workspace, now):
                if workspace is not None:
                    await self._release_workspace_locked(workspace_id, status="expired")
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please re-select recording")
            if not self._workspace_owned_by(workspace, user_id):
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace belongs to another login session")

            workspace.last_user_activity_at = now
            workspace.last_server_touch_at = now
            if normalized_shortcode is not None:
                workspace.client_shortcode = normalized_shortcode
            if normalized_ip is not None:
                workspace.client_ip = normalized_ip
            if normalized_user_agent is not None:
                workspace.client_user_agent = normalized_user_agent
            if current_view is not None:
                workspace.current_view = current_view

            if workspace.current_recording:
                lease = self._recording_leases.get(workspace.current_recording)
                if lease and lease.owner_id == workspace_id:
                    holder_browser_name, holder_browser_version = self._parse_browser_info(workspace.client_user_agent)
                    holder_os_name, holder_os_version = self._parse_os_info(workspace.client_user_agent)
                    lease.holder_user_id = workspace.user_id
                    lease.holder_username = workspace.username
                    lease.holder_view = workspace.current_view
                    lease.holder_client_shortcode = workspace.client_shortcode
                    lease.holder_ip = workspace.client_ip
                    lease.holder_user_agent = workspace.client_user_agent
                    lease.holder_browser_name = holder_browser_name
                    lease.holder_browser_version = holder_browser_version
                    lease.holder_os_name = holder_os_name
                    lease.holder_os_version = holder_os_version
                    lease.renewed_at = now
                    lease.renewal_count += 1
                    lease.expires_at = now + WORKSPACE_IDLE_TIMEOUT_SECONDS

            return workspace

    async def set_current_recording(self, workspace_id: str, directory_name: str) -> WorkspaceState:
        now = self._now()
        async with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None or self._workspace_expired(workspace, now):
                if workspace is not None:
                    await self._release_workspace_locked(workspace_id, status="expired")
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please re-select recording")

            old_recording = workspace.current_recording
            if old_recording and old_recording != directory_name:
                await self._release_recording_locked(old_recording, workspace_id)

            existing_lease = self._recording_leases.get(directory_name)
            if existing_lease and self._recording_lease_expired(existing_lease, now):
                del self._recording_leases[directory_name]
                existing_lease = None

            if existing_lease and existing_lease.owner_id != workspace_id:
                conflict_payload = self._build_recording_lock_conflict_payload(directory_name, existing_lease)
                raise app_error(
                    409,
                    "RECORDING_LOCK_CONFLICT",
                    "Recording is currently used by another workspace",
                    **conflict_payload,
                )

            holder_browser_name, holder_browser_version = self._parse_browser_info(workspace.client_user_agent)
            holder_os_name, holder_os_version = self._parse_os_info(workspace.client_user_agent)
            self._recording_leases[directory_name] = RecordingLease(
                resource_id=directory_name,
                owner_id=workspace_id,
                holder_user_id=workspace.user_id,
                holder_username=workspace.username,
                holder_view=workspace.current_view,
                holder_client_shortcode=workspace.client_shortcode,
                holder_ip=workspace.client_ip,
                holder_user_agent=workspace.client_user_agent,
                holder_browser_name=holder_browser_name,
                holder_browser_version=holder_browser_version,
                holder_os_name=holder_os_name,
                holder_os_version=holder_os_version,
                locked_at=now,
                expires_at=now + WORKSPACE_IDLE_TIMEOUT_SECONDS,
                renewed_at=now,
                renewal_count=0,
            )
            workspace.current_recording = directory_name
            workspace.last_user_activity_at = now
            workspace.last_server_touch_at = now
            workspace.status = "active"
            return workspace

    async def release_current_recording(self, workspace_id: str) -> WorkspaceState:
        async with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please re-select recording")
            if workspace.current_recording:
                await self._release_recording_locked(workspace.current_recording, workspace_id)
            workspace.current_recording = None
            workspace.last_server_touch_at = self._now()
            return workspace

    async def release_workspace(self, workspace_id: str) -> None:
        async with self._lock:
            await self._release_workspace_locked(workspace_id, status="released")

    async def _release_recording_locked(self, directory_name: str, workspace_id: str) -> None:
        lease = self._recording_leases.get(directory_name)
        if lease and lease.owner_id == workspace_id:
            del self._recording_leases[directory_name]

    async def _release_workspace_locked(self, workspace_id: str, *, status: str) -> None:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            return

        if workspace.current_recording:
            await self._release_recording_locked(workspace.current_recording, workspace_id)

        device_sessions = [
            device_session_id
            for device_session_id, device_session in self._device_sessions.items()
            if device_session.workspace_id == workspace_id
        ]
        for device_session_id in device_sessions:
            await self._release_device_session_locked(device_session_id, status="expired")

        workspace.status = status
        del self._workspaces[workspace_id]

    async def create_device_session(self, workspace_id: str, user_id: Optional[int], device_serial: str) -> DeviceSessionState:
        now = self._now()
        async with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None or self._workspace_expired(workspace, now):
                if workspace is not None:
                    await self._release_workspace_locked(workspace_id, status="expired")
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace expired, please reconnect from an active tab")
            if not self._workspace_owned_by(workspace, user_id):
                raise app_error(409, "WORKSPACE_EXPIRED", "Workspace belongs to another login session")

            for device_session_id, device_session in list(self._device_sessions.items()):
                if self._device_expired(device_session, now):
                    await self._release_device_session_locked(device_session_id, status="expired")
                    continue
                if device_session.device_serial == device_serial and device_session.state == "connected":
                    raise app_error(409, "DEVICE_LOCK_CONFLICT", "Device is currently used by another workspace")

            device_session = DeviceSessionState(
                workspace_id=workspace_id,
                user_id=user_id,
                device_serial=device_serial,
                state="connected",
            )
            device_session.last_transport_alive_at = now
            device_session.last_user_activity_at = now
            self._device_sessions[device_session.device_session_id] = device_session
            return device_session

    async def require_device_session(self, device_session_id: str) -> DeviceSessionState:
        now = self._now()
        async with self._lock:
            device_session = self._device_sessions.get(device_session_id)
            if device_session is None:
                raise app_error(410, "DEVICE_SESSION_EXPIRED", "Device connection expired")
            if self._device_expired(device_session, now):
                await self._release_device_session_locked(device_session_id, status="expired")
                raise app_error(410, "DEVICE_SESSION_EXPIRED", "Device connection expired")
            return device_session

    async def touch_device_transport(self, device_session_id: str) -> DeviceSessionState:
        now = self._now()
        async with self._lock:
            device_session = self._device_sessions.get(device_session_id)
            if device_session is None or self._device_expired(device_session, now):
                if device_session is not None:
                    await self._release_device_session_locked(device_session_id, status="expired")
                raise app_error(410, "DEVICE_SESSION_EXPIRED", "Device connection expired")
            device_session.last_transport_alive_at = now
            return device_session

    async def touch_device_activity(self, device_session_id: str) -> DeviceSessionState:
        now = self._now()
        async with self._lock:
            device_session = self._device_sessions.get(device_session_id)
            if device_session is None or self._device_expired(device_session, now):
                if device_session is not None:
                    await self._release_device_session_locked(device_session_id, status="expired")
                raise app_error(410, "DEVICE_SESSION_EXPIRED", "Device connection expired")
            device_session.last_transport_alive_at = now
            device_session.last_user_activity_at = now
            return device_session

    async def is_device_locked(self, device_serial: str) -> bool:
        now = self._now()
        async with self._lock:
            for device_session_id, device_session in list(self._device_sessions.items()):
                if self._device_expired(device_session, now):
                    await self._release_device_session_locked(device_session_id, status="expired")
                    continue
                if device_session.device_serial == device_serial and device_session.state == "connected":
                    return True
            return False

    async def release_device_session(self, device_session_id: str, *, status: str = "disconnected") -> None:
        async with self._lock:
            await self._release_device_session_locked(device_session_id, status=status)

    async def _release_device_session_locked(self, device_session_id: str, *, status: str) -> None:
        device_session = self._device_sessions.get(device_session_id)
        if device_session is None:
            return

        runtime_ids = [
            runtime_id
            for runtime_id, runtime in self._runtime_sessions.items()
            if runtime.device_session_id == device_session_id
        ]
        for runtime_id in runtime_ids:
            await self._release_runtime_locked(runtime_id, status="expired")

        device_session.state = status  # type: ignore[assignment]
        del self._device_sessions[device_session_id]

    async def create_runtime_session(
        self,
        *,
        recording_runtime_id: str,
        device_session_id: str,
        workspace_id: str,
        task_id: Optional[str],
        directory_name: str,
        recorded_by: Optional[int],
    ) -> RecordingRuntimeState:
        now = self._now()
        async with self._lock:
            device_session = self._device_sessions.get(device_session_id)
            if device_session is None or self._device_expired(device_session, now):
                if device_session is not None:
                    await self._release_device_session_locked(device_session_id, status="expired")
                raise app_error(410, "DEVICE_SESSION_EXPIRED", "Device connection expired")

            for runtime_id, runtime in list(self._runtime_sessions.items()):
                if self._runtime_expired(runtime, now):
                    await self._release_runtime_locked(runtime_id, status="expired")
                    continue
                if runtime.device_session_id == device_session_id and runtime.state in {"starting", "recording", "paused"}:
                    raise app_error(409, "RECORDING_RUNTIME_ACTIVE", "Recording runtime is already active for this device session")

            runtime = RecordingRuntimeState(
                recording_runtime_id=recording_runtime_id,
                device_session_id=device_session_id,
                workspace_id=workspace_id,
                task_id=task_id,
                directory_name=directory_name,
                recorded_by=recorded_by,
                state="starting",
            )
            runtime.last_user_action_at = now
            self._runtime_sessions[runtime.recording_runtime_id] = runtime
            return runtime

    async def require_runtime_session(self, recording_runtime_id: str) -> RecordingRuntimeState:
        now = self._now()
        async with self._lock:
            runtime = self._runtime_sessions.get(recording_runtime_id)
            if runtime is None:
                raise app_error(410, "RECORDING_RUNTIME_EXPIRED", "Recording runtime expired")
            if self._runtime_expired(runtime, now):
                await self._release_runtime_locked(recording_runtime_id, status="expired")
                raise app_error(410, "RECORDING_RUNTIME_EXPIRED", "Recording runtime expired")
            return runtime

    async def set_runtime_state(self, recording_runtime_id: str, state: str) -> RecordingRuntimeState:
        async with self._lock:
            runtime = self._runtime_sessions.get(recording_runtime_id)
            if runtime is None:
                raise app_error(410, "RECORDING_RUNTIME_EXPIRED", "Recording runtime expired")
            runtime.state = state  # type: ignore[assignment]
            runtime.last_user_action_at = self._now()
            return runtime

    async def touch_runtime_activity(self, recording_runtime_id: str) -> RecordingRuntimeState:
        now = self._now()
        async with self._lock:
            runtime = self._runtime_sessions.get(recording_runtime_id)
            if runtime is None or self._runtime_expired(runtime, now):
                if runtime is not None:
                    await self._release_runtime_locked(recording_runtime_id, status="expired")
                raise app_error(410, "RECORDING_RUNTIME_EXPIRED", "Recording runtime expired")
            runtime.last_user_action_at = now
            return runtime

    async def release_runtime_session(self, recording_runtime_id: str, *, status: str = "stopped") -> None:
        async with self._lock:
            await self._release_runtime_locked(recording_runtime_id, status=status)

    async def _release_runtime_locked(self, recording_runtime_id: str, *, status: str) -> None:
        runtime = self._runtime_sessions.get(recording_runtime_id)
        if runtime is None:
            return
        runtime.state = status  # type: ignore[assignment]
        del self._runtime_sessions[recording_runtime_id]

    async def cleanup_expired(self) -> int:
        now = self._now()
        cleaned = 0
        async with self._lock:
            expired_runtime_ids = [
                runtime_id for runtime_id, runtime in self._runtime_sessions.items()
                if self._runtime_expired(runtime, now)
            ]
            for runtime_id in expired_runtime_ids:
                await self._release_runtime_locked(runtime_id, status="expired")
                cleaned += 1

            expired_device_ids = [
                device_session_id for device_session_id, device_session in self._device_sessions.items()
                if self._device_expired(device_session, now)
            ]
            for device_session_id in expired_device_ids:
                await self._release_device_session_locked(device_session_id, status="expired")
                cleaned += 1

            expired_workspace_ids = [
                workspace_id for workspace_id, workspace in self._workspaces.items()
                if self._workspace_expired(workspace, now)
            ]
            for workspace_id in expired_workspace_ids:
                await self._release_workspace_locked(workspace_id, status="expired")
                cleaned += 1

            expired_recordings = [
                directory_name for directory_name, lease in self._recording_leases.items()
                if self._recording_lease_expired(lease, now)
            ]
            for directory_name in expired_recordings:
                del self._recording_leases[directory_name]
                cleaned += 1

        return cleaned


workspace_state_manager = WorkspaceStateManager()


async def get_workspace_data(
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
    current_user: User = Depends(get_current_active_user),
) -> WorkspaceState:
    return await workspace_state_manager.require_workspace(x_workspace_id, user_id=current_user.id)


async def get_workspace_data_for_write(
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
    current_user: User = Depends(get_current_active_user),
) -> WorkspaceState:
    workspace = await workspace_state_manager.require_workspace(x_workspace_id, user_id=current_user.id)
    return await workspace_state_manager.touch_workspace_activity(workspace.workspace_id, user_id=current_user.id)


async def _get_current_recording_from_workspace(workspace: WorkspaceState) -> str:
    if not workspace.current_recording:
        raise app_error(428, "RECORDING_REQUIRED", "Please select a recording first")
    return workspace.current_recording


async def _current_recording_dependency(
    x_workspace_id: Optional[str],
    *,
    touch: bool,
    user_id: int,
) -> str:
    workspace = await (
        workspace_state_manager.touch_workspace_activity(x_workspace_id, user_id=user_id)
        if touch
        else workspace_state_manager.require_workspace(x_workspace_id, user_id=user_id)
    )
    return await _get_current_recording_from_workspace(workspace)


async def current_recording_from_header(
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
    current_user: User = Depends(get_current_active_user),
) -> str:
    return await _current_recording_dependency(x_workspace_id, touch=False, user_id=current_user.id)


async def current_recording_from_header_for_write(
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
    current_user: User = Depends(get_current_active_user),
) -> str:
    return await _current_recording_dependency(x_workspace_id, touch=True, user_id=current_user.id)


async def is_device_locked(device_serial: str) -> bool:
    return await workspace_state_manager.is_device_locked(device_serial)


_cleanup_task: Optional[asyncio.Task] = None
_cleanup_running = False


async def start_session_cleanup_task(
    interval_seconds: int = SESSION_CLEANUP_INTERVAL,
    timeout_seconds: int = SESSION_IDLE_TIMEOUT,
):
    _ = timeout_seconds
    global _cleanup_running
    if _cleanup_running:
        return

    _cleanup_running = True
    try:
        while _cleanup_running:
            await asyncio.sleep(interval_seconds)
            if not _cleanup_running:
                break
            cleaned = await workspace_state_manager.cleanup_expired()
            if cleaned:
                logger.info("Cleaned up %s expired unified session state entries", cleaned)
    except asyncio.CancelledError:
        logger.info("Unified session cleanup task cancelled")
    finally:
        _cleanup_running = False


def schedule_session_cleanup(
    interval_seconds: int = SESSION_CLEANUP_INTERVAL,
    timeout_seconds: int = SESSION_IDLE_TIMEOUT,
):
    _ = timeout_seconds
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        return
    _cleanup_task = asyncio.create_task(start_session_cleanup_task(interval_seconds=interval_seconds))


async def stop_session_cleanup_task():
    global _cleanup_task, _cleanup_running
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_running = False
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


__all__ = [
    "WORKSPACE_IDLE_TIMEOUT_SECONDS",
    "DEVICE_SESSION_IDLE_TIMEOUT_SECONDS",
    "RECORDING_RUNTIME_LEASE_SECONDS",
    "SESSION_CLEANUP_INTERVAL",
    "WEBSOCKET_PING_INTERVAL",
    "WEBSOCKET_PONG_TIMEOUT",
    "SESSION_IDLE_TIMEOUT",
    "workspace_state_manager",
    "get_workspace_data",
    "get_workspace_data_for_write",
    "current_recording_from_header",
    "current_recording_from_header_for_write",
    "is_device_locked",
    "schedule_session_cleanup",
    "start_session_cleanup_task",
    "stop_session_cleanup_task",
]
