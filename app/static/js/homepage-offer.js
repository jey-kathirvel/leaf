(function () {
    const modal = document.getElementById("homepageOfferModal");
    if (!modal) {
        return;
    }

    const delayMs = Number(modal.dataset.delaySeconds || 5) * 1000;
    const autoCloseSeconds = Number(modal.dataset.autoCloseSeconds || 15);
    const autoCloseMs = autoCloseSeconds * 1000;
    const timerEl = document.getElementById("homepageOfferTimer");
    const timerValueEl = document.getElementById("homepageOfferTimerValue");
    let showTimer = null;
    let closeTimer = null;
    let countdownTimer = null;
    let remainingSeconds = autoCloseSeconds;

    function clearCountdown() {
        if (countdownTimer) {
            clearInterval(countdownTimer);
            countdownTimer = null;
        }
    }

    function updateCountdownDisplay() {
        if (!timerValueEl) {
            return;
        }
        timerValueEl.textContent = String(Math.max(remainingSeconds, 0));
    }

    function startCountdown() {
        remainingSeconds = autoCloseSeconds;
        updateCountdownDisplay();
        if (timerEl) {
            timerEl.hidden = false;
        }
        clearCountdown();
        countdownTimer = setInterval(() => {
            remainingSeconds -= 1;
            updateCountdownDisplay();
            if (remainingSeconds <= 0) {
                clearCountdown();
            }
        }, 1000);
    }

    function closeOffer() {
        if (showTimer) {
            clearTimeout(showTimer);
            showTimer = null;
        }
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        clearCountdown();
        if (timerEl) {
            timerEl.hidden = true;
        }
        modal.classList.add("is-hidden");
        modal.hidden = true;
        document.body.classList.remove("offer-modal-open");
    }

    function showOffer() {
        modal.hidden = false;
        modal.classList.remove("is-hidden");
        document.body.classList.add("offer-modal-open");
        startCountdown();
        closeTimer = setTimeout(closeOffer, autoCloseMs);
        const closeButton = modal.querySelector(".homepage-offer-close");
        if (closeButton) {
            closeButton.focus({ preventScroll: true });
        }
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
