/* ============================================================
   daily_automate — Client JS
   Button feedback + uptime card formatting via HTMX events.
   ============================================================ */

/* ----- Button feedback after trigger + auto-reload ----- */
document.body.addEventListener("htmx:afterRequest", function (event) {
    var el = event.detail.elt;
    if (el.tagName !== "BUTTON") return;
    if (!event.detail.successful) return;

    /* Check if this is a trigger button (hx-post to /api/trigger/) */
    var url = el.getAttribute("hx-post") || "";
    var isTrigger = url.indexOf("/api/trigger/") === 0;

    var original = el.textContent;
    el.textContent = isTrigger ? "Running..." : "Done!";
    el.disabled = true;

    if (isTrigger) {
        /* Record the trigger timestamp so we can detect new activity after it */
        var triggerTime = new Date().toISOString().slice(0, 19).replace("T", " ");
        var attempts = 0;
        var poll = setInterval(function () {
            attempts++;
            if (attempts > 60) {  /* Give up after ~5 min */
                clearInterval(poll);
                el.textContent = original;
                el.disabled = false;
                return;
            }
            fetch("/api/activity")
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    /* Look for any non-"triggered" entry newer than our trigger */
                    for (var i = 0; i < data.length; i++) {
                        if (data[i].action === "triggered") continue;
                        if (data[i].timestamp >= triggerTime) {
                            clearInterval(poll);
                            location.reload();
                            return;
                        }
                        break; /* older entries won't match either */
                    }
                });
        }, 5000);
    } else {
        setTimeout(function () {
            el.textContent = original;
            el.disabled = false;
        }, 2000);
    }
});

/* ----- Dashboard stats: parse /api/dashboard/stats and update cards ----- */
document.body.addEventListener("htmx:beforeSwap", function (event) {
    if (event.detail.target.id === "prs-count") {
        try {
            var data = JSON.parse(event.detail.serverResponse);
            event.detail.serverResponse = String(data.prs_open);
            // Also update drafts count if it exists
            var draftsEl = document.getElementById("drafts-count");
            if (draftsEl) draftsEl.textContent = String(data.drafts_pending);
        } catch (e) {}
        return;
    }
});

/* ----- Uptime card: parse /api/health JSON and format ----- */
document.body.addEventListener("htmx:beforeSwap", function (event) {
    if (event.detail.target.id !== "uptime") return;

    var text = event.detail.serverResponse;
    try {
        var data = JSON.parse(text);
        var s = data.uptime;
        var formatted;
        if (s >= 3600) {
            var h = Math.floor(s / 3600);
            var m = Math.floor((s % 3600) / 60);
            formatted = h + "h " + m + "m";
        } else if (s >= 60) {
            var m2 = Math.floor(s / 60);
            var sec = s % 60;
            formatted = m2 + "m " + sec + "s";
        } else {
            formatted = s + "s";
        }
        event.detail.serverResponse = formatted;
    } catch (e) {
        // If parsing fails, let HTMX handle the raw response
    }
});
