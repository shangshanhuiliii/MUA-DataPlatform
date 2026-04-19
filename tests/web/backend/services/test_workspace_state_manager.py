import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WEB_ROOT = PROJECT_ROOT / "web"
for root in (PROJECT_ROOT, WEB_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from backend.errors import AppError
from backend.session_config import DEVICE_SESSION_IDLE_TIMEOUT_SECONDS, WorkspaceStateManager

EDGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
)
CHROME_USER_AGENT = "Mozilla/5.0 Chrome/136.0.0.0 Safari/537.36"


class WorkspaceStateManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = WorkspaceStateManager()

    async def test_bootstrap_reuses_active_workspace(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=7, current_view="data-editor")
        original_activity = workspace.last_user_activity_at

        same_workspace = await self.manager.bootstrap_workspace(
            workspace.workspace_id,
            user_id=7,
            current_view="task-recorder",
        )

        self.assertEqual(same_workspace.workspace_id, workspace.workspace_id)
        self.assertEqual(same_workspace.current_view, "task-recorder")
        self.assertGreaterEqual(same_workspace.last_user_activity_at, original_activity)

    async def test_bootstrap_does_not_reuse_workspace_for_different_user(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=7, current_view="data-editor")
        await self.manager.set_current_recording(workspace.workspace_id, "record/task_a")

        with self.assertRaises(AppError) as ctx:
            await self.manager.bootstrap_workspace(
                workspace.workspace_id,
                user_id=9,
                current_view="task-recorder",
            )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "WORKSPACE_EXPIRED")

    async def test_bootstrap_rejects_missing_workspace_id(self):
        with self.assertRaises(AppError) as ctx:
            await self.manager.bootstrap_workspace("workspace-missing", user_id=7)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "WORKSPACE_EXPIRED")

    async def test_require_workspace_rejects_principal_mismatch(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=7, current_view="data-editor")

        with self.assertRaises(AppError) as ctx:
            await self.manager.require_workspace(workspace.workspace_id, user_id=9)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "WORKSPACE_EXPIRED")

    async def test_recording_lock_conflict_is_scoped_to_workspace(self):
        workspace_a = await self.manager.bootstrap_workspace(
            None,
            user_id=1,
            username="alice",
            client_shortcode="a7f2",
            client_ip="10.23.45.67",
            client_user_agent=EDGE_USER_AGENT,
            current_view="data-editor",
        )
        workspace_b = await self.manager.bootstrap_workspace(None, user_id=2, username="bob")

        await self.manager.set_current_recording(workspace_a.workspace_id, "record/task_a")

        with self.assertRaises(AppError) as ctx:
            await self.manager.set_current_recording(workspace_b.workspace_id, "record/task_a")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "RECORDING_LOCK_CONFLICT")
        self.assertEqual(ctx.exception.extra["directory_name"], "record/task_a")
        self.assertEqual(ctx.exception.extra["holder_username"], "alice")
        self.assertEqual(ctx.exception.extra["holder_user_id"], 1)
        self.assertEqual(ctx.exception.extra["holder_view"], "data-editor")
        self.assertEqual(ctx.exception.extra["holder_client_shortcode"], "A7F2")
        self.assertEqual(ctx.exception.extra["holder_ip_full"], "10.23.45.67")
        self.assertEqual(ctx.exception.extra["holder_ip_masked"], "10.23.*.*")
        self.assertEqual(ctx.exception.extra["holder_user_agent"], EDGE_USER_AGENT)
        self.assertEqual(ctx.exception.extra["holder_browser_name"], "Edge")
        self.assertEqual(ctx.exception.extra["holder_browser_version"], "136.0.0.0")
        self.assertEqual(ctx.exception.extra["holder_os_name"], "Windows")
        self.assertEqual(ctx.exception.extra["holder_os_version"], "10")
        self.assertEqual(ctx.exception.extra["owner_workspace_id"], workspace_a.workspace_id)
        self.assertEqual(ctx.exception.extra["lock_diagnostic_level"], "normal")
        self.assertIn("locked_at", ctx.exception.extra)
        self.assertIn("expires_at", ctx.exception.extra)

    async def test_recording_lock_conflict_allows_missing_username(self):
        workspace_a = await self.manager.bootstrap_workspace(
            None,
            user_id=1,
            client_shortcode="A7F2",
            client_ip="10.23.45.67",
            client_user_agent=EDGE_USER_AGENT,
            current_view="data-editor",
        )
        workspace_b = await self.manager.bootstrap_workspace(None, user_id=2, username="bob")

        await self.manager.set_current_recording(workspace_a.workspace_id, "record/task_a")

        with self.assertRaises(AppError) as ctx:
            await self.manager.set_current_recording(workspace_b.workspace_id, "record/task_a")

        self.assertIsNone(ctx.exception.extra["holder_username"])
        self.assertEqual(ctx.exception.extra["holder_view"], "data-editor")
        self.assertEqual(ctx.exception.extra["holder_username_reason"], "workspace_username_not_captured")
        self.assertEqual(ctx.exception.extra["diagnostic_reason_summary"], "legacy_client_or_incomplete_session_metadata")
        self.assertEqual(ctx.exception.extra["lock_diagnostic_level"], "degraded")

    async def test_release_current_recording_clears_workspace_context(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=1)
        await self.manager.set_current_recording(workspace.workspace_id, "record/task_a")

        released_workspace = await self.manager.release_current_recording(workspace.workspace_id)

        self.assertIsNone(released_workspace.current_recording)

    async def test_touch_workspace_activity_refreshes_recording_holder_metadata(self):
        workspace = await self.manager.bootstrap_workspace(
            None,
            user_id=1,
            username="alice",
            client_shortcode="task1",
            client_ip="10.23.45.67",
            client_user_agent=EDGE_USER_AGENT,
            current_view="task-recorder",
        )
        await self.manager.set_current_recording(workspace.workspace_id, "record/task_a")

        lease = self.manager._recording_leases["record/task_a"]
        original_expiry = lease.expires_at

        await self.manager.touch_workspace_activity(
            workspace.workspace_id,
            user_id=1,
            client_shortcode="edit2",
            client_ip="10.99.88.77",
            client_user_agent=CHROME_USER_AGENT,
            current_view="data-editor",
        )

        refreshed_lease = self.manager._recording_leases["record/task_a"]
        self.assertEqual(refreshed_lease.holder_username, "alice")
        self.assertEqual(refreshed_lease.holder_user_id, 1)
        self.assertEqual(refreshed_lease.holder_view, "data-editor")
        self.assertEqual(refreshed_lease.holder_client_shortcode, "EDIT2")
        self.assertEqual(refreshed_lease.holder_ip, "10.99.88.77")
        self.assertEqual(refreshed_lease.holder_user_agent, CHROME_USER_AGENT)
        self.assertEqual(refreshed_lease.holder_browser_name, "Chrome")
        self.assertEqual(refreshed_lease.holder_browser_version, "136.0.0.0")
        self.assertEqual(refreshed_lease.holder_os_name, None)
        self.assertEqual(refreshed_lease.holder_os_version, None)
        self.assertGreaterEqual(refreshed_lease.expires_at, original_expiry)

    async def test_recording_lock_conflict_marks_suspicious_when_metadata_is_missing(self):
        workspace_a = await self.manager.bootstrap_workspace(None, user_id=None)
        workspace_b = await self.manager.bootstrap_workspace(None, user_id=2, username="bob")

        await self.manager.set_current_recording(workspace_a.workspace_id, "record/task_a")

        with self.assertRaises(AppError) as ctx:
            await self.manager.set_current_recording(workspace_b.workspace_id, "record/task_a")

        self.assertEqual(ctx.exception.extra["holder_username_reason"], "anonymous_workspace")
        self.assertEqual(ctx.exception.extra["holder_view_reason"], "view_not_reported")
        self.assertEqual(ctx.exception.extra["holder_client_shortcode_reason"], "client_shortcode_not_sent")
        self.assertEqual(ctx.exception.extra["holder_ip_reason"], "client_ip_unavailable")
        self.assertEqual(ctx.exception.extra["holder_user_agent_reason"], "user_agent_unavailable")
        self.assertEqual(ctx.exception.extra["diagnostic_reason_summary"], "legacy_client_or_incomplete_session_metadata")
        self.assertEqual(ctx.exception.extra["lock_diagnostic_level"], "suspicious")
        self.assertIn("旧版本会话遗留", ctx.exception.extra["lock_diagnostic_message"])

    async def test_recording_lock_conflict_reports_missing_user_agent_reason_after_renewal(self):
        workspace_a = await self.manager.bootstrap_workspace(
            None,
            user_id=1,
            username="alice",
            client_shortcode="A7F2",
            client_ip="10.23.45.67",
            current_view="data-editor",
        )
        workspace_b = await self.manager.bootstrap_workspace(None, user_id=2, username="bob")

        await self.manager.set_current_recording(workspace_a.workspace_id, "record/task_a")
        await self.manager.touch_workspace_activity(
            workspace_a.workspace_id,
            user_id=1,
            current_view="data-editor",
        )

        with self.assertRaises(AppError) as ctx:
            await self.manager.set_current_recording(workspace_b.workspace_id, "record/task_a")

        self.assertEqual(ctx.exception.extra["holder_browser_name"], None)
        self.assertEqual(ctx.exception.extra["holder_user_agent_reason"], "user_agent_not_captured")
        self.assertEqual(ctx.exception.extra["lock_diagnostic_level"], "degraded")

    async def test_recording_lock_conflict_reports_view_lost_on_renewal(self):
        workspace_a = await self.manager.bootstrap_workspace(
            None,
            user_id=1,
            username="alice",
            client_shortcode="A7F2",
            client_ip="10.23.45.67",
            client_user_agent=EDGE_USER_AGENT,
        )
        workspace_b = await self.manager.bootstrap_workspace(None, user_id=2, username="bob")

        await self.manager.set_current_recording(workspace_a.workspace_id, "record/task_a")
        await self.manager.touch_workspace_activity(
            workspace_a.workspace_id,
            user_id=1,
        )

        with self.assertRaises(AppError) as ctx:
            await self.manager.set_current_recording(workspace_b.workspace_id, "record/task_a")

        self.assertEqual(ctx.exception.extra["holder_view_reason"], "view_lost_on_renewal")
        self.assertEqual(ctx.exception.extra["lock_diagnostic_level"], "degraded")

    async def test_is_device_locked_tracks_active_device_session(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=1)
        device_session = await self.manager.create_device_session(
            workspace.workspace_id,
            user_id=1,
            device_serial="device://serial-1",
        )

        self.assertTrue(await self.manager.is_device_locked("device://serial-1"))

        await self.manager.release_device_session(device_session.device_session_id)

        self.assertFalse(await self.manager.is_device_locked("device://serial-1"))

    async def test_is_device_locked_releases_expired_device_session(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=1)
        device_session = await self.manager.create_device_session(
            workspace.workspace_id,
            user_id=1,
            device_serial="device://serial-2",
        )

        self.manager._device_sessions[device_session.device_session_id].last_user_activity_at -= (
            DEVICE_SESSION_IDLE_TIMEOUT_SECONDS + 1
        )

        self.assertFalse(await self.manager.is_device_locked("device://serial-2"))
        self.assertNotIn(device_session.device_session_id, self.manager._device_sessions)

    async def test_touch_device_transport_rejects_expired_session(self):
        workspace = await self.manager.bootstrap_workspace(None, user_id=1)
        device_session = await self.manager.create_device_session(
            workspace.workspace_id,
            user_id=1,
            device_serial="device://serial-3",
        )
        self.manager._device_sessions[device_session.device_session_id].last_user_activity_at -= (
            DEVICE_SESSION_IDLE_TIMEOUT_SECONDS + 1
        )

        with self.assertRaises(AppError) as ctx:
            await self.manager.touch_device_transport(device_session.device_session_id)

        self.assertEqual(ctx.exception.status_code, 410)
        self.assertEqual(ctx.exception.code, "DEVICE_SESSION_EXPIRED")
        self.assertNotIn(device_session.device_session_id, self.manager._device_sessions)


if __name__ == "__main__":
    unittest.main()
