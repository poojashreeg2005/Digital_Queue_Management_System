/**
 * visitor_queue.js
 * Live polling and status updates for QueueFlow AI Visitor Digital Pass.
 */

document.addEventListener("DOMContentLoaded", function () {
    const statusContainer = document.getElementById("visitor-pass-container");
    if (!statusContainer) return;

    const trackingToken = statusContainer.getAttribute("data-tracking-token");
    if (!trackingToken) return;

    const updatesUrl = `/visitor/updates/${trackingToken}`;

    async function pollVisitorStatus() {
        try {
            const response = await fetch(updatesUrl, {
                method: "GET",
                headers: { "Accept": "application/json" },
                cache: "no-store"
            });

            if (!response.ok) return;

            const data = await response.json();
            if (!data.success) return;

            // 1. Update Status Badge
            const statusBadge = document.getElementById("pass-status-badge");
            if (statusBadge) {
                statusBadge.textContent = data.status.toUpperCase();
                statusBadge.className = `badge-status badge-${data.status.toLowerCase()}`;
            }

            // 2. Update Queue Position & People Ahead
            const queuePosElem = document.getElementById("pass-queue-position");
            if (queuePosElem) {
                if (data.status === "approved") {
                    queuePosElem.textContent = data.queue_position ? `#${data.queue_position}` : "Awaiting Lineup";
                } else if (data.status === "called") {
                    queuePosElem.textContent = "NOW SERVING";
                } else if (data.status === "completed") {
                    queuePosElem.textContent = "Completed";
                } else {
                    queuePosElem.textContent = "—";
                }
            }

            const peopleAheadElem = document.getElementById("pass-people-ahead");
            if (peopleAheadElem) {
                if (data.status === "approved") {
                    peopleAheadElem.textContent = `${data.people_ahead} ahead in queue`;
                } else if (data.status === "called") {
                    peopleAheadElem.textContent = "Proceed to counter now";
                } else {
                    peopleAheadElem.textContent = "";
                }
            }

            // 3. Update Wait Time
            const waitTimeElem = document.getElementById("pass-wait-time");
            if (waitTimeElem) {
                waitTimeElem.textContent = data.estimated_wait_text || "Calculating...";
            }

            // 4. Update Serving Token
            const servingTokenElem = document.getElementById("pass-serving-token");
            if (servingTokenElem) {
                servingTokenElem.textContent = data.currently_serving || "None active";
            }

            // 5. Update Counter Info
            const counterNameElem = document.getElementById("pass-counter-name");
            if (counterNameElem) {
                counterNameElem.textContent = data.counter_name || "Awaiting assignment";
            }

            const counterLocElem = document.getElementById("pass-counter-location");
            if (counterLocElem) {
                counterLocElem.textContent = data.counter_location || "Location will be displayed once counter is assigned.";
            }

            // 6. Action Alert Banner if token is Called
            const alertBanner = document.getElementById("pass-action-banner");
            if (alertBanner) {
                if (data.status === "called") {
                    alertBanner.style.display = "block";
                    alertBanner.innerHTML = `
                        <div style="background:#eaf8f0; border:2px solid #16865a; color:#16865a; padding:16px; border-radius:12px; margin-bottom:20px; text-align:center;">
                            <h3 style="margin:0 0 6px; font-size:18px;">🔔 YOUR TOKEN IS NOW BEING CALLED!</h3>
                            <p style="margin:0; font-size:14px;">Please proceed immediately to <strong>${data.counter_name || "Assigned Counter"}</strong> in <strong>${data.counter_location || "Administrative Block"}</strong>.</p>
                        </div>
                    `;
                } else if (data.status === "completed") {
                    alertBanner.style.display = "block";
                    alertBanner.innerHTML = `
                        <div style="background:#f7f6fc; border:1px solid #d1ceeb; color:#49348e; padding:14px; border-radius:12px; margin-bottom:20px; text-align:center;">
                            <p style="margin:0; font-weight:bold;">✓ Service Completed. Thank you for visiting Canara Engineering College!</p>
                        </div>
                    `;
                } else if (data.status === "declined") {
                    alertBanner.style.display = "block";
                    alertBanner.innerHTML = `
                        <div style="background:#fff0f2; border:1px solid #ffd9de; color:#d94b61; padding:14px; border-radius:12px; margin-bottom:20px; text-align:center;">
                            <p style="margin:0; font-weight:bold;">This token was declined: ${data.decline_reason || "Please visit reception desk for guidance."}</p>
                        </div>
                    `;
                } else {
                    alertBanner.style.display = "none";
                }
            }

        } catch (error) {
            console.warn("QueueFlow live status polling error:", error);
        }
    }

    // Initial poll and recurring every 15 seconds
    pollVisitorStatus();
    setInterval(pollVisitorStatus, 15000);
});
