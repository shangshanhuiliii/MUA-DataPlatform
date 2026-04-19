import asyncio
import queue
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WEB_ROOT = PROJECT_ROOT / "web"
for root in (PROJECT_ROOT, WEB_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from droidbot.constant import ViewsMode
from backend.services.recording_worker_thread import RecordingWorkerThread
from backend.services.task_record_service import TaskRecordService


class FakeState:
    def __init__(self, name: str):
        self.foreground_activity = name


class FakeUTGService:
    def __init__(self):
        self.calls = []
        self.node_sync_calls = []

    def add_transition_sync(self, event, from_state, to_state, dataset):
        self.calls.append((event, from_state, to_state, dataset))
        return {"success": True}

    def sync_state_node_sync(self, state, dataset):
        self.node_sync_calls.append((state, dataset))
        return {"success": True, "state": getattr(state, "foreground_activity", None)}


class FakeDevice:
    def __init__(self, states=None):
        self.states = list(states or [])
        self.sent_events = []

    def get_current_state(self):
        if not self.states:
            raise AssertionError("No fake states left")
        return self.states.pop(0)

    def send_event(self, event):
        self.sent_events.append(event)


class FakeSession:
    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self.created_time = 1
        self.pause_calls = 0
        self.resume_calls = 0

    def is_alive(self):
        return True

    async def pause(self):
        self.pause_calls += 1

    async def resume(self):
        self.resume_calls += 1


def build_worker():
    response_queue = queue.Queue()
    worker = RecordingWorkerThread(
        device_serial="device-1",
        output_dir="out",
        views_mode=ViewsMode.XML_MODE,
        event_queue=queue.Queue(),
        response_queue=response_queue,
        dataset="dataset-1",
    )
    return worker, response_queue


def drain_queue(q):
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            return items


class RecordingWorkerThreadPauseTest(unittest.TestCase):
    def test_first_recorded_event_syncs_current_state_before_transition(self):
        worker, response_queue = build_worker()
        utg_service = FakeUTGService()
        start_state = FakeState("segment-start")

        worker.device = FakeDevice(states=[start_state])
        worker.utg_service = utg_service
        first_event = object()
        worker._create_input_event = lambda event_data: first_event

        worker._handle_event({"type": "touch", "x": 5, "y": 6})

        self.assertEqual(worker.event_count, 1)
        self.assertEqual(worker.device.sent_events, [first_event])
        self.assertEqual(utg_service.calls, [])
        self.assertEqual(utg_service.node_sync_calls, [(start_state, "dataset-1")])
        self.assertIs(worker.last_state, start_state)
        self.assertIs(worker.last_event, first_event)

        responses = drain_queue(response_queue)
        self.assertEqual(responses[-1]["type"], "event_completed")
        self.assertTrue(responses[-1]["recorded"])

    def test_pause_flushes_last_recorded_transition(self):
        worker, response_queue = build_worker()
        utg_service = FakeUTGService()
        pause_state = FakeState("paused-screen")

        worker.device = FakeDevice(states=[pause_state])
        worker.utg_service = utg_service
        worker.last_state = FakeState("before-pause")
        worker.last_event = object()

        worker._handle_pause()

        self.assertTrue(worker.is_paused)
        self.assertIsNone(worker.last_state)
        self.assertIsNone(worker.last_event)
        self.assertEqual(len(utg_service.calls), 1)
        recorded_event, from_state, to_state, dataset = utg_service.calls[0]
        self.assertIsNotNone(recorded_event)
        self.assertEqual(from_state.foreground_activity, "before-pause")
        self.assertIs(to_state, pause_state)
        self.assertEqual(dataset, "dataset-1")

        responses = drain_queue(response_queue)
        self.assertEqual(responses[-1]["type"], "recording_paused")

    def test_paused_action_executes_without_recording(self):
        worker, response_queue = build_worker()
        worker.is_paused = True
        worker.device = FakeDevice()
        worker.utg_service = FakeUTGService()

        fake_input_event = object()
        worker._create_input_event = lambda event_data: fake_input_event

        worker._handle_event({"type": "touch", "x": 10, "y": 20})

        self.assertEqual(worker.device.sent_events, [fake_input_event])
        self.assertEqual(worker.event_count, 0)
        self.assertIsNone(worker.last_state)
        self.assertIsNone(worker.last_event)
        self.assertEqual(worker.utg_service.calls, [])
        self.assertEqual(worker.utg_service.node_sync_calls, [])

        responses = drain_queue(response_queue)
        self.assertEqual(responses[-1]["type"], "event_completed")
        self.assertFalse(responses[-1]["recorded"])
        self.assertEqual(responses[-1]["recording_state"], "paused")

    def test_resume_starts_new_recording_segment(self):
        worker, response_queue = build_worker()
        utg_service = FakeUTGService()
        state_after_pause = FakeState("after-pause")
        resumed_start_state = FakeState("resumed-start")
        resumed_end_state = FakeState("resumed-end")

        worker.device = FakeDevice(states=[state_after_pause, resumed_start_state, resumed_end_state])
        worker.utg_service = utg_service

        pre_pause_event = object()
        worker.last_state = FakeState("before-pause")
        worker.last_event = pre_pause_event

        worker._handle_pause()

        paused_event = object()
        worker._create_input_event = lambda event_data: paused_event
        worker._handle_event({"type": "touch", "x": 1, "y": 1})

        worker._handle_resume()

        resumed_event = object()
        worker._create_input_event = lambda event_data: resumed_event
        worker._handle_event({"type": "touch", "x": 2, "y": 2})
        worker._handle_shutdown()

        self.assertEqual(worker.event_count, 1)
        self.assertEqual(worker.device.sent_events, [paused_event, resumed_event])
        self.assertEqual(len(utg_service.calls), 2)
        self.assertEqual(utg_service.node_sync_calls, [(resumed_start_state, "dataset-1")])
        self.assertIs(utg_service.calls[0][0], pre_pause_event)
        self.assertEqual(utg_service.calls[0][1].foreground_activity, "before-pause")
        self.assertIs(utg_service.calls[0][2], state_after_pause)
        self.assertEqual(utg_service.calls[0][3], "dataset-1")
        self.assertIs(utg_service.calls[1][0], resumed_event)
        self.assertIs(utg_service.calls[1][1], resumed_start_state)
        self.assertIs(utg_service.calls[1][2], resumed_end_state)
        self.assertEqual(utg_service.calls[1][3], "dataset-1")

        responses = drain_queue(response_queue)
        self.assertEqual(
            [item["type"] for item in responses],
            ["recording_paused", "event_completed", "recording_resumed", "event_completed"],
        )
        self.assertFalse(responses[1]["recorded"])
        self.assertTrue(responses[3]["recorded"])


class TaskRecordServicePauseRoutingTest(unittest.TestCase):
    def test_service_routes_pause_and_resume_messages_to_session(self):
        service = TaskRecordService()
        session = FakeSession(device_serial="device-1")
        service.recording_sessions = {"session-1": session}

        asyncio.run(service.handle_client_message("device-1", {"type": "pause_recording"}))
        asyncio.run(service.handle_client_message("device-1", {"type": "resume_recording"}))

        self.assertEqual(session.pause_calls, 1)
        self.assertEqual(session.resume_calls, 1)


if __name__ == "__main__":
    unittest.main()
