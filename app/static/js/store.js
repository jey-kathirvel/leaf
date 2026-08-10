"use strict";

let deferredInstallPrompt = null;
const pwaInstallButton = document.getElementById("pwaInstallButton");

window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    if (pwaInstallButton) pwaInstallButton.hidden = false;
});

if (pwaInstallButton) {
    pwaInstallButton.addEventListener("click", async () => {
        if (!deferredInstallPrompt) return;
        deferredInstallPrompt.prompt();
        await deferredInstallPrompt.userChoice;
        deferredInstallPrompt = null;
        pwaInstallButton.hidden = true;
    });
}

window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    if (pwaInstallButton) pwaInstallButton.hidden = true;
});

if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").then((registration) => {
            const activateWaitingWorker = (worker) => {
                if (!worker || !navigator.serviceWorker.controller) return;
                worker.postMessage({type: "SKIP_WAITING"});
            };
            activateWaitingWorker(registration.waiting);
            registration.addEventListener("updatefound", () => {
                const worker = registration.installing;
                if (!worker) return;
                worker.addEventListener("statechange", () => {
                    if (worker.state === "installed") activateWaitingWorker(worker);
                });
            });
        }).catch(() => {
            // The storefront remains fully functional when registration is unavailable.
        });
    });

    let pwaRefreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (pwaRefreshing) return;
        pwaRefreshing = true;
        window.location.reload();
    });
}

const mobileMenuButton = document.getElementById(
    "mobileMenuButton"
);

const mainNav = document.getElementById("mainNav");

if (mobileMenuButton && mainNav) {
    mobileMenuButton.addEventListener("click", () => {
        const isOpen = mainNav.classList.toggle("is-open");

        mobileMenuButton.setAttribute(
            "aria-expanded",
            String(isOpen)
        );

        document.body.classList.toggle(
            "menu-open",
            isOpen
        );
    });

    mainNav.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
            mainNav.classList.remove("is-open");

            mobileMenuButton.setAttribute(
                "aria-expanded",
                "false"
            );

            document.body.classList.remove("menu-open");
        });
    });
}

document
    .querySelectorAll(".add-cart-button")
    .forEach((button) => {
        button.addEventListener("click", async () => {
            const originalText = button.textContent;

            button.disabled = true;
            button.textContent = "Adding…";
            try {
                const response = await fetch(
                    `/cart/items/${button.dataset.productId}`,
                    {
                        method: "POST",
                        headers: {"X-Requested-With": "XMLHttpRequest"},
                    }
                );
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.message || "Could not add this product.");
                }
                document.querySelectorAll(".cart-count").forEach((count) => {
                    count.textContent = result.count;
                });
                button.textContent = "Added ✓";
            } catch (error) {
                button.textContent = error.message;
                button.classList.add("button-error");
            }
            window.setTimeout(() => {
                button.disabled = false;
                button.textContent = originalText;
                button.classList.remove("button-error");
            }, 1800);
        });
    });

const mainProductImage = document.querySelector(
    ".product-main-image img"
);

document
    .querySelectorAll("[data-gallery-image]")
    .forEach((thumbnail) => {
        thumbnail.addEventListener("click", () => {
            if (!mainProductImage) return;
            mainProductImage.src = thumbnail.dataset.galleryImage;
            mainProductImage.alt = thumbnail.dataset.galleryAlt || "Product image";
        });
    });

const revealNodes = document.querySelectorAll(".reveal");
if (revealNodes.length) {
    if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add("is-visible");
                    revealObserver.unobserve(entry.target);
                });
            },
            { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
        );
        revealNodes.forEach((node) => revealObserver.observe(node));
    } else {
        revealNodes.forEach((node) => node.classList.add("is-visible"));
    }
}
