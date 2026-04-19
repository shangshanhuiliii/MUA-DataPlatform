import asyncio
from datetime import timedelta
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WEB_ROOT = PROJECT_ROOT / "web"
for root in (PROJECT_ROOT, WEB_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from backend.auth.dependencies import get_current_active_user, get_optional_current_user
from backend.auth.security import REFRESH_TOKEN_COOKIE_NAME, create_access_token, create_refresh_token
from backend.database import get_session
from backend.errors import AppError
from backend.config import Config
from backend.routers import auth as auth_router
from backend.routers import recordings as recordings_router
from backend.routers import tasks as tasks_router
from backend.routers import utg as utg_router
from backend.routers import workspaces as workspaces_router
from backend.services.task_service import TaskService
from backend.services.utg_service_v2 import UTGServiceV2
from backend.session_config import workspace_state_manager

EDGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
)


def reset_workspace_state_manager():
    workspace_state_manager._workspaces.clear()
    workspace_state_manager._recording_leases.clear()
    workspace_state_manager._device_sessions.clear()
    workspace_state_manager._runtime_sessions.clear()


def override_session():
    yield object()


def build_test_app():
    test_app = FastAPI()
    test_app.include_router(auth_router.router)
    test_app.include_router(recordings_router.router)
    test_app.include_router(tasks_router.router)
    test_app.include_router(utg_router.router)
    test_app.include_router(workspaces_router.router)

    @test_app.exception_handler(AppError)
    async def app_error_handler(request, exc):
        _ = request
        return exc.to_response()

    @test_app.exception_handler(404)
    async def not_found_handler(request, exc):
        _ = request, exc
        return JSONResponse(status_code=404, content={"error": "Not found"})

    return test_app


