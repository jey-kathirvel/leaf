(function () {
    const modal = document.getElementById("homepageOfferModal");
    if (!modal) {
        return;
    }

    const delayMs = Number(modal.dataset.delaySeconds || 5) * 1000;
    const autoCloseMs = Number(modal.dataset.autoCloseSeconds || 15) * 1000;
    let showTimer = null;
    let closeTimer = null;

    function closeOffer() {
        if (showTimer) {
            clearTimeout(showTimer);
            showTimer = null;
        }
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        modal.classList.add("is-hidden");
        modal.hidden = true;
        document.body.classList.remove("offer-modal-open");
    }

    function showOffer() {
        modal.hidden = false;
        modal.classList.remove("is-hidden");
        document.body.classList.add("offer-modal-open");
        closeTimer = setTimeout(closeOffer, autoCloseMs);
    }

    modal.querySelectorAll("[data-offer-close]").forEach((element) => {
        element.addEventListener("click", closeOffer);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) {
            closeOffer();
        }
    });

    const copyButton = document.getElementById("homepageOfferCopy");
    const couponCode = document.getElementById("homepageOfferCoupon");
    if (copyButton && couponCode) {
        copyButton.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(couponCode.textContent.trim());
                copyButton.textContent = "Copied";
                setTimeout(() => {
                    copyButton.textContent = "Copy";
                }, 1800);
            } catch (_error) {
                copyButton.textContent = "Copy failed";
            }
        });
    }

    showTimer = setTimeout(showOffer, delayMs);
})();
