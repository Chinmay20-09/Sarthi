from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from knowledge.manager import get_manager
from skills.speech_recognization.listener import listen

from brain.interpreter import interpret
from brain.entity_resolver import EntityResolver
from actions.executor import execute
from skills.manager import load_skills
app = FastAPI(title="Sarthi API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

resolver = EntityResolver()
knowledge = get_manager()


class CommandRequest(BaseModel):
    text: str


@app.get("/")
def home():
    return {
        "assistant": "Sarthi",
        "status": "Running"
    }


@app.post("/command")
def command(request: CommandRequest):

    intent = interpret(request.text)

    if intent.target:
        intent.target = resolver.resolve(intent.target)

    execute(intent)

    return {
        "action": intent.action,
        "target": intent.target,
        "confidence": intent.confidence,
        "status": "executed"
    }
@app.get("/knowledge")
def knowledge_stats():

    applications = knowledge.load_applications() 

    games = [
    e for e in applications
    if e["category"] == "game"
    ]

    apps = [
    e for e in applications
    if e["category"] == "application"
    ]
@app.get("/applications")
def applications():

    apps = knowledge.load_applications()

    return [
        {
            "name": app["name"],
            "category": app["category"]
        }
        for app in apps
    ]
@app.get("/skills")
def get_skills():

    return load_skills()
@app.post("/listen")
def listen_command():

    text = listen()

    print(f"🎤 Whisper : {text}")

    intent = interpret(text)

    if intent.target:
        intent.target = resolver.resolve(intent.target)

    print(f"🧠 Intent : {intent.model_dump()}")

    execute(intent)

    return {
        "text": text,
        "action": intent.action,
        "target": intent.target,
        "confidence": intent.confidence,
        "status": "executed"
    }