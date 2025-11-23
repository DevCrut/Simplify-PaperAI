from openai import OpenAI

LLM_BASE_URL = "http://127.0.0.1:8000/v1"
LLM_API_KEY = "dummy-key"  # vLLM just needs *something* here

client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
)

LOCAL_MODEL_NAME = "Qwen/Qwen2.5-Coder-3B-Instruct"


def generate_member_doc(class_name: str, member_name: str, yaml_text: str) -> str:
    prompt = f"""
You are a Roblox Luau API documentation writer.

I will give you the full YAML description of a class: {class_name}.
Then I will give you the name of one member of that class.

Write a short, developer-friendly documentation snippet (max 3 sentences)
for that member, focusing on what it does and how it is used in Roblox games.

Class YAML:
---
{yaml_text}
---

Member name: {member_name}

Return ONLY the description text, no bullet points, no JSON.
""".strip()

    resp = client.chat.completions.create(
        model=LOCAL_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are an expert, concise Roblox Luau API documentation writer.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=256,
    )

    return resp.choices[0].message.content.strip()
