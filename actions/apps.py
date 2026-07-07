import subprocess


APP_ALIASES = {

    "vscode": {
        "command": "code",
        "aliases": [
            "vs code",
            "visual studio code",
            "code"
        ]
    },

    "notepad": {
        "command": "notepad",
        "aliases": []
    },
    "calculator": {
        "command": "calc.exe",
        "aliases": []
    }

}


def open_app(target: str) -> bool:

    print(f"Target received: {target}")

    target = target.lower().strip()

    command = APP_ALIASES.get(target)

    print(f"Command resolved: {command}")

    if command is None:
        return False

    try:
        subprocess.Popen(command["command"], shell=True)
        print(f"🖥️ Opening {target}")
        return True

    except Exception as e:
        print(e)
        return False