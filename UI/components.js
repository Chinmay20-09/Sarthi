async function loadComponent(id, file) {

    const response = await fetch(file);

    document.getElementById(id).innerHTML =
        await response.text();

}

async function loadLayout() {

    await loadComponent("sidebar", "components/sidebar.html");

    await loadComponent("footer", "components/footer.html");

    if (typeof initializePage === "function") {

        initializePage();

    }

}

loadLayout();
function initializePage() {


        const API = "http://127.0.0.1:8000";

        const typeButton = document.getElementById("typebutton");
        const speakButton = document.getElementById("speakButton");
        const status = document.getElementById("status");

        typeButton.addEventListener("click", async () => {

                const command = prompt("Enter command");

                if (!command)
                    return;

                status.innerText = "Thinking...";

                try {

                    const response = await fetch(API + "/command", {

                        method: "POST",

                        headers: {
                            "Content-Type": "application/json"
                        },

                        body: JSON.stringify({
                            text: command
                        })

                    });

                    const result = await response.json();

                    status.innerText =
                        "Executed : " + result.action + " " + result.target;

                } catch (err) {

                    console.error(err);

                    status.innerText = "Connection Failed";

                }

            });
        speakButton.addEventListener("click", async () => {

                status.innerText = "Listening...";

                try {

                    const response = await fetch(API + "/listen", {

                        method: "POST"

                    });

                    const result = await response.json();

                    status.innerText =
                        "Executed : " + result.action + " " + result.target;

                    console.log(result);

                }

                catch (err) {

                    console.error(err);

                    status.innerText = "Connection Failed";

                }

            });
        }