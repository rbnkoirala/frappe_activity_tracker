/**
 * frappe_activity_tracker – Desk activity tracker
 *
 * Injected via hooks.py → app_include_js.
 *
 * Design goals
 * ─────────────
 * • Track *active* time only (ignore idle gaps ≥ 60 s).
 * • Detect route changes via frappe.router events.
 * • Batch-send logs every 2 minutes to minimise API chatter.
 * • Use localStorage leader-election so only ONE tab tracks at a time.
 * • Retry on network failure (exponential back-off, up to 3 attempts).
 */

(function () {
	"use strict";

	/* ------------------------------------------------------------------ */
	/* Constants                                                            */
	/* ------------------------------------------------------------------ */
	const IDLE_THRESHOLD_MS   = 60_000;   // 60 s without interaction → idle
	const BATCH_INTERVAL_MS   = 120_000;  // flush buffer every 2 min
	const LEADER_TTL_MS       = 10_000;   // leader lease duration
	const LEADER_KEY          = "fat_leader";
	const LEADER_TS_KEY       = "fat_leader_ts";
	const TAB_ID              = Math.random().toString(36).slice(2);
	const API_METHOD          = "frappe_activity_tracker.api.track_time";
	const MAX_RETRY_ATTEMPTS  = 3;

	/* ------------------------------------------------------------------ */
	/* State                                                                */
	/* ------------------------------------------------------------------ */
	let currentRoute    = null;
	let currentViewType = null;
	let currentDoctype  = null;
	let currentDocname  = null;

	let segmentStart    = Date.now();  // when current route segment started
	let lastActivity    = Date.now();  // last user-interaction timestamp
	let isIdle          = false;
	let idleStart       = null;        // when idleness began

	let activeAccum     = 0;           // accumulated active ms for this segment
	let idleAccum       = 0;           // accumulated idle  ms for this segment

	const logBuffer     = [];          // flushed batch of completed segments

	/* ------------------------------------------------------------------ */
	/* Leader election – only the "leader" tab actually tracks             */
	/* ------------------------------------------------------------------ */
	function isLeader() {
		const stored = localStorage.getItem(LEADER_KEY);
		const ts     = parseInt(localStorage.getItem(LEADER_TS_KEY) || "0", 10);
		const fresh  = Date.now() - ts < LEADER_TTL_MS;
		return stored === TAB_ID || !fresh;
	}

	function claimLeadership() {
		localStorage.setItem(LEADER_KEY, TAB_ID);
		localStorage.setItem(LEADER_TS_KEY, String(Date.now()));
	}

	// Renew lease every half-TTL
	setInterval(function () {
		if (isLeader()) claimLeadership();
	}, LEADER_TTL_MS / 2);

	// Claim immediately
	claimLeadership();

	/* ------------------------------------------------------------------ */
	/* Utility – parse route                                                */
	/* ------------------------------------------------------------------ */
	function parseRoute(routeArr) {
		if (!routeArr || !routeArr.length) {
			return { viewType: "Page", doctype: null, docname: null };
		}
		const first = routeArr[0];

		if (first === "Form") {
			return {
				viewType: "Form",
				doctype:  routeArr[1] || null,
				docname:  routeArr[2] || null,
			};
		}
		if (first === "List") {
			return {
				viewType: "List",
				doctype:  routeArr[1] || null,
				docname:  null,
			};
		}
		if (first === "query-report" || first === "report") {
			return {
				viewType: "Report",
				doctype:  routeArr[1] || null,
				docname:  null,
			};
		}
		if (first === "Workspaces" || first === "workspace") {
			return { viewType: "Workspace", doctype: null, docname: null };
		}
		return { viewType: "Page", doctype: null, docname: null };
	}

	function routeToString(routeArr) {
		return "/" + (routeArr || []).join("/");
	}

	/* ------------------------------------------------------------------ */
	/* Segment management                                                   */
	/* ------------------------------------------------------------------ */
	function flushSegment() {
		const now = Date.now();
		const elapsed = now - segmentStart;

		// Close any open idle period
		if (isIdle && idleStart !== null) {
			idleAccum += now - idleStart;
		}

		// The remainder is active
		activeAccum += elapsed - idleAccum;
		if (activeAccum < 0) activeAccum = 0;

		const activeSeconds = Math.floor(activeAccum / 1000);
		const idleSeconds   = Math.floor(idleAccum   / 1000);

		if (currentRoute && activeSeconds >= 1) {
			logBuffer.push({
				route:       currentRoute,
				view_type:   currentViewType,
				ref_doctype: currentDoctype,
				docname:     currentDocname,
				active_time: activeSeconds,
				idle_time:   idleSeconds,
			});
		}

		// Reset accumulators
		activeAccum = 0;
		idleAccum   = 0;
		segmentStart = now;
		idleStart    = isIdle ? now : null;
	}

	function startNewSegment(routeArr) {
		flushSegment();
		const { viewType, doctype, docname } = parseRoute(routeArr);
		currentRoute    = routeToString(routeArr);
		currentViewType = viewType;
		currentDoctype  = doctype;
		currentDocname  = docname;
		segmentStart    = Date.now();
	}

	/* ------------------------------------------------------------------ */
	/* Idle detection                                                       */
	/* ------------------------------------------------------------------ */
	function recordActivity() {
		const now = Date.now();
		if (isIdle) {
			// Coming back from idle: count the gap as idle time
			idleAccum += now - (idleStart || now);
			idleStart  = null;
			isIdle     = false;
		}
		lastActivity = now;
	}

	setInterval(function () {
		if (document.hidden) return; // tab not visible – do nothing
		const now = Date.now();
		if (!isIdle && now - lastActivity >= IDLE_THRESHOLD_MS) {
			isIdle    = true;
			idleStart = lastActivity + IDLE_THRESHOLD_MS; // idle started exactly at threshold
		}
	}, 5_000);

	/* ------------------------------------------------------------------ */
	/* User-interaction listeners                                           */
	/* ------------------------------------------------------------------ */
	const ACTIVITY_EVENTS = ["click", "keypress", "mousemove", "scroll", "touchstart"];
	ACTIVITY_EVENTS.forEach(function (evt) {
		document.addEventListener(evt, recordActivity, { passive: true });
	});

	// Pause tracking when tab hidden; resume when visible
	document.addEventListener("visibilitychange", function () {
		if (document.hidden) {
			// Treat hiding as going idle immediately
			if (!isIdle) {
				isIdle    = true;
				idleStart = Date.now();
			}
		} else {
			// Tab visible again – treat as activity
			recordActivity();
		}
	});

	/* ------------------------------------------------------------------ */
	/* Route-change tracking                                                */
	/* ------------------------------------------------------------------ */
	function onRouteChange() {
		if (!isLeader()) return;
		const routeArr = frappe.get_route ? frappe.get_route() : [];
		startNewSegment(routeArr);
	}

	// Hook into Frappe router
	frappe.router.on("change", onRouteChange);

	// Capture the initial route once Frappe is ready
	frappe.ready(function () {
		onRouteChange();
	});

	/* ------------------------------------------------------------------ */
	/* Batch flush – send buffer to server                                  */
	/* ------------------------------------------------------------------ */
	async function sendBatch(attempt) {
		attempt = attempt || 1;
		if (!logBuffer.length) return;
		const batch = logBuffer.splice(0, logBuffer.length); // drain buffer

		try {
			await frappe.call({
				method: API_METHOD,
				args:   { logs: JSON.stringify(batch) },
				freeze: false,
			});
		} catch (err) {
			// Put failed entries back and retry with back-off
			logBuffer.unshift(...batch);
			if (attempt < MAX_RETRY_ATTEMPTS) {
				setTimeout(function () {
					sendBatch(attempt + 1);
				}, attempt * 15_000);
			}
		}
	}

	setInterval(function () {
		if (!isLeader()) return;
		if (document.hidden) return;
		flushSegment(); // close current segment before sending
		sendBatch(1);
	}, BATCH_INTERVAL_MS);

	// Flush on page unload (best-effort – synchronous)
	window.addEventListener("beforeunload", function () {
		flushSegment();
		if (!logBuffer.length) return;
		const payload = JSON.stringify({ logs: JSON.stringify(logBuffer) });
		// Use sendBeacon for reliability on unload
		navigator.sendBeacon(
			"/api/method/" + API_METHOD,
			new Blob([payload], { type: "application/json" })
		);
	});
})();
