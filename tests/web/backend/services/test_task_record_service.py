import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WEB_ROOT = PROJECT_ROOT / "web"
for root in (PROJECT_ROOT, WEB_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from droidbot.constant import ViewsMode
from backend.config import Config
from backend.crud import recording as recording_crud
from backend.routers import recordings as recording_router
from backend.schemas.recording import RecordingCreate
from backend.services import task_record_service as task_record_service


class FakeCrudSession:
    def __init__(self, commit_error=None):
        self.commit_error = commit_error
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.refresh_calls = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, obj):
        self.refresh_calls += 1


class FakeRecordingSession:
    instances = []

    def __init__(
        self,
        device_serial,
        output_dir,
        dataset,
        user_task_id=None,
        views_mode=ViewsMode.XML_MODE,
        use_image_state=False,
        recording_mode="new_task",
        service_manager=None,
        creator_user_id=None,
    ):
        self.device_serial = device_serial
        self.output_dir = output_dir
        self.dataset = dataset
        self.user_task_id = user_task_id
        self.views_mode = views_mode
        self.use_image_state = use_image_state
        self.recording_mode = recording_mode
        self.service_manager = service_manager
        self.creator_user_id = creator_user_id
        self.session_id = f"session-{len(self.__class__.instances) + 1}"
        self.__class__.instances.append(self)

    def start(self):
        return True

    def is_alive(self):
        return False


class DummyRecordingWorkerThread:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.event_count = 0

    def is_alive(self):
        return False


class DummyAliveRecordingWorkerThread:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.event_count = 0
        self._alive = True

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self._alive = False


class EnsureRecordingTest(unittest.TestCase):
    def test_returns_existing_recording_without_creating(self):
        existing = SimpleNamespace(id=1, directory_name="record/task_1_demo")
        session = FakeCrudSession()

        with patch.object(recording_crud, "get_recording_by_directory", return_value=existing):
            recording, created = recording_crud.ensure_recording(
                session,
                task_id=1,
                directory_name="record/task_1_demo",
                recorded_by=2,
            )

        self.assertIs(recording, existing)
        self.assertFalse(created)
        self.assertEqual(session.added, [])
        self.assertEqual(session.commit_calls, 0)

    def test_recovers_existing_recording_after_integrity_error(self):
        existing = SimpleNamespace(id=2, directory_name="record/task_2_demo")
        session = FakeCrudSession(
            commit_error=IntegrityError(
                "insert into recordings",
                {"directory_name": existing.directory_name},
                Exception("duplicate"),
            )
        )

        with patch.object(recording_crud, "get_recording_by_directory", side_effect=[None, existing]):
            recording, created = recording_crud.ensure_recording(
                session,
                task_id=2,
                directory_name=existing.directory_name,
                recorded_by=3,
            )

        self.assertIs(recording, existing)
        self.assertFalse(created)
        self.assertEqual(session.commit_calls, 1)
        self.assertEqual(session.rollback_calls, 1)
        self.assertEqual(session.refresh_calls, 0)


class RecordingCreateRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_existing_recording_returns_200_and_existing_metadata(self):
        now = datetime.utcnow()
        existing = SimpleNamespace(
            id=9,
            task_id=12,
            directory_name="record/task_12_demo",
            recorded_by=33,
            created_at=now,
            updated_at=now,
        )
        current_user = SimpleNamespace(id=7, username="current-user", is_superuser=True)
        response = Response()

        with patch.object(recording_router.recording_crud, "get_recording_by_directory", return_value=existing), \
             patch.object(recording_router.recording_crud, "get_task_description", return_value="existing task"), \
             patch.object(recording_router.recording_crud, "get_username", return_value="existing-recorder"):
            result = await recording_router.create_recording(
                request=RecordingCreate(task_id=12, directory_name=existing.directory_name),
                response=response,
                current_user=current_user,
                session=object(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(result.task_description, "existing task")
        self.assertEqual(result.recorded_by, 33)
        self.assertEqual(result.recorded_by_username, "existing-recorder")

    async def test_existing_other_users_recording_is_forbidden_for_normal_user(self):
        now = datetime.utcnow()
        existing = SimpleNamespace(
            id=9,
            task_id=88,
            directory_name="record/task_88_demo",
            recorded_by=99,
            created_at=now,
            updated_at=now,
        )
        current_user = SimpleNamespace(id=7, username="current-user", is_superuser=False)
        response = Response()

        with patch.object(recording_router.recording_crud, "get_recording_by_directory", return_value=existing), \
             patch.object(recording_router.recording_crud, "ensure_recording") as ensure_mock:
            with self.assertRaises(HTTPException) as ctx:
                await recording_router.create_recording(
                    request=RecordingCreate(task_id=12, directory_name=existing.directory_name),
                    response=response,
                    current_user=current_user,
                    session=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        ensure_mock.assert_not_called()

    async def test_existing_other_users_recording_is_allowed_for_superuser(self):
        now = datetime.utcnow()
        existing = SimpleNamespace(
            id=9,
            task_id=88,
            directory_name="record/task_88_demo",
            recorded_by=99,
            created_at=now,
            updated_at=now,
        )
        current_user = SimpleNamespace(id=1, username="admin", is_superuser=True)
        response = Response()

        with patch.object(recording_router.recording_crud, "get_recording_by_directory", return_value=existing), \
             patch.object(recording_router.recording_crud, "get_task_description", return_value="owner task"), \
             patch.object(recording_router.recording_crud, "get_username", return_value="owner-user"):
            result = await recording_router.create_recording(
                request=RecordingCreate(task_id=12, directory_name=existing.directory_name),
                response=response,
                current_user=current_user,
                session=object(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(result.task_id, 88)
        self.assertEqual(result.recorded_by, 99)
        self.assertEqual(result.recorded_by_username, "owner-user")


class TaskRecordServiceStartRecordingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeRecordingSession.instances = []

    async def test_start_recording_with_auth_token_sets_creator(self):
        service = task_record_service.TaskRecordService()
        creator = {"id": 18, "username": "alice", "is_superuser": False}
        data_dir = Path("/tmp/data-root")
        message = {
            "type": "start_recording",
            "task_id": "1490",
            "recording_mode": "new_task",
            "views_mode": "xml_mode",
            "use_image_state": False,
            "auth_token": "jwt-token",
            "workspace_id": "workspace-1",
            "device_session_id": "device-session-1",
            "_creator": creator,
        }

        with patch.object(Config, "DATA_DIR", data_dir), \
             patch.object(task_record_service, "resolve_recording_creator_from_token", return_value=creator) as resolve_mock, \
             patch.object(task_record_service, "validate_recording_creator_access") as validate_mock, \
             patch.object(task_record_service, "RecordingSession", FakeRecordingSession), \
             patch.object(task_record_service.workspace_state_manager, "create_runtime_session", new=AsyncMock()) as create_runtime_mock, \
             patch.object(task_record_service, "update_task_status"), \
             patch.object(service, "_generate_output_dir", return_value=str(data_dir / "custom-recordings" / "task_1490_demo")) as output_dir_mock:
            session_id = await service.start_recording("device-1", message)

        self.assertEqual(session_id, "session-1")
        self.assertEqual(len(FakeRecordingSession.instances), 1)
        created_session = FakeRecordingSession.instances[0]
        self.assertEqual(created_session.creator_user_id, 18)
        self.assertEqual(created_session.user_task_id, "1490")
        self.assertEqual(created_session.dataset, "custom-recordings/task_1490_demo")
        create_runtime_mock.assert_awaited_once()
        resolve_mock.assert_not_called()
        validate_mock.assert_called_once_with(1490, creator)
        output_dir_mock.assert_called_once_with("1490")

    async def test_start_recording_without_auth_token_fails_fast(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        message = {
            "type": "start_recording",
            "task_id": "1490",
            "recording_mode": "new_task",
            "views_mode": "xml_mode",
            "workspace_id": "workspace-1",
            "device_session_id": "device-session-1",
        }

        with patch.object(task_record_service, "resolve_recording_creator_from_token") as resolve_mock, \
             patch.object(task_record_service, "validate_recording_creator_access") as validate_mock, \
             patch.object(task_record_service, "RecordingSession", FakeRecordingSession), \
             patch.object(task_record_service, "update_task_status"), \
             patch.object(service, "_generate_output_dir") as output_dir_mock:
            session_id = await service.start_recording("device-1", message)

        self.assertIsNone(session_id)
        self.assertEqual(FakeRecordingSession.instances, [])
        resolve_mock.assert_not_called()
        validate_mock.assert_not_called()
        output_dir_mock.assert_not_called()
        service.broadcast_to_device_clients.assert_awaited_once()
        args, _ = service.broadcast_to_device_clients.await_args
        self.assertEqual(args[1]["type"], "recording_error")
        self.assertEqual(
            args[1]["message"],
            "Authentication required for new task recording. Please refresh and log in again."
        )

    async def test_invalid_auth_token_reports_recording_error(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        message = {
            "type": "start_recording",
            "task_id": "1490",
            "recording_mode": "new_task",
            "auth_token": "bad-token",
            "workspace_id": "workspace-1",
            "device_session_id": "device-session-1",
        }

        with patch.object(task_record_service, "resolve_recording_creator_from_token", side_effect=ValueError("Invalid auth token")), \
             patch.object(task_record_service, "RecordingSession") as session_cls, \
             patch.object(service, "_generate_output_dir") as output_dir_mock:
            session_id = await service.start_recording("device-1", message)

        self.assertIsNone(session_id)
        session_cls.assert_not_called()
        service.broadcast_to_device_clients.assert_awaited_once()
        args, _ = service.broadcast_to_device_clients.await_args
        self.assertEqual(args[1]["type"], "recording_error")
        self.assertEqual(args[1]["message"], "Invalid auth token")
        output_dir_mock.assert_not_called()

    async def test_invalid_task_id_does_not_create_output_dir(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        message = {
            "type": "start_recording",
            "task_id": "bad-task-id",
            "recording_mode": "new_task",
            "auth_token": "jwt-token",
            "workspace_id": "workspace-1",
            "device_session_id": "device-session-1",
        }

        with patch.object(task_record_service, "RecordingSession") as session_cls, \
             patch.object(service, "_generate_output_dir") as output_dir_mock:
            session_id = await service.start_recording("device-1", message)

        self.assertIsNone(session_id)
        session_cls.assert_not_called()
        output_dir_mock.assert_not_called()
        args, _ = service.broadcast_to_device_clients.await_args
        self.assertEqual(args[1]["message"], "Invalid task ID for authenticated recording")

    async def test_forbidden_task_does_not_create_output_dir(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        creator = {"id": 18, "username": "alice", "is_superuser": False}
        message = {
            "type": "start_recording",
            "task_id": "1490",
            "recording_mode": "new_task",
            "auth_token": "jwt-token",
            "workspace_id": "workspace-1",
            "device_session_id": "device-session-1",
        }

        with patch.object(task_record_service, "resolve_recording_creator_from_token", return_value=creator), \
             patch.object(task_record_service, "validate_recording_creator_access", side_effect=ValueError("You don't have access to this task")), \
             patch.object(task_record_service, "RecordingSession") as session_cls, \
             patch.object(service, "_generate_output_dir") as output_dir_mock:
            session_id = await service.start_recording("device-1", message)

        self.assertIsNone(session_id)
        session_cls.assert_not_called()
        output_dir_mock.assert_not_called()
        args, _ = service.broadcast_to_device_clients.await_args
        self.assertEqual(args[1]["message"], "You don't have access to this task")


class RecordingSessionForwardingTest(unittest.IsolatedAsyncioTestCase):
    async def test_forward_recording_ready_persists_metadata_when_creator_is_known(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        service._ensure_recording_entry = AsyncMock()
        runtime_state_mock = AsyncMock()

        with patch.object(task_record_service, "RecordingWorkerThread", DummyRecordingWorkerThread), \
             patch.object(task_record_service.workspace_state_manager, "set_runtime_state", new=runtime_state_mock):
            session = task_record_service.RecordingSession(
                device_serial="device-1",
                output_dir="/tmp/out",
                dataset="record/task_1490_demo",
                user_task_id="1490",
                views_mode=ViewsMode.XML_MODE,
                use_image_state=False,
                recording_mode="new_task",
                service_manager=service,
                creator_user_id=22,
            )

            await session._forward_recording_ready({"timestamp": 123}, success=True)

        service._ensure_recording_entry.assert_awaited_once_with(
            task_id=1490,
            directory_name="record/task_1490_demo",
            recorded_by=22,
        )
        service.broadcast_to_device_clients.assert_awaited_once()
        args, _ = service.broadcast_to_device_clients.await_args
        self.assertEqual(args[1]["type"], "recording_ready")
        self.assertEqual(args[1]["dataset"], "record/task_1490_demo")

    async def test_forward_recording_ready_stops_after_metadata_failure(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        service._ensure_recording_entry = AsyncMock(side_effect=RuntimeError("db down"))
        release_runtime_mock = AsyncMock()

        with patch.object(task_record_service, "RecordingWorkerThread", DummyAliveRecordingWorkerThread), \
             patch.object(task_record_service.workspace_state_manager, "release_runtime_session", new=release_runtime_mock), \
             patch.object(task_record_service, "update_task_status") as update_status_mock:
            session = task_record_service.RecordingSession(
                device_serial="device-1",
                output_dir="/tmp/out",
                dataset="record/task_1490_demo",
                user_task_id="1490",
                views_mode=ViewsMode.XML_MODE,
                use_image_state=False,
                recording_mode="new_task",
                service_manager=service,
                creator_user_id=22,
            )

            service.recording_sessions[session.session_id] = session
            await session._forward_recording_ready({"timestamp": 123}, success=True)

        service._ensure_recording_entry.assert_awaited_once()
        service.broadcast_to_device_clients.assert_awaited_once()
        args, _ = service.broadcast_to_device_clients.await_args
        self.assertEqual(args[1]["type"], "recording_error")
        self.assertNotIn(session.session_id, service.recording_sessions)
        update_status_mock.assert_called_once_with(1490, "pending")


class TaskRecordServiceLoggingTest(unittest.TestCase):
    def test_sanitize_message_for_logging_redacts_tokens(self):
        service = task_record_service.TaskRecordService()
        original = {
            "type": "start_recording",
            "auth_token": "abc",
            "token": "def",
            "Authorization": "ghi",
        }

        sanitized = service._sanitize_message_for_logging(original)

        self.assertEqual(sanitized["auth_token"], "<redacted>")
        self.assertEqual(sanitized["token"], "<redacted>")
        self.assertEqual(sanitized["Authorization"], "<redacted>")
        self.assertEqual(original["auth_token"], "abc")


class RecordingStopSemanticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_recording_session_stop_does_not_complete_task_on_disconnect(self):
        service = task_record_service.TaskRecordService()

        with patch.object(task_record_service, "RecordingWorkerThread", DummyAliveRecordingWorkerThread), \
             patch.object(task_record_service, "update_task_status") as update_status_mock:
            session = task_record_service.RecordingSession(
                device_serial="device-1",
                output_dir="/tmp/out",
                dataset="record/task_1490_demo",
                user_task_id="1490",
                views_mode=ViewsMode.XML_MODE,
                use_image_state=False,
                recording_mode="new_task",
                service_manager=service,
                creator_user_id=22,
            )

            await session.stop(reason=task_record_service.STOP_REASON_DISCONNECT)

        update_status_mock.assert_not_called()

    async def test_stop_recording_marks_task_completed_only_for_user_stop(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        target_session = SimpleNamespace(
            session_id="session-1",
            device_serial="device-1",
            recording_mode="new_task",
            user_task_id="1490",
            stop=AsyncMock(return_value=7),
        )
        service.recording_sessions[target_session.session_id] = target_session

        with patch.object(task_record_service.workspace_state_manager, "set_runtime_state", new=AsyncMock()), \
             patch.object(task_record_service.workspace_state_manager, "release_runtime_session", new=AsyncMock()), \
             patch.object(task_record_service, "update_task_status") as update_status_mock:
            action_count = await service.stop_recording("device-1", {"session_id": target_session.session_id})

        self.assertEqual(action_count, 7)
        target_session.stop.assert_awaited_once_with(reason=task_record_service.STOP_REASON_USER)
        update_status_mock.assert_called_once_with(1490, "completed")

    async def test_disconnect_client_does_not_mark_task_completed(self):
        service = task_record_service.TaskRecordService()
        websocket = object()

        with patch.object(task_record_service, "RecordingWorkerThread", DummyAliveRecordingWorkerThread), \
             patch.object(task_record_service.workspace_state_manager, "release_device_session", new=AsyncMock()), \
             patch.object(task_record_service, "update_task_status") as update_status_mock:
            session = task_record_service.RecordingSession(
                device_serial="device-1",
                output_dir="/tmp/out",
                dataset="record/task_1490_demo",
                user_task_id="1490",
                views_mode=ViewsMode.XML_MODE,
                use_image_state=False,
                recording_mode="new_task",
                service_manager=service,
                creator_user_id=22,
            )
            service.recording_sessions[session.session_id] = session
            service.connections["device-1"] = {websocket}
            service.connection_clients[id(websocket)] = {
                "client_id": "client-1",
                "device_session_id": "device-session-1",
            }

            await service.disconnect_client("device-1", websocket)

        update_status_mock.assert_not_called()

    async def test_runtime_expiry_probe_does_not_mark_task_completed(self):
        service = task_record_service.TaskRecordService()
        service.broadcast_to_device_clients = AsyncMock()
        target_session = SimpleNamespace(
            session_id="session-1",
            device_serial="device-1",
            recording_mode="new_task",
            user_task_id="1490",
            stop=AsyncMock(return_value=7),
        )
        service.recording_sessions[target_session.session_id] = target_session

        with patch.object(
            task_record_service.workspace_state_manager,
            "require_runtime_session",
            new=AsyncMock(
                side_effect=task_record_service.app_error(
                    410,
                    "RECORDING_RUNTIME_EXPIRED",
                    "Recording runtime expired",
                )
            ),
        ), \
            patch.object(task_record_service.workspace_state_manager, "set_runtime_state", new=AsyncMock()), \
            patch.object(task_record_service.workspace_state_manager, "release_runtime_session", new=AsyncMock()), \
            patch.object(task_record_service, "update_task_status") as update_status_mock:
            is_alive = await service._ensure_runtime_alive_for_device("device-1")

        self.assertFalse(is_alive)
        target_session.stop.assert_awaited_once_with(reason=task_record_service.STOP_REASON_EXPIRED_CLEANUP)
        update_status_mock.assert_not_called()
        self.assertGreaterEqual(service.broadcast_to_device_clients.await_count, 2)
        first_call = service.broadcast_to_device_clients.await_args_list[0]
        self.assertEqual(first_call.args[0], "device-1")
        self.assertEqual(first_call.args[1]["type"], "session_event")
        self.assertEqual(first_call.args[1]["scope"], "runtime")
        self.assertEqual(first_call.args[1]["code"], "RECORDING_RUNTIME_EXPIRED")


if __name__ == "__main__":
    unittest.main()
