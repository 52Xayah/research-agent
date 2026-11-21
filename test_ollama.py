
import json
from urllib.request import Request, urlopen

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen3.5:4b"


def chat(prompt):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    request = Request(
        OLLAMA_URL,
        data=json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urlopen(request, timeout=180) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    return result["message"]["content"]


if __name__ == "__main__":
    answer = chat("请用中文介绍什么是 AI Agent。")
    print("模型回答：")
    print(answer)
