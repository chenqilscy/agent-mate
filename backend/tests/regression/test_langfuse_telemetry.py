"""Regression coverage for optional Langfuse instrumentation (WB-230)."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime, telemetry  # noqa: E402
from config import scrubbed_env, settings  # noqa: E402


class _FakeObservation:
    def __init__(self, kwargs: dict, parent: "_FakeObservation | None") -> None:
        self.kwargs = kwargs
        self.parent = parent
        self.updates: list[dict] = []
        self.ended = False

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class _FakeObservationManager:
    def __init__(self, client: "_FakeClient", observation: _FakeObservation) -> None:
        self.client = client
        self.observation = observation

    def __enter__(self) -> _FakeObservation:
        self.client.stack.append(self.observation)
        return self.observation

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.observation.ended = True
        self.client.stack.pop()
        return False


class _FakeAttributeManager:
    def __init__(self, sink: list[dict], kwargs: dict) -> None:
        self.sink = sink
        self.kwargs = kwargs

    def __enter__(self):
        self.sink.append(self.kwargs)
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _FakeClient:
    def __init__(self, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.stack: list[_FakeObservation] = []
        self.observations: list[_FakeObservation] = []
        self.shutdown_called = False

    def start_as_current_observation(self, **kwargs):
        if self.fail_start:
            raise RuntimeError("collector unavailable")
        observation = _FakeObservation(kwargs, self.stack[-1] if self.stack else None)
        self.observations.append(observation)
        return _FakeObservationManager(self, observation)

    def shutdown(self) -> None:
        self.shutdown_called = True


class LangfuseTelemetryTest(unittest.TestCase):
    def _client_patches(self, client: _FakeClient):
        return (
            patch.object(telemetry, "_client", client),
            patch.object(telemetry, "_client_initialized", True),
        )

    def test_default_metadata_only_trace_has_agent_generation_and_tool_hierarchy(self) -> None:
        client = _FakeClient()
        attributes: list[dict] = []
        client_patch, initialized_patch = self._client_patches(client)
        with (
            patch.object(settings, "LANGFUSE_CAPTURE_CONTENT", False),
            client_patch,
            initialized_patch,
            patch.object(
                telemetry,
                "_propagate_attributes",
                side_effect=lambda **kwargs: _FakeAttributeManager(attributes, kwargs),
            ),
        ):
            with telemetry.chat_observation(
                session_id="session-1", user_id="user@example.com", user_text="private prompt",
                project_id="project-1", mode="exec", selected_model="deepseek-chat",
                refs_count=1, skills_count=2, connectors_count=1,
            ) as root:
                with telemetry.generation_observation(
                    name="llm.chat.round-1", model="deepseek-chat",
                    messages=[{"role": "user", "content": "private prompt"}],
                    temperature=0.6, round_number=1,
                ) as generation:
                    generation.update(output="private answer", usage_details={"input": 10, "output": 4})
                with telemetry.tool_observation(
                    name="knowledge_retrieve", arguments={"query": "private query"}, source="builtin",
                ) as tool:
                    tool.update(output="private document")
                root.update(output="private answer")

        self.assertEqual(["agent", "generation", "retriever"], [o.kwargs["as_type"] for o in client.observations])
        root, generation, tool = client.observations
        self.assertIsNone(root.parent)
        self.assertIs(generation.parent, root)
        self.assertIs(tool.parent, root)
        self.assertEqual({"type": "text", "chars": 14}, root.kwargs["input"])
        exported = repr([(o.kwargs, o.updates) for o in client.observations])
        self.assertNotIn("private prompt", exported)
        self.assertNotIn("private answer", exported)
        self.assertNotIn("private query", exported)
        self.assertNotIn("private document", exported)
        self.assertTrue(all(o.ended for o in client.observations))
        self.assertEqual("session-1", attributes[0]["session_id"])
        self.assertNotEqual("user@example.com", attributes[0]["user_id"])

    def test_explicit_content_capture_still_redacts_credentials(self) -> None:
        with patch.object(settings, "LANGFUSE_CAPTURE_CONTENT", True):
            payload = telemetry.safe_payload({
                "api_key": "sk-super-secret-value",
                "access_token": "private-access-token",
                "authorization": "Bearer abc.def.ghi",
                "text": "call with sk-another-secret-value",
                "prompt_tokens": 123,
                "completion_tokens": 45,
            })
        rendered = repr(payload)
        self.assertNotIn("super-secret", rendered)
        self.assertNotIn("abc.def.ghi", rendered)
        self.assertNotIn("another-secret", rendered)
        self.assertIn("REDACTED", rendered)
        self.assertEqual(123, payload["prompt_tokens"])
        self.assertEqual(45, payload["completion_tokens"])

    def test_collector_start_failure_is_a_noop(self) -> None:
        client = _FakeClient(fail_start=True)
        client_patch, initialized_patch = self._client_patches(client)
        with client_patch, initialized_patch:
            with telemetry.observation(as_type="tool", name="demo", input={"value": 1}) as observation:
                self.assertFalse(observation.enabled)

    def test_langfuse_secret_is_removed_from_command_environment(self) -> None:
        with patch.dict(os.environ, {"LANGFUSE_SECRET_KEY": "must-not-leak"}, clear=False):
            self.assertNotIn("LANGFUSE_SECRET_KEY", scrubbed_env())

    def test_shutdown_flushes_initialized_client_without_raising(self) -> None:
        client = _FakeClient()
        client_patch, initialized_patch = self._client_patches(client)
        with client_patch, initialized_patch:
            telemetry.shutdown()
        self.assertTrue(client.shutdown_called)


class RuntimeTelemetryBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_public_run_chat_wraps_existing_sse_generator(self) -> None:
        seen: dict = {}

        @contextmanager
        def fake_chat_observation(**kwargs):
            seen.update(kwargs)
            yield telemetry.Observation()

        async def fake_inner(*args, **kwargs):
            self.assertIsInstance(kwargs["chat_trace"], telemetry.Observation)
            yield "event: done\ndata: {}\n\n"

        session = SimpleNamespace(id="session-1", project_id="project-1")
        user = SimpleNamespace(id="user-1")
        with (
            patch.object(runtime.telemetry, "chat_observation", fake_chat_observation),
            patch.object(runtime, "_run_chat_inner", fake_inner),
        ):
            chunks = [chunk async for chunk in runtime.run_chat(
                session, user, "hello", model="model-1", skills=["web-access"],
            )]

        self.assertEqual(["event: done\ndata: {}\n\n"], chunks)
        self.assertEqual("session-1", seen["session_id"])
        self.assertEqual("exec", seen["mode"])
        self.assertEqual(1, seen["skills_count"])


if __name__ == "__main__":
    unittest.main()
