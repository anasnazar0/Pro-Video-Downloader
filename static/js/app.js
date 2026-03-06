/* ===================================================================
   StreamVault — Frontend Logic
   =================================================================== */
(function () {
    "use strict";

    // ---- DOM refs ----
    const form        = document.getElementById("urlForm");
    const urlInput    = document.getElementById("urlInput");
    const submitBtn   = document.getElementById("submitBtn");
    const btnLabel    = submitBtn.querySelector(".btn-label");
    const btnSpinner  = submitBtn.querySelector(".btn-spinner");

    const statusArea  = document.getElementById("statusArea");
    const statusText  = document.getElementById("statusText");

    const resultCard  = document.getElementById("resultCard");
    const videoPlayer = document.getElementById("videoPlayer");
    const videoTitle  = document.getElementById("videoTitle");
    const videoDur    = document.getElementById("videoDuration");
    const videoSize   = document.getElementById("videoSize");
    const downloadBtn = document.getElementById("downloadBtn");

    const toast       = document.getElementById("errorToast");
    const toastMsg    = document.getElementById("toastMsg");
    const toastClose  = document.getElementById("toastClose");

    let toastTimer = null;

    // ---- Helpers ----
    function setLoading(on) {
        submitBtn.disabled   = on;
        btnLabel.hidden      = on;
        btnSpinner.hidden    = !on;
        statusArea.hidden    = !on;
        statusText.textContent = "Downloading & processing — this may take a moment…";
    }

    function formatDuration(sec) {
        if (!sec && sec !== 0) return "Unknown";
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${s.toString().padStart(2, "0")}`;
    }

    function showToast(msg, autoMs = 6000) {
        toastMsg.textContent = msg;
        toast.hidden = false;
        clearTimeout(toastTimer);
        if (autoMs > 0) {
            toastTimer = setTimeout(() => { toast.hidden = true; }, autoMs);
        }
    }

    function hideToast() {
        toast.hidden = true;
        clearTimeout(toastTimer);
    }

    // ---- Form submit ----
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideToast();

        const url = urlInput.value.trim();
        if (!url) return;

        // Reset previous result
        resultCard.hidden = true;
        // Free previous video from memory
        videoPlayer.removeAttribute("src");
        videoPlayer.load();

        setLoading(true);

        try {
            const res = await fetch("/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url }),
            });

            const data = await res.json();

            if (!res.ok) {
                const errMsg = data.error || `Server error (${res.status})`;
                showToast(errMsg);
                return;
            }

            // Success — show the result card
            const streamUrl = `/stream/${encodeURIComponent(data.filename)}`;

            videoPlayer.src = streamUrl;
            videoPlayer.load();

            videoTitle.textContent   = data.title || "Untitled";
            videoDur.textContent     = `⏱ ${formatDuration(data.duration)}`;
            videoSize.textContent    = `💾 ${data.size_mb} MB`;
            downloadBtn.href        = `${streamUrl}?dl=1`;

            resultCard.hidden = false;
        } catch (err) {
            showToast("Network error — please check your connection and try again.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    });

    // ---- Toast close ----
    toastClose.addEventListener("click", hideToast);
})();
