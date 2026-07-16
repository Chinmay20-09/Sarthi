import requests


class NotionClient:
    BASE_URL = "https://api.notion.com/v1"

    def __init__(self, token: str, version: str = "2022-06-28"):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        }

    def _post(self, endpoint: str, payload: dict):
        response = requests.post(
            f"{self.BASE_URL}{endpoint}",
            headers=self.headers,
            json=payload,
            timeout=15,
        )

        response.raise_for_status()
        return response.json()

    def _get(self, endpoint: str):
        response = requests.get(
            f"{self.BASE_URL}{endpoint}",
            headers=self.headers,
            timeout=15,
        )

        response.raise_for_status()
        return response.json()

    def query_database(self, database_id: str):
        return self._post(
            f"/databases/{database_id}/query",
            {}
        )

    def get_page(self, page_id: str):
        return self._get(f"/pages/{page_id}")

    def create_page(self, database_id: str, title: str, properties: dict | None = None):
        payload = {
            "parent": {
                "database_id": database_id
            },
            "properties": {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }
        }

        if properties:
            payload["properties"].update(properties)

        return self._post("/pages", payload)

    def update_page(self, page_id: str, properties: dict):
        response = requests.patch(
            f"{self.BASE_URL}/pages/{page_id}",
            headers=self.headers,
            json={"properties": properties},
            timeout=15,
        )

        response.raise_for_status()
        return response.json()

    def search(self, query: str):
        payload = {
            "query": query
        }

        return self._post("/search", payload)

    def find_project(self, database_id: str, project_name: str):
        data = self.query_database(database_id)

        for page in data.get("results", []):
            props = page.get("properties", {})
            title = props.get("Name", {}).get("title", [])

            if title:
                name = title[0]["plain_text"]

                if name.lower() == project_name.lower():
                    return page

        return None