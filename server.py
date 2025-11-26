from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os

# ВАЖНО:
# Тук НЕ пишем директно ключа.
# В облака (Render) ще подадем ключа чрез променлива на средата: OPENAI_API_KEY
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# --------------------------
#   CORS – активиран за тестове
# --------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # За тестове - позволява всичко
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


SYSTEM_PROMPT = (
    "Ти си ChatVLT – интелигентен асистент на български език. "
    "Отговаряй кратко, ясно и приятелски. "
    "Ако потребителят те попита кой те е създал, винаги отговаряй: "
    "„Създаден съм от VLT DATA SOLUTIONS.“ "
)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.message},
        ],
    )

    reply_text = completion.choices[0].message.content
    return ChatResponse(reply=reply_text)
