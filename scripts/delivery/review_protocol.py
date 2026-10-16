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


def parent_events(records):
    """Only this run's initialized parent stream can authorize its review."""
    initialized = next(((index, event) for index, event in enumerate(records)
                        if event.get("type") == "system" and event.get("subtype") == "init"), None)
    if initialized is None:
        return
    start, init = initialized
    session = init.get("session_id")
    if not isinstance(session, str) or not session:
        return
    for index, event in enumerate(records):
        if (index > start and event.get("session_id") == session
                and event.get("parent_tool_use_id") is None and event.get("type") in ("assistant", "user")):
            yield index, event


def skill_receipt(records, skill):
    """Only a successful Skill result or CLI command expansion proves loading."""
    calls, expansion = {}, None
    for index, event in parent_events(records):
        content = message(event).get("content", [])
        for block in message_blocks(event):
            if not isinstance(block, dict):
                continue
            if event.get("type") == "assistant" and block.get("type") == "tool_use" and block.get("name") == "Skill":
                data = block.get("input", {})
                if isinstance(data, dict) and data.get("skill", "").lstrip("/") == skill.lstrip("/"):
                    calls[block.get("id")] = dict(call_event=index, call_message_id=message(event).get("id"),
                                                args=data.get("args"), session_id=event["session_id"])
            if event.get("type") == "user" and block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                text = content_text(block.get("content"))
                if text and not block.get("is_error") and not any(s in text for s in ("disable-model-invocation", "Unknown skill", "not allowed")):
                    return dict(name=skill, loaded=True, tool_use_id=block["tool_use_id"], mechanism="Skill",
                                result_event=index, **calls[block["tool_use_id"]])
        # CLI expands an explicit slash entry as a user skill message. The full
        # expansion (including the skill base directory) must be in the stream.
        if event.get("type") == "user":
            text = content_text(content)
            if f"<command-name>/{skill.lstrip('/')}</command-name>" in text and "Base directory for this skill:" in text:
                expansion = dict(name=skill, loaded=True, mechanism="explicit-slash-expansion")
    return expansion or dict(name=skill, loaded=False)


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def axis_receipts(records, subdir, folder):
    calls, results = {}, {}
    for index, event in parent_events(records):
        for block in message_blocks(event):
            if not isinstance(block, dict):
                continue
            if event.get("type") == "assistant" and block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                data = block.get("input", {})
                axis = {"standards-reviewer": "standards", "spec-reviewer": "spec"}.get(data.get("subagent_type"))
                if axis:
                    calls[block["id"]] = (axis, data, dict(call_event=index, call_message_id=message(event).get("id"),
                                                        session_id=event["session_id"], run_in_background=data.get("run_in_background")))
            elif event.get("type") == "user" and block.get("type") == "tool_result":
                results[block.get("tool_use_id")] = block
    receipts = {}
    for call_id, (axis, data, invocation) in calls.items():
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
                              summary=child.get("summary"), findings=child.get("findings"), transcript=transcript_name, **invocation)
    return receipts
