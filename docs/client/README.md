# Use Sarthi

Sarthi runs on your Windows computer. Enter a command in the desktop app or in the web dashboard.

Sarthi first checks for a known, direct action. The desktop app can open one installed app from its local inventory. Other requests go to the backend. The backend can use a local or cloud model, based on your settings. A Desktop Hand performs approved computer actions.

## Start here

1. Read [Installation](INSTALLATION.md) to install and start Sarthi.
2. Read [Usage](USAGE.md) for commands and features.
3. Read [FAQ](FAQ.md) for common problems and limits.

For system design and development, see [developer documentation](../dev/README.md).

## Data and network

Sarthi stores its database and task records on this computer. The default model provider is local Ollama. The backend listens on this computer only. Do not expose the backend or Desktop Agent to a network. They do not have remote authentication or encrypted transport.

The desktop app can open a known app when the backend is offline. Other commands need the backend.
