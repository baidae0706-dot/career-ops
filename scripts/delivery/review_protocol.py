"""Persisted session selection and completed, axis-bound child review evidence."""

import json
import re
from pathlib import Path


def validate_session_model(previous, model):
    if previous and previous.get("review_model", "opus") != model:
        raise ValueError("Existing review session uses a different model; preserve it for explicit coordinator reconciliation")


def session_arguments(session_id, transcript):
    return ["--resume" if transcript.is_file() else "--session-id", session_id]


def read_events(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                yield event
        except json.JSONDecodeError:
            continue


def message(event):
    value = event.get("message", {})
    return value if isinstance(value, dict) else {}


def message_blocks(event):
    content = message(event).get("content", [])
    return content if isinstance(content, list) else []


def response_models(records):
    models = set()
    for event in records:
        if event.get("type") == "system" and event.get("subtype") == "init" and event.get("model"):
            models.add(event["model"])
        if event.get("type") == "assistant":
            model = message(event).get("model")
            models.add(model if isinstance(model, str) and model else "UNVERIFIED_ASSISTANT_MODEL")
    return sorted(models)


def skill_receipt(records, skill):
    """Only a successful Skill result or CLI command expansion proves loading."""
    calls = set()
    for event in records:
        content = message(event).get("content", [])
        for block in message_blocks(event):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                data = block.get("input", {})
                if isinstance(data, dict) and data.get("skill", "").lstrip("/") == skill.lstrip("/"):
                    calls.add(block.get("id"))
            if block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                text = content_text(block.get("content"))
                if text and not block.get("is_error") and not any(s in text for s in ("disable-model-invocation", "Unknown skill", "not allowed")):
                    return dict(name=skill, loaded=True, tool_use_id=block["tool_use_id"], mechanism="Skill")
        # CLI expands an explicit slash entry as a user skill message. The full
        # expansion (including the skill base directory) must be in the stream.
        if event.get("type") == "user":
            text = content_text(content)
            if f"<command-name>/{skill.lstrip('/')}</command-name>" in text and "Base directory for this skill:" in text:
                return dict(name=skill, loaded=True, mechanism="explicit-slash-expansion")
    return dict(name=skill, loaded=False)


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def axis_receipts(records, subdir, folder):
    calls, results = {}, {}
    for event in records:
        for block in message_blocks(event):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                data = block.get("input", {})
                axis = {"standards-reviewer": "standards", "spec-reviewer": "spec"}.get(data.get("subagent_type"))
                if axis:
                    calls[block["id"]] = (axis, data)
            elif block.get("type") == "tool_result":
                results[block.get("tool_use_id")] = block
    receipts = {}
    for call_id, (axis, data) in calls.items():
        # The latest attempt for an axis must complete; an old PASS cannot hide a failed retry.
        receipts.pop(axis, None)
        result = results.get(call_id, {})
        text = content_text(result.get("content"))
        match = re.search(r"agentId[^a-zA-Z0-9]{1,8}([a-zA-Z0-9_-]+)", text)
        if result.get("is_error") or data.get("run_in_background") or not match:
            continue
        agent_id = match.group(1)
        transcript = Path(subdir) / f"agent-{agent_id}.jsonl"
        if not transcript.is_file():
            continue
        children = list(read_events(transcript))
        models = response_models(children)
        # A foreground tool result is completion evidence. Parse the returned child report,
        # never reconstruct one from a parent summary or an unrelated transcript.
        try:
            start = text.index("{")
            child, _ = json.JSONDecoder().raw_decode(text[start:])
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(child, dict) or child.get("axis") != axis:
            continue
        raw_name, report_name = f"{axis}-child.txt", f"{axis}-child.json"
        (folder / raw_name).write_text(text, encoding="utf-8")
        (folder / report_name).write_text(json.dumps(child, ensure_ascii=False, indent=2), encoding="utf-8")
        transcript_name = f"{axis}-transcript.jsonl"
        (folder / transcript_name).write_bytes(transcript.read_bytes())
        receipts[axis] = dict(tool_use_id=call_id, agent_id=agent_id, completed=True, models=models,
                              report=report_name, raw_report=raw_name, status=child.get("status"),
                              summary=child.get("summary"), findings=child.get("findings"), transcript=transcript_name)
    return receipts
