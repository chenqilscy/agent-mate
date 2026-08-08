"""WB-461 Server work-item tools do not require a local business mirror."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agent import tools


class ServerWorkItemToolTest(unittest.TestCase):
    def tearDown(self) -> None:
        tools.set_work_context(None, None)

    def test_list_and_update_use_server_authority_without_local_rows(self) -> None:
        remote = [{
            "id": "item-server-461", "project_id": "project-server-461",
            "title": "Server 待办", "status": "todo",
        }]
        tools.set_work_context(
            "project-server-461", "owner-server-461", server_token="server-token-461",
        )
        with (
            patch.object(tools.server_client, "list_work_items", return_value=remote) as list_remote,
            patch.object(tools.server_client, "update_work_item", return_value={**remote[0], "status": "doing"}) as update_remote,
            patch.object(tools.db, "list_work_items", side_effect=AssertionError("local mirror must not be read")),
            patch.object(tools.db, "get_work_item", side_effect=AssertionError("local mirror must not be read")),
        ):
            listed = tools._list_work_items_run({})
            updated = tools._set_work_item_status_run({
                "item_id": "item-server-461", "status": "进行中",
            })

        self.assertIn("Server 待办", listed.text)
        self.assertIn("进行中", updated.text)
        list_remote.assert_called()
        update_remote.assert_called_once_with(
            "server-token-461", "project-server-461", "item-server-461", {"status": "doing"},
        )


if __name__ == "__main__":
    unittest.main()
