"use strict";

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
