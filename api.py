from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from knowledge.manager import get_manager

from brain.interpreter import interpret
from brain.entity_resolver import EntityResolver
from actions.executor import execute

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