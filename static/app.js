/* ============================================================
   daily_automate — Client JS
   Button feedback + uptime card formatting via HTMX events.
   ============================================================ */

/* ----- Button feedback after trigger ----- */
document.body.addEventListener("htmx:afterRequest", function (event) {
    var el = event.detail.elt;
    if (el.tagName !== "BUTTON") return;
    if (!event.detail.successful) return;

    var original = el.textContent;
    el.textContent = "Triggered!";
    el.disabled = true;

    setTimeout(function () {
        el.textContent = original;
        el.disabled = false;
    }, 2000);
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