class WorkspacePrincipalIsolationRouteTest(unittest.TestCase):
    def setUp(self):
        reset_workspace_state_manager()
        self.app = build_test_app()
        self.app.dependency_overrides[get_session] = override_session
        self.app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=2,
            username="user-b",
            is_active=True,
            is_superuser=False,
        )

    def tearDown(self):
        self.app.dependency_overrides.clear()
        reset_workspace_state_manager()

    def test_workspace_principal_mismatch_returns_workspace_expired(self):
        workspace = asyncio.run(
            workspace_state_manager.bootstrap_workspace(None, user_id=1, current_view="task-recorder")
        )
        asyncio.run(workspace_state_manager.set_current_recording(workspace.workspace_id, "record/task_a"))

        with TestClient(self.app) as client, \
             patch.object(TaskService, "get_task_info", return_value="task: demo") as task_info_mock, \
             patch.object(UTGServiceV2, "get_utg", return_value={"nodes": [], "edges": []}) as utg_mock:
            headers = {"X-Workspace-Id": workspace.workspace_id}
            for path in ("/api/recordings/current", "/api/task-info", "/api/utg"):
                response = client.get(path, headers=headers)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "WORKSPACE_EXPIRED")

        task_info_mock.assert_not_called()
        utg_mock.assert_not_called()
        self.assertIn(workspace.workspace_id, workspace_state_manager._workspaces)

    def test_bootstrap_principal_mismatch_returns_workspace_expired(self):
        workspace = asyncio.run(
            workspace_state_manager.bootstrap_workspace(None, user_id=1, current_view="task-recorder")
        )

        with TestClient(self.app) as client:
            response = client.post(
                "/api/workspaces/bootstrap",
                json={"workspace_id": workspace.workspace_id, "current_view": "data-editor"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "WORKSPACE_EXPIRED")


class WorkspaceBootstrapAuthRouteTest(unittest.TestCase):
    def setUp(self):
        reset_workspace_state_manager()
        self.app = build_test_app()
        self.app.dependency_overrides[get_session] = override_session

    def tearDown(self):
        self.app.dependency_overrides.clear()
        reset_workspace_state_manager()

    def test_bootstrap_allows_anonymous_request_without_token(self):
        with TestClient(self.app) as client:
            response = client.post("/api/workspaces/bootstrap", json={"current_view": "task-recorder"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["workspace_id"])
        self.assertEqual(body["current_view"], "task-recorder")

    def test_bootstrap_rejects_invalid_bearer_token(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/workspaces/bootstrap",
                json={"current_view": "task-recorder"},
                headers={"Authorization": "Bearer invalid-token"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Could not validate credentials")

    def test_bootstrap_rejects_expired_access_token(self):
        expired_access_token = create_access_token({"sub": "alice"}, expires_delta=timedelta(minutes=-1))

        with TestClient(self.app) as client:
            response = client.post(
                "/api/workspaces/bootstrap",
                json={"current_view": "task-recorder"},
                headers={"Authorization": f"Bearer {expired_access_token}"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "AUTH_EXPIRED")

    def test_bootstrap_captures_client_shortcode_and_ip(self):
        self.app.dependency_overrides[get_optional_current_user] = lambda: SimpleNamespace(
            id=8,
            username="alice",
            is_active=True,
            is_superuser=False,
        )

        with TestClient(self.app, client=("203.0.113.7", 4321)) as client:
            response = client.post(
                "/api/workspaces/bootstrap",
                json={"current_view": "task-recorder"},
                headers={
                    "X-Client-Shortcode": "a7f2",
                    "X-Forwarded-For": "10.23.45.67, 127.0.0.1",
                    "User-Agent": EDGE_USER_AGENT,
                },
            )

        self.assertEqual(response.status_code, 200)
        workspace = workspace_state_manager._workspaces[response.json()["workspace_id"]]
        self.assertEqual(workspace.username, "alice")
        self.assertEqual(workspace.client_shortcode, "A7F2")
        self.assertEqual(workspace.client_ip, "203.0.113.7")
        self.assertEqual(workspace.client_user_agent, EDGE_USER_AGENT)

    def test_extract_client_ip_rejects_invalid_peer_and_ignores_proxy_headers(self):
        request = SimpleNamespace(
            headers={"X-Forwarded-For": "10.23.45.67"},
            client=SimpleNamespace(host="not-an-ip"),
        )

        self.assertIsNone(workspaces_router._extract_client_ip(request))


class LogoutRouteTest(unittest.TestCase):
    def setUp(self):
        reset_workspace_state_manager()
        self.app = build_test_app()
        self.app.dependency_overrides[get_session] = override_session

    def tearDown(self):
        self.app.dependency_overrides.clear()
        reset_workspace_state_manager()

    def test_logout_clears_refresh_cookie_and_releases_workspace(self):
        workspace = asyncio.run(
            workspace_state_manager.bootstrap_workspace(None, user_id=1, current_view="task-recorder")
        )
        access_token = create_access_token({"sub": "alice"})
        fake_user = SimpleNamespace(id=1, username="alice", is_active=True)

        with TestClient(self.app) as client, \
             patch.object(auth_router.user_crud, "get_user_by_username", return_value=fake_user):
            response = client.post(
                "/api/auth/logout",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Workspace-Id": workspace.workspace_id,
                },
                cookies={REFRESH_TOKEN_COOKIE_NAME: "refresh-cookie"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logged out")
        self.assertNotIn(workspace.workspace_id, workspace_state_manager._workspaces)
        self.assertIn(f"{REFRESH_TOKEN_COOKIE_NAME}=", response.headers["set-cookie"])
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_logout_releases_workspace_when_access_token_is_expired_but_refresh_cookie_is_valid(self):
        workspace = asyncio.run(
            workspace_state_manager.bootstrap_workspace(None, user_id=1, current_view="task-recorder")
        )
        expired_access_token = create_access_token({"sub": "alice"}, expires_delta=timedelta(minutes=-1))
        refresh_token = create_refresh_token({"sub": "alice"})
        fake_user = SimpleNamespace(id=1, username="alice", is_active=True)

        with TestClient(self.app) as client, \
             patch.object(auth_router.user_crud, "get_user_by_username", return_value=fake_user):
            response = client.post(
                "/api/auth/logout",
                headers={
                    "Authorization": f"Bearer {expired_access_token}",
                    "X-Workspace-Id": workspace.workspace_id,
                },
                cookies={REFRESH_TOKEN_COOKIE_NAME: refresh_token},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(workspace.workspace_id, workspace_state_manager._workspaces)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_logout_with_invalid_tokens_still_clears_cookie(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/auth/logout",
                headers={"X-Workspace-Id": "workspace-missing"},
                cookies={REFRESH_TOKEN_COOKIE_NAME: "invalid-refresh"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logged out")
        self.assertIn("Max-Age=0", response.headers["set-cookie"])


class WorkspaceActivityRouteTest(unittest.TestCase):
    def setUp(self):
        reset_workspace_state_manager()
        self.app = build_test_app()
        self.app.dependency_overrides[get_session] = override_session
        self.app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=11,
            username="user-a",
            is_active=True,
            is_superuser=False,
        )

    def tearDown(self):
        self.app.dependency_overrides.clear()
        reset_workspace_state_manager()

    def test_activity_heartbeat_updates_owned_workspace(self):
        workspace = asyncio.run(
            workspace_state_manager.bootstrap_workspace(None, user_id=11, current_view="task-recorder")
        )

        with TestClient(self.app, client=("198.51.100.23", 54231)) as client:
            response = client.post(
                f"/api/workspaces/{workspace.workspace_id}/activity",
                headers={
                    "X-Workspace-Id": workspace.workspace_id,
                    "X-Client-Shortcode": "edit2",
                    "X-Forwarded-For": "10.99.88.77, 127.0.0.1",
                    "User-Agent": "Mozilla/5.0 Chrome/136.0.0.0 Safari/537.36",
                },
                json={"current_view": "data-editor"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workspace_id"], workspace.workspace_id)
        self.assertEqual(body["current_view"], "data-editor")
        refreshed = workspace_state_manager._workspaces[workspace.workspace_id]
        self.assertEqual(refreshed.client_shortcode, "EDIT2")
        self.assertEqual(refreshed.client_ip, "198.51.100.23")
        self.assertEqual(refreshed.client_user_agent, "Mozilla/5.0 Chrome/136.0.0.0 Safari/537.36")


class RecordingLockConflictVisibilityRouteTest(unittest.TestCase):
    def setUp(self):
        reset_workspace_state_manager()
        self.app = build_test_app()
        self.app.dependency_overrides[get_session] = override_session

    def tearDown(self):
        self.app.dependency_overrides.clear()
        reset_workspace_state_manager()

    def test_normal_user_sees_masked_ip_and_missing_reason(self):
        workspace_a = asyncio.run(
            workspace_state_manager.bootstrap_workspace(
                None,
                user_id=1,
                username="alice",
                client_shortcode="A7F2",
                client_ip="10.23.45.67",
                client_user_agent=EDGE_USER_AGENT,
                current_view="data-editor",
            )
        )
        workspace_b = asyncio.run(
            workspace_state_manager.bootstrap_workspace(
                None,
                user_id=2,
                username="bob",
                current_view="task-recorder",
            )
        )
        asyncio.run(workspace_state_manager.set_current_recording(workspace_a.workspace_id, "record/task_a"))
        self.app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=2,
            username="bob",
            is_active=True,
            is_superuser=False,
        )

        with tempfile.TemporaryDirectory() as temp_dir, \
             patch.object(Config, "DATA_DIR", Path(temp_dir)), \
             patch.object(recordings_router.recording_crud, "get_recording_by_directory", return_value=None):
            (Path(temp_dir) / "record" / "task_a").mkdir(parents=True)
            with TestClient(self.app) as client:
                response = client.post(
                    "/api/recordings/current/record%2Ftask_a",
                    headers={"X-Workspace-Id": workspace_b.workspace_id},
                )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["code"], "RECORDING_LOCK_CONFLICT")
        self.assertEqual(body["holder_ip_masked"], "10.23.*.*")
        self.assertEqual(body["holder_ip_reason"], "ip_hidden_by_policy")
        self.assertEqual(body["holder_browser_name"], "Edge")
        self.assertEqual(body["holder_browser_version"], "136.0.0.0")
        self.assertEqual(body["holder_os_name"], "Windows")
        self.assertEqual(body["holder_os_version"], "10")
        self.assertNotIn("holder_user_agent", body)
        self.assertNotIn("holder_ip_full", body)

    def test_admin_sees_full_ip_in_conflict_payload(self):
        workspace_a = asyncio.run(
            workspace_state_manager.bootstrap_workspace(
                None,
                user_id=1,
                username="alice",
                client_shortcode="A7F2",
                client_ip="10.23.45.67",
                client_user_agent=EDGE_USER_AGENT,
                current_view="data-editor",
            )
        )
        workspace_b = asyncio.run(
            workspace_state_manager.bootstrap_workspace(
                None,
                user_id=99,
                username="admin",
                current_view="task-recorder",
            )
        )
        asyncio.run(workspace_state_manager.set_current_recording(workspace_a.workspace_id, "record/task_a"))
        self.app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=99,
            username="admin",
            is_active=True,
            is_superuser=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir, \
             patch.object(Config, "DATA_DIR", Path(temp_dir)), \
             patch.object(recordings_router.recording_crud, "get_recording_by_directory", return_value=None):
            (Path(temp_dir) / "record" / "task_a").mkdir(parents=True)
            with TestClient(self.app) as client:
                response = client.post(
                    "/api/recordings/current/record%2Ftask_a",
                    headers={"X-Workspace-Id": workspace_b.workspace_id},
                )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["code"], "RECORDING_LOCK_CONFLICT")
        self.assertEqual(body["holder_ip_full"], "10.23.45.67")
        self.assertEqual(body["holder_ip_masked"], "10.23.*.*")
        self.assertEqual(body["holder_browser_name"], "Edge")
        self.assertEqual(body["holder_browser_version"], "136.0.0.0")
        self.assertEqual(body["holder_os_name"], "Windows")
        self.assertEqual(body["holder_os_version"], "10")
        self.assertEqual(body["holder_user_agent"], EDGE_USER_AGENT)
        self.assertNotEqual(body.get("holder_ip_reason"), "ip_hidden_by_policy")


if __name__ == "__main__":
    unittest.main()
