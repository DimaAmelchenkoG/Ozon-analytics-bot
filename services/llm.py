import os

import httpx


def ask_llm(prompt: str) -> str:
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        raise RuntimeError("Set LLM_API_KEY in .env")

    url = f"{base_url}/responses"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "Отвечай кратко и по делу на русском языке."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    response.raise_for_status()
    data = response.json()

    return data["output"][0]["content"][0]["text"].strip()
