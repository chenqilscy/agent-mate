"""Hermetic regression embedding policy (WB-360)."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import mem_embed  # noqa: E402


class EmbeddingDownloadPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_model = mem_embed._model
        self.old_unavailable = mem_embed._local_unavailable
        mem_embed._model = None
        mem_embed._local_unavailable = False

    def tearDown(self) -> None:
        mem_embed._model = self.old_model
        mem_embed._local_unavailable = self.old_unavailable

    def test_disabled_policy_never_constructs_fastembed(self) -> None:
        fake = types.ModuleType("fastembed")

        class MustNotConstruct:
            def __init__(self, *args, **kwargs) -> None:
                raise AssertionError("offline regression attempted an embedding model download")

        fake.TextEmbedding = MustNotConstruct
        with (
            patch.dict("os.environ", {"AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD": "1"}),
            patch.dict(sys.modules, {"fastembed": fake}),
        ):
            self.assertIsNone(mem_embed._local_model())
            self.assertFalse(mem_embed.local_available())

    def test_policy_is_explicit_and_does_not_poison_future_runtime(self) -> None:
        sentinel = object()
        with patch.dict("os.environ", {"AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD": "1"}):
            mem_embed._model = sentinel
            self.assertIsNone(mem_embed._local_model())
        with patch.dict("os.environ", {"AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD": "0"}):
            self.assertIs(sentinel, mem_embed._local_model())


if __name__ == "__main__":
    unittest.main()
