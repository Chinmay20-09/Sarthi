import webbrowser

SITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
}


def open_site(target: str):

    target = target.lower()

    if target in SITES:

        print(f"🌐 Opening {target}")

        webbrowser.open(SITES[target])

        return True

    return False