from actions.apps import open_app
from actions.browser import open_site


def execute(intent):
    if intent.action != "open":
        print("Unknown action")
        return

    if open_site(intent.target):
        return

    if open_app(intent.target):
        return

    print("Unknown target:", intent.target)
