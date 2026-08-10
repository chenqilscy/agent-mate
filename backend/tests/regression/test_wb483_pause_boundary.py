"""WB-483/WB-484: pause acknowledgement and timeout budget share one safe boundary."""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import server_run_worker  # noqa: E402


class PauseBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_control_loop_requests_pause_without_acknowledging_it(self) -> None:
        gate = asyncio.Event()
        gate.set()
        state = server_run_worker._ControlState(gate=gate)

        async def finish_after_flush(*_args):
            state.terminal = True
            return {"sent": 0, "acked": 0}

        with patch.object(asyncio, "sleep", new=AsyncMock()), patch.object(
            server_run_worker.run_transport, "renew_lease",
            return_value={"commands": [{"id": "pause-1", "command_type": "pause", "payload": {}}]},
        ), patch.object(
            server_run_worker.run_transport, "append_event",
        ) as append, patch.object(
            server_run_worker, "_flush", new=AsyncMock(side_effect=finish_after_flush),
        ):
            await server_run_worker._control_loop(
                run_id="run-1", owner_id="owner-1", device_token="device-token",
                local_session_id="session-1", state=state,
            )

        self.assertTrue(state.pause_requested)
        self.assertTrue(gate.is_set())
        self.assertEqual(["pause-1"], state.pending_pause_commands)
        append.assert_not_called()

    async def test_pause_boundary_freezes_timeout_until_resume(self) -> None:
        gate = asyncio.Event()
        gate.set()
        state = server_run_worker._ControlState(
            gate=gate, pause_requested=True, pending_pause_commands=["pause-1"],
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 0.01

        async def resume_later() -> None:
            await asyncio.sleep(0.05)
            state.paused = False
            gate.set()

        resume = asyncio.create_task(resume_later())
        with patch.object(
            server_run_worker.run_transport, "append_event",
        ) as append, patch.object(
            server_run_worker, "_flush", new=AsyncMock(return_value={"sent": 2, "acked": 2}),
        ):
            async with asyncio.timeout_at(deadline) as timeout_context:
                extended = await server_run_worker._pause_at_boundary(
                    run_id="run-1", owner_id="owner-1", device_token="device-token",
                    state=state, execution_timeout=timeout_context, deadline=deadline,
                )
        await resume

        self.assertIsNotNone(extended)
        self.assertGreater(extended, deadline + 0.03)
        self.assertEqual(
            [
                ("run-1", "run.paused", {"reason": "user_requested"}),
                ("run-1", "command.ack", {"command_id": "pause-1"}),
            ],
            [call.args for call in append.call_args_list],
        )


if __name__ == "__main__":
    unittest.main()
