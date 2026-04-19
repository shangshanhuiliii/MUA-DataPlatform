"""
Recording exception management service.

Scans recording directories on disk and identifies metadata exceptions that
need manual admin repair.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlmodel import Session, select

from ..config import Config
from ..models.recording import Recording
from ..models.task import Task
from ..models.task_assignment import TaskAssignment
from ..models.user import User
from ..utils.file_utils import FileUtils


TASK_ID_PATTERN = re.compile(r"^task_(\d+)(?:_|$)")


def normalize_task_id(value) -> Optional[int]:
    """Normalize task id values read from filenames or task-info.yaml."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def infer_task_id_from_directory_name(directory_name: str) -> Optional[int]:
    """Infer task id from a directory like record/task_1490_xxx."""
    basename = Path(directory_name).name
    match = TASK_ID_PATTERN.match(basename)
    if not match:
        return None
    return normalize_task_id(match.group(1))


def get_recording_directory_name(path: Path) -> str:
    """Convert an on-disk recording path into the stored directory_name form."""
    try:
        return str(path.relative_to(Config.DATA_DIR))
    except ValueError as exc:
        raise ValueError(f"Recording path '{path}' is not under DATA_DIR '{Config.DATA_DIR}'") from exc


def get_recording_path(directory_name: str) -> Path:
    """Resolve a recording directory_name to the actual on-disk path."""
    return Config.DATA_DIR / directory_name


def load_task_info_summary(directory_name: str) -> Dict[str, Optional[object]]:
    """Read task-info.yaml when present and return a compact summary."""
    task_info_path = get_recording_path(directory_name) / "task-info.yaml"
    if not task_info_path.exists():
        return {
            "task_info_exists": False,
            "task_info_task_id": None,
            "task_info_description": None,
        }

    task_info = FileUtils.read_yaml_file(task_info_path) or {}
    return {
        "task_info_exists": True,
        "task_info_task_id": normalize_task_id(task_info.get("id")),
        "task_info_description": task_info.get("description") or None,
    }


def list_recording_directories() -> List[str]:
    """List recording directories from RECORD_DIR as relative directory_name values."""
    if not Config.RECORD_DIR.exists():
        return []

    directory_names = []
    for path in Config.RECORD_DIR.iterdir():
        if path.is_dir():
            directory_names.append(get_recording_directory_name(path))
    return sorted(directory_names)


def get_recording_exception_item(session: Session, directory_name: str) -> Optional[Dict[str, object]]:
    """Return the current exception item for a directory, if it still exists."""
    for item in list_recording_exceptions(session):
        if item["directory_name"] == directory_name:
            return item
    return None


def _matches_keyword(item: Dict[str, object], keyword: Optional[str]) -> bool:
    if not keyword:
        return True

    needle = keyword.strip().lower()
    if not needle:
        return True

    candidates = [
        item.get("directory_name"),
        item.get("task_description"),
        item.get("recorded_by_username"),
        item.get("inferred_task_description"),
        item.get("task_info_description"),
        item.get("exception_type"),
        " ".join(item.get("issues", [])),
    ]
    return any(needle in str(candidate).lower() for candidate in candidates if candidate)


def list_recording_exceptions(
    session: Session,
    keyword: Optional[str] = None,
    exception_type: Optional[str] = None,
) -> List[Dict[str, object]]:
    """Build the admin exception list for recordings on disk."""
    recordings = list(session.exec(select(Recording)).all())
    tasks = {task.id: task for task in session.exec(select(Task)).all()}
    users = {user.id: user for user in session.exec(select(User)).all()}
    assignments = {
        (assignment.task_id, assignment.user_id)
        for assignment in session.exec(select(TaskAssignment)).all()
    }

    recordings_by_directory = {recording.directory_name: recording for recording in recordings}
    items: List[Dict[str, object]] = []

    for directory_name in list_recording_directories():
        task_info_summary = load_task_info_summary(directory_name)
        inferred_task_id = (
            task_info_summary["task_info_task_id"]
            or infer_task_id_from_directory_name(directory_name)
        )
        inferred_task = tasks.get(inferred_task_id) if inferred_task_id else None
        inferred_task_description = (
            inferred_task.description
            if inferred_task is not None
            else task_info_summary["task_info_description"]
        )

        recording = recordings_by_directory.get(directory_name)
        item: Optional[Dict[str, object]] = None

        if recording is None:
            item = {
                "directory_name": directory_name,
                "record_url": f"/{directory_name}",
                "exception_type": "missing_db_record",
                "issues": ["db_missing"],
                "recording_id": None,
                "task_id": None,
                "task_description": None,
                "recorded_by": None,
                "recorded_by_username": None,
                "inferred_task_id": inferred_task_id,
                "inferred_task_description": inferred_task_description,
                **task_info_summary,
            }
        else:
            issues = []
            task = tasks.get(recording.task_id)
            user = users.get(recording.recorded_by)

            if task is None:
                issues.append("task_missing")
            if user is None:
                issues.append("user_missing")
            elif task is not None and not user.is_superuser and (recording.task_id, recording.recorded_by) not in assignments:
                issues.append("user_not_assigned")

            if issues:
                item = {
                    "directory_name": directory_name,
                    "record_url": f"/{directory_name}",
                    "exception_type": "invalid_relationship",
                    "issues": issues,
                    "recording_id": recording.id,
                    "task_id": recording.task_id,
                    "task_description": task.description if task else None,
                    "recorded_by": recording.recorded_by,
                    "recorded_by_username": user.username if user else None,
                    "inferred_task_id": inferred_task_id,
                    "inferred_task_description": inferred_task_description,
                    **task_info_summary,
                }

        if item is None:
            continue
        if exception_type and item["exception_type"] != exception_type:
            continue
        if not _matches_keyword(item, keyword):
            continue

        items.append(item)

    items.sort(key=lambda item: (item["exception_type"] != "missing_db_record", item["directory_name"]))
    return items


def repair_recording_exception(
    session: Session,
    directory_name: str,
    task_id: int,
    recorded_by: int,
    repaired_by: int,
) -> Dict[str, object]:
    """Create or repair a recording row and normalize task assignment if needed."""
    if get_recording_exception_item(session, directory_name) is None:
        raise ValueError("Recording is not an exception item")

    recording_path = get_recording_path(directory_name)
    if not recording_path.exists() or not recording_path.is_dir():
        raise ValueError("Recording directory not found")

    task = session.get(Task, task_id)
    if task is None:
        raise ValueError("Task not found")

    user = session.get(User, recorded_by)
    if user is None:
        raise ValueError("User not found")

    assignment_created = False
    if not user.is_superuser:
        existing_assignment = session.exec(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.user_id == recorded_by,
            )
        ).first()
        if existing_assignment is None:
            session.add(
                TaskAssignment(
                    task_id=task_id,
                    user_id=recorded_by,
                    assigned_by=repaired_by,
                    assigned_at=datetime.utcnow(),
                )
            )
            assignment_created = True

    recording = session.exec(
        select(Recording).where(Recording.directory_name == directory_name)
    ).first()

    action = "updated"
    now = datetime.utcnow()
    if recording is None:
        recording = Recording(
            task_id=task_id,
            recorded_by=recorded_by,
            directory_name=directory_name,
            created_at=now,
            updated_at=now,
        )
        session.add(recording)
        action = "created"
    else:
        recording.task_id = task_id
        recording.recorded_by = recorded_by
        recording.updated_at = now
        session.add(recording)

    session.commit()
    session.refresh(recording)

    return {
        "action": action,
        "assignment_created": assignment_created,
        "recording": recording,
    }
