import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WEB_ROOT = PROJECT_ROOT / "web"
for root in (PROJECT_ROOT, WEB_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from backend.config import Config
from backend.models.batch import Batch
from backend.models.recording import Recording
from backend.models.task import Task
from backend.models.task_assignment import TaskAssignment
from backend.models.user import User
from backend.services import recording_exception_service


class RecordingExceptionServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.record_dir = self.data_dir / "record"
        self.record_dir.mkdir(parents=True, exist_ok=True)

        self.config_patchers = [
            patch.object(Config, "DATA_DIR", self.data_dir),
            patch.object(Config, "RECORD_DIR", self.record_dir),
            patch.object(recording_exception_service.Config, "DATA_DIR", self.data_dir),
            patch.object(recording_exception_service.Config, "RECORD_DIR", self.record_dir),
        ]
        for patcher in self.config_patchers:
            patcher.start()

    def tearDown(self):
        self.session.close()
        self.temp_dir.cleanup()
        for patcher in reversed(self.config_patchers):
            patcher.stop()

    def create_user(self, user_id: int, username: str, is_superuser: bool = False) -> User:
        user = User(
            id=user_id,
            username=username,
            email=f"{username}@example.com",
            password_hash="hash",
            is_superuser=is_superuser,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def create_batch(self, batch_id: int, created_by: int) -> Batch:
        batch = Batch(id=batch_id, name=f"batch-{batch_id}", created_by=created_by)
        self.session.add(batch)
        self.session.commit()
        self.session.refresh(batch)
        return batch

    def create_task(self, task_id: int, created_by: int, description: str = "demo task") -> Task:
        task = Task(
            id=task_id,
            description=description,
            created_by=created_by,
            batch_id=None,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def create_recording_dir(self, directory_name: str, task_info: str = ""):
        record_path = self.data_dir / directory_name
        record_path.mkdir(parents=True, exist_ok=True)
        if task_info:
            (record_path / "task-info.yaml").write_text(task_info, encoding="utf-8")

    def test_list_recording_exceptions_detects_missing_db_record(self):
        admin = self.create_user(1, "admin", is_superuser=True)
        self.create_batch(1, admin.id)
        self.create_task(1490, admin.id, description="咖啡任务")
        self.create_recording_dir(
            "record/task_1490_coffee_0487",
            task_info="id: 1490\ndescription: 咖啡任务\n",
        )

        items = recording_exception_service.list_recording_exceptions(self.session)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["exception_type"], "missing_db_record")
        self.assertEqual(item["directory_name"], "record/task_1490_coffee_0487")
        self.assertEqual(item["inferred_task_id"], 1490)
        self.assertEqual(item["task_info_task_id"], 1490)
        self.assertTrue(item["task_info_exists"])

    def test_list_recording_exceptions_detects_invalid_assignment_relationship(self):
        admin = self.create_user(1, "admin", is_superuser=True)
        recorder = self.create_user(2, "recorder")
        self.create_batch(1, admin.id)
        task = self.create_task(1490, admin.id, description="咖啡任务")
        self.create_recording_dir("record/task_1490_coffee_0487")

        self.session.add(
            Recording(
                task_id=task.id,
                recorded_by=recorder.id,
                directory_name="record/task_1490_coffee_0487",
            )
        )
        self.session.commit()

        items = recording_exception_service.list_recording_exceptions(self.session)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["exception_type"], "invalid_relationship")
        self.assertIn("user_not_assigned", item["issues"])
        self.assertEqual(item["recorded_by_username"], "recorder")

    def test_list_and_repair_respect_custom_record_dir_under_data_dir(self):
        custom_record_dir = self.data_dir / "archive" / "recordings"
        custom_record_dir.mkdir(parents=True, exist_ok=True)
        directory_name = "archive/recordings/task_1490_coffee_0487"
        record_path = custom_record_dir / "task_1490_coffee_0487"
        record_path.mkdir(parents=True, exist_ok=True)
        (record_path / "task-info.yaml").write_text("id: 1490\ndescription: 咖啡任务\n", encoding="utf-8")

        admin = self.create_user(1, "admin", is_superuser=True)
        recorder = self.create_user(2, "recorder")
        self.create_batch(1, admin.id)
        task = self.create_task(1490, admin.id, description="咖啡任务")

        with patch.object(Config, "RECORD_DIR", custom_record_dir), patch.object(
            recording_exception_service.Config, "RECORD_DIR", custom_record_dir
        ):
            items = recording_exception_service.list_recording_exceptions(self.session)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["directory_name"], directory_name)

            result = recording_exception_service.repair_recording_exception(
                self.session,
                directory_name=directory_name,
                task_id=task.id,
                recorded_by=recorder.id,
                repaired_by=admin.id,
            )

        self.assertEqual(result["action"], "created")
        recording = self.session.exec(
            select(Recording).where(Recording.directory_name == directory_name)
        ).first()
        self.assertIsNotNone(recording)
        self.assertEqual(recording.task_id, task.id)
        self.assertEqual(recording.recorded_by, recorder.id)

    def test_validate_paths_rejects_record_dir_outside_data_dir(self):
        external_record_dir = Path(self.temp_dir.name) / "external-recordings"

        with patch.object(Config, "RECORD_DIR", external_record_dir):
            with self.assertRaisesRegex(ValueError, "RECORD_DIR .* must be a subdirectory of DATA_DIR"):
                Config.validate_paths()

    def test_repair_recording_exception_creates_recording_and_assignment(self):
        admin = self.create_user(1, "admin", is_superuser=True)
        recorder = self.create_user(2, "recorder")
        self.create_batch(1, admin.id)
        task = self.create_task(1490, admin.id, description="咖啡任务")
        self.create_recording_dir("record/task_1490_coffee_0487")

        result = recording_exception_service.repair_recording_exception(
            self.session,
            directory_name="record/task_1490_coffee_0487",
            task_id=task.id,
            recorded_by=recorder.id,
            repaired_by=admin.id,
        )

        self.assertEqual(result["action"], "created")
        self.assertTrue(result["assignment_created"])
        recording = result["recording"]
        self.assertEqual(recording.directory_name, "record/task_1490_coffee_0487")
        self.assertEqual(recording.task_id, task.id)
        self.assertEqual(recording.recorded_by, recorder.id)

        assignment = self.session.exec(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task.id,
                TaskAssignment.user_id == recorder.id,
            )
        ).first()
        self.assertIsNotNone(assignment)

    def test_repair_recording_exception_updates_existing_recording(self):
        admin = self.create_user(1, "admin", is_superuser=True)
        wrong_user = self.create_user(2, "wrong-user")
        actual_user = self.create_user(3, "actual-user")
        self.create_batch(1, admin.id)
        old_task = self.create_task(1490, admin.id, description="旧任务")
        new_task = self.create_task(1491, admin.id, description="新任务")
        self.create_recording_dir("record/task_1490_coffee_0487")

        recording = Recording(
            task_id=old_task.id,
            recorded_by=wrong_user.id,
            directory_name="record/task_1490_coffee_0487",
        )
        self.session.add(recording)
        self.session.commit()

        result = recording_exception_service.repair_recording_exception(
            self.session,
            directory_name="record/task_1490_coffee_0487",
            task_id=new_task.id,
            recorded_by=actual_user.id,
            repaired_by=admin.id,
        )

        self.assertEqual(result["action"], "updated")
        refreshed = self.session.exec(
            select(Recording).where(Recording.directory_name == "record/task_1490_coffee_0487")
        ).first()
        self.assertEqual(refreshed.task_id, new_task.id)
        self.assertEqual(refreshed.recorded_by, actual_user.id)

    def test_repair_recording_exception_rejects_non_exception_directory(self):
        admin = self.create_user(1, "admin", is_superuser=True)
        recorder = self.create_user(2, "recorder")
        self.create_batch(1, admin.id)
        task = self.create_task(1490, admin.id, description="咖啡任务")
        self.create_recording_dir("record/task_1490_coffee_0487")

        self.session.add(
            TaskAssignment(
                task_id=task.id,
                user_id=recorder.id,
                assigned_by=admin.id,
            )
        )
        self.session.add(
            Recording(
                task_id=task.id,
                recorded_by=recorder.id,
                directory_name="record/task_1490_coffee_0487",
            )
        )
        self.session.commit()

        with self.assertRaisesRegex(ValueError, "Recording is not an exception item"):
            recording_exception_service.repair_recording_exception(
                self.session,
                directory_name="record/task_1490_coffee_0487",
                task_id=task.id,
                recorded_by=admin.id,
                repaired_by=admin.id,
            )

        refreshed = self.session.exec(
            select(Recording).where(Recording.directory_name == "record/task_1490_coffee_0487")
        ).first()
        self.assertEqual(refreshed.task_id, task.id)
        self.assertEqual(refreshed.recorded_by, recorder.id)


if __name__ == "__main__":
    unittest.main()
