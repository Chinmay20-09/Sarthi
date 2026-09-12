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

// API base is whatever host the page was opened from (127.0.0.1 locally,
// the PC's LAN IP when opened from a phone or another device), so the
// dashboard works on any device without editing code.
const API = window.location.origin;

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
    setupCommandHandlers();
    setupMobileDrawer();

    if (typeof initializePage === "function") {
        initializePage();
    }
}

// ---------------------------------------------------------------------------
// Mobile sidebar drawer (phones/tablets <md)
// ---------------------------------------------------------------------------
// The shared sidebar is display:none on <md; the footer hamburger toggles it
// as an off-canvas drawer. Tap outside or navigate to dismiss.
function setupMobileDrawer() {
    const root = document.getElementById("sarthi-sidebar-root");
    const sidebar = document.getElementById("sarthi-sidebar");
    const scrim = document.getElementById("sarthi-sidebar-scrim");
    const menuBtn = document.getElementById("sarthi-menu-btn");
    if (!root || !sidebar || !menuBtn) return;

    const isOpen = () => root.classList.contains("sarthi-drawer-open");

    const close = () => {
        root.classList.remove("sarthi-drawer-open");
        sidebar.classList.remove("sarthi-drawer-open");
        if (scrim) scrim.classList.remove("sarthi-drawer-open");
    };

    const open = () => {
        root.classList.add("sarthi-drawer-open");
        sidebar.classList.add("sarthi-drawer-open");
        if (scrim) scrim.classList.add("sarthi-drawer-open");
    };

    menuBtn.addEventListener("click", (event) => {
        // The document-level tap-outside listener must not immediately
        // re-close the drawer for the same tap that opened it.
        event.stopPropagation();
        if (isOpen()) {
            close();
        } else {
            open();
        }
    });

    if (scrim) {
        scrim.addEventListener("click", close);
    }

    // Navigation always closes the drawer (nav links carry .sarthi-nav-close).
    document.querySelectorAll(".sarthi-nav-close").forEach((el) => {
        el.addEventListener("click", close);
    });

    // Tap outside the open drawer closes it.
    document.addEventListener("click", (event) => {
        if (!isOpen()) return;
        const target = event.target;
        if (target instanceof Node && sidebar.contains(target)) return;
        close();
    });
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
    if (!typeButton || !speakButton) return;

    function updateStatus(text) {
        const el = document.getElementById("status");
        if (el) el.innerText = text;
    }

    typeButton.addEventListener("click", async () => {
        const command = prompt("Enter command");
        if (!command) return;
        updateStatus("Thinking...");
        try {
            const response = await fetch(API + "/command", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: command }),
            });
            const result = await response.json();
            updateStatus("Executed : " + result.action + " " + result.target);
        } catch (err) {
            console.error(err);
            updateStatus("Connection Failed");
        }
    });

    speakButton.addEventListener("click", async () => {
        updateStatus("Listening...");
        try {
            const response = await fetch(API + "/listen", { method: "POST" });
            const result = await response.json();
            updateStatus("Executed : " + result.action + " " + result.target);
        } catch (err) {
            console.error(err);
            updateStatus("Connection Failed");
        }
    });
}

// Auto-initialize on DOM ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadLayout);
} else {
    loadLayout();
}
