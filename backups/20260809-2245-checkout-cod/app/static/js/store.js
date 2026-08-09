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
        button.addEventListener("click", () => {
            const originalText = button.textContent;

            button.disabled = true;
            button.textContent = "Added";

            window.setTimeout(() => {
                button.disabled = false;
                button.textContent = originalText;
            }, 1200);
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
