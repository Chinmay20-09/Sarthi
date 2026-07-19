/**
 * Sarthi UI — Shared Component Loader
 *
 * Loads sidebar and footer from component files, highlights active page,
 * and calls page-specific initializePage() after loading.
 *
 * Every HTML page should:
 *   1. Include: <script src="components.js"></script>
 *   2. Define: initializePage() for page-specific logic
 *   3. Include containers: <div id="sidebar"></div>, <div id="footer"></div>
 */

const API = "http://127.0.0.1:8000";

async function loadComponent(id, file) {
    try {
        const response = await fetch(file);
        if (!response.ok) {
            console.warn("Sarthi UI: Could not load " + file + " (" + response.status + ")");
            return;
        }
        const html = await response.text();
        const target = document.getElementById(id);
        if (target) {
            target.innerHTML = html;
        }
    } catch (err) {
        console.warn("Sarthi UI: Failed to load component " + file, err);
    }
}

async function loadLayout() {
    await loadComponent("sidebar", "components/sidebar.html");
    await loadComponent("footer", "components/footer.html");

    highlightCurrentPage();
    attachNavAnimations();

    if (typeof initializePage === "function") {
        initializePage();
    }
}

function highlightCurrentPage() {
    const currentPage = getCurrentPageName();
    document.querySelectorAll(".nav-item").forEach((item) => {
        const page = item.getAttribute("data-page");
        if (page === currentPage) {
            item.classList.add("text-primary", "font-bold", "border-r-2",
                "border-primary-container", "bg-primary/5");
            item.classList.remove("text-on-surface-variant", "font-medium");
        }
    });
}

function getCurrentPageName() {
    const page = window.location.pathname.split("/").pop().replace(".html", "");
    return page || "dashboard";
}

function attachNavAnimations() {
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.addEventListener("mouseenter", () => {
            if (!item.classList.contains("text-primary")) {
                item.style.paddingLeft = "36px";
            }
        });
        item.addEventListener("mouseleave", () => {
            if (!item.classList.contains("text-primary")) {
                item.style.paddingLeft = "32px";
            }
        });
    });
}

function setupCommandHandlers() {
    const typeButton = document.getElementById("typebutton");
    const speakButton = document.getElementById("speakButton");
    const status = document.getElementById("status");
    if (!typeButton || !speakButton || !status) return;

    typeButton.addEventListener("click", async () => {
        const command = prompt("Enter command");
        if (!command) return;
        status.innerText = "Thinking...";
        try {
            const response = await fetch(API + "/command", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: command }),
            });
            const result = await response.json();
            status.innerText = "Executed : " + result.action + " " + result.target;
        } catch (err) {
            console.error(err);
            status.innerText = "Connection Failed";
        }
    });

    speakButton.addEventListener("click", async () => {
        status.innerText = "Listening...";
        try {
            const response = await fetch(API + "/listen", { method: "POST" });
            const result = await response.json();
            status.innerText = "Executed : " + result.action + " " + result.target;
        } catch (err) {
            console.error(err);
            status.innerText = "Connection Failed";
        }
    });
}

// Auto-initialize on DOM ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadLayout);
} else {
    loadLayout();
}
