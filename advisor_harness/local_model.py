"""Worker for loopback model requests. The parent owns timeout and cancellation."""

import http.client
import json
import sys


def object_schema(fields, required):
    return {"type": "object", "properties": fields, "required": required, "additionalProperties": False}


def response_schema(phase):
    string = {"type": "string"}
    number = {"type": "integer"}
    strings = {"type": "array", "items": string}
    if phase == "plan":
        task = object_schema({
            "id": string, "title": string, "depends": strings, "priority": number, "checks": strings,
        }, ["id", "title", "depends", "checks"])
        finding = object_schema({
            "tag": string, "issue": string, "impact": string, "verification": string,
        }, ["tag", "issue", "impact", "verification"])
        return object_schema({
            "level": number, "goal": string, "constraints": strings, "answer": string,
            "tasks": {"type": "array", "items": task}, "review": {"type": "array", "items": finding},
        }, ["level", "goal", "constraints", "tasks"])
    work = ["read", "check", "edit", "finish", "block"]
    return object_schema({
        "action": {"enum": ["edit", "finish"] if phase == "repair" else work},
        "path": string, "id": string, "old": {"type": ["string", "null"]}, "new": string,
        "summary": string, "tag": string, "root_cause": string, "basis": string,
        "experience": {"type": ["integer", "null"]},
    }, ["action"])


def request(kind, model, port, prompt):
    messages = [{"role": "user", "content": prompt}]
    context = json.loads(prompt.rsplit("\n--- DATA ---\n", 1)[1])
    schema = response_schema(context["phase"])
    if kind == "ollama":
        path = "/api/chat"
        payload = {
            "model": model, "messages": messages, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_predict": 1400},
        }
    elif kind == "llama":
        path = "/v1/chat/completions"
        payload = {
            "model": model, "messages": messages, "stream": False, "temperature": 0,
            "max_tokens": 1400, "seed": 11, "response_format": {
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
                "content": value["message"]["content"],
                "input_tokens": value.get("prompt_eval_count"), "output_tokens": value.get("eval_count"),
            }
        usage = value.get("usage", {})
        return {
            "content": value["choices"][0]["message"]["content"],
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
