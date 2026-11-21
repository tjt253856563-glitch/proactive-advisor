"""Worker for loopback model requests. The parent owns timeout and cancellation."""

import http.client
import json
import sys


def object_schema(fields, required):
    return {"type": "object", "properties": fields, "required": required, "additionalProperties": False}


def response_schema(context):
    phase = context["phase"]
    string = {"type": "string", "maxLength": 400}
    number = {"type": "integer"}
    strings = {"type": "array", "items": string, "maxItems": 12}
    if phase == "plan":
        ids = list(context["policy"]["checks"])
        task = object_schema({
            "id": string, "title": string, "depends": strings, "priority": number,
            "checks": {"type": "array", "items": {"enum": ids} if ids else string, "maxItems": 12},
        }, ["id", "title", "depends", "checks"])
        finding = object_schema({name: string for name in ("tag", "issue", "impact", "verification")},
                                ["tag", "issue", "impact", "verification"])
        return object_schema({
            "level": {"enum": [0, 1, 2, 3]}, "goal": string, "constraints": strings, "answer": string,
            "tasks": {"type": "array", "items": task, "maxItems": 6},
            "review": {"type": "array", "items": finding, "maxItems": 3},
        }, ["level", "goal", "tasks"])

    def action(verb, fields, optional=()):
        return object_schema(
            {"action": {"const": verb}, **fields}, ["action", *(key for key in fields if key not in optional)],
        )

    actions = [action("finish", {"summary": string})]
    choice = context["policy"]["editable"]
    if choice:
        fields = {"path": {"enum": choice}, "old": {"type": ["string", "null"]}, "new": {"type": "string"}}
        if phase == "repair":
            fields.update({
                "tag": {"enum": ["GAP", "LEAP", "ASSUME", "CONFLICT", "UNKNOWN", "OPINION"]},
                "root_cause": string, "basis": string,
                "experience": {"type": ["integer", "null"]},
            })
        actions.append(action("edit", fields, optional=("experience",)))
    if phase == "work":
        for option, verb, key in (("next_reads", "read", "path"), ("next_checks", "check", "id")):
            if context.get(option):
                actions.append(action(verb, {key: {"enum": context[option]}}))
        actions.append(action("block", {"summary": string}))
    return {"oneOf": actions}


def request(kind, model, port, prompt):
    messages = [{"role": "user", "content": prompt}]
    context = json.loads(prompt.rsplit("\n--- DATA ---\n", 1)[1])
    schema = response_schema(context)
    if kind == "ollama":
        path = "/api/chat"
        payload = {
            "model": model, "messages": messages, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_predict": 1100, "num_ctx": 8192},
        }
    elif kind == "llama":
        path = "/v1/chat/completions"
        payload = {
            "model": model, "messages": messages, "stream": False, "temperature": 0,
            "max_tokens": 1100, "seed": 11, "response_format": {
                "type": "json_schema", "json_schema": {"name": "advisor_decision", "schema": schema},
            },
        }
    else:
        return {"error": "unknown local service"}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3600)
    try:
        connection.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            return {"error": f"HTTP {response.status}"}
        data = response.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            return {"error": "model response too large"}
        value = json.loads(data)
        if kind == "ollama":
            return {
                "content": value["message"]["content"], "finish_reason": value.get("done_reason"),
                "input_tokens": value.get("prompt_eval_count"), "output_tokens": value.get("eval_count"),
            }
        usage = value.get("usage", {})
        return {
            "content": value["choices"][0]["message"]["content"], "finish_reason": value["choices"][0].get("finish_reason"),
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        }
    finally:
        connection.close()


def main():
    try:
        kind, model, port = sys.argv[1:]
        raw = sys.stdin.buffer.read(96 * 1024 + 1)
        if len(raw) > 96 * 1024:
            raise ValueError("oversized prompt")
        result = request(kind, model, int(port), raw.decode())
    except (ValueError, TypeError, OSError, KeyError, IndexError, http.client.HTTPException) as error:
        result = {"error": type(error).__name__}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
