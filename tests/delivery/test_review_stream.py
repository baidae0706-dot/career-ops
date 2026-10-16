"""Real stream parsing tolerates non-message JSON without inventing evidence."""
import json
import tempfile
import unittest
from pathlib import Path

from review_protocol import read_events, response_models, axis_receipts, skill_receipt


class StreamTests(unittest.TestCase):
    def test_unknown_shapes_preserve_changes_required_but_never_prove_a_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stream = root / "stream.jsonl"
            records = [False, None, [], "text", {"type": "system", "message": "quota"},
                       {"type": "assistant", "message": "unknown"},
                       {"type": "result", "structured_output": {"verdict": "CHANGES_REQUIRED"}}]
            stream.write_text("\n".join(map(json.dumps, records)) + '\n{"truncated":', encoding="utf-8")
            events = list(read_events(stream))
            self.assertEqual(events[-1]["structured_output"]["verdict"], "CHANGES_REQUIRED")
            self.assertEqual(response_models(events), ["UNVERIFIED_ASSISTANT_MODEL"])
            self.assertEqual(axis_receipts(events, root, root), {})

    def test_every_assistant_model_must_be_known(self):
        records = [{"type": "system", "subtype": "init", "model": "claude-opus-5-5"},
                   {"type": "assistant", "message": {"model": "claude-opus-5-5"}},
                   {"type": "assistant", "message": {}}]
        self.assertEqual(response_models(records), ["UNVERIFIED_ASSISTANT_MODEL", "claude-opus-5-5"])

    def test_skill_name_in_prompt_is_not_successful_skill_loading(self):
        prompt = {"type":"user","message":{"content":"Please use /matt-code-review"}}
        call = {"type":"assistant","message":{"content":[{"type":"tool_use","id":"skill-call","name":"Skill","input":{"skill":"matt-code-review"}}]}}
        refused = {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"skill-call","is_error":True,"content":"disable-model-invocation"}]}}
        passed = {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"skill-call","content":"Base directory for this skill: /skills/matt-code-review\nTwo independent axes"}]}}
        init = dict(type="system", subtype="init", session_id="current")
        for event in (prompt, call, refused, passed):
            event["session_id"] = "current"
        self.assertFalse(skill_receipt([prompt], "matt-code-review")["loaded"])
        self.assertFalse(skill_receipt([init,prompt,call,refused], "matt-code-review")["loaded"])
        self.assertTrue(skill_receipt([init,prompt,call,passed], "matt-code-review")["loaded"])


if __name__ == "__main__":
    unittest.main()
