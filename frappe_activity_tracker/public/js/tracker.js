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
 * • Track button clicks with action classification and context metadata.
 * • Batch-send button click logs every 60 seconds.
 * • Debounce duplicate clicks (300 ms window).
 */

(function () {
	"use strict";

	/* ------------------------------------------------------------------ */
	/* Constants                                                            */
	/* ------------------------------------------------------------------ */
	const IDLE_THRESHOLD_MS        = 60_000;   // 60 s without interaction → idle
	const BATCH_INTERVAL_MS        = 120_000;  // flush time-buffer every 2 min
	const CLICK_BATCH_INTERVAL_MS  = 60_000;   // flush click-buffer every 1 min
	const LEADER_TTL_MS            = 10_000;   // leader lease duration
	const LEADER_KEY               = "fat_leader";
	const LEADER_TS_KEY            = "fat_leader_ts";
	const TAB_ID                   = Math.random().toString(36).slice(2);
	const API_METHOD               = "frappe_activity_tracker.api.track_time";
	const CLICK_API_METHOD         = "frappe_activity_tracker.api.track_button_click";
	const MAX_RETRY_ATTEMPTS       = 3;
	const CLICK_DEBOUNCE_MS        = 300;   // ignore duplicate clicks within 300 ms

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

	// Button click tracking state
	const clickBuffer   = [];          // pending button click entries
	let lastClickKey    = null;        // debounce: "<label>|<route>" of last click
	let lastClickTime   = 0;           // debounce: timestamp of last click

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

	/* ------------------------------------------------------------------ */
	/* Button click tracking                                                */
	/* ------------------------------------------------------------------ */

	/**
	 * Classify an action label into a canonical action type.
	 */
	function classifyAction(label) {
		label = label.toLowerCase();
		if (label.includes("save"))   return "save";
		if (label.includes("submit")) return "submit";
		if (label.includes("cancel")) return "cancel";
		if (label.includes("delete")) return "delete";
		if (label.includes("update")) return "update";
		if (label.includes("amend"))  return "amend";
		if (label.includes("print"))  return "print";
		if (label.includes("email"))  return "email";
		if (label.includes("export")) return "export";
		if (label.includes("import")) return "import";
		return "custom";
	}

	/**
	 * Derive a button_type string from the element's class list.
	 */
	function getButtonType(btn) {
		const cls = btn.className || "";
		if (cls.includes("btn-danger"))    return "danger";
		if (cls.includes("btn-primary") || cls.includes("primary-action")) return "primary";
		if (cls.includes("btn-secondary")) return "secondary";
		if (cls.includes("btn-default"))   return "default";
		if (cls.includes("dropdown-item")) return "dropdown";
		if (cls.includes("menu-item"))     return "menu";
		return "custom";
	}

	/**
	 * Extract tracking metadata from a button/clickable element.
	 */
	function extractButtonInfo(btn) {
		const label = (btn.innerText || btn.textContent || btn.title || "").trim();
		return {
			label:       label.slice(0, 140),
			button_type: getButtonType(btn),
			action_type: classifyAction(label),
		};
	}

	/**
	 * Return true when the element is invisible or disabled (should be ignored).
	 */
	function isButtonIgnored(btn) {
		if (btn.disabled || btn.getAttribute("disabled") !== null) return true;
		if (btn.getAttribute("aria-disabled") === "true") return true;
		// offsetParent is null for hidden elements (except position:fixed)
		if (btn.offsetParent === null && getComputedStyle(btn).position !== "fixed") return true;
		return false;
	}

	/**
	 * Determine view_type, ref_doctype, docname, and route from current Frappe state.
	 */
	function getClickContext() {
		const routeArr  = (frappe.get_route ? frappe.get_route() : []) || [];
		const { viewType, doctype, docname } = parseRoute(routeArr);
		return {
			view_type:   viewType,
			ref_doctype: doctype,
			docname:     docname,
			route:       routeToString(routeArr),
		};
	}

	/**
	 * Record a single button click into the buffer (with debounce guard).
	 */
	function trackButtonClick(btn) {
		if (isButtonIgnored(btn)) return;

		const info    = extractButtonInfo(btn);
		if (!info.label) return;  // skip unlabelled buttons

		// Debounce: ignore if same label+route within CLICK_DEBOUNCE_MS
		const now     = Date.now();
		const ctx     = getClickContext();
		const clickKey = info.label + "|" + ctx.route;
		if (clickKey === lastClickKey && now - lastClickTime < CLICK_DEBOUNCE_MS) return;
		lastClickKey  = clickKey;
		lastClickTime = now;

		clickBuffer.push({
			label:       info.label,
			button_type: info.button_type,
			action_type: info.action_type,
			view_type:   ctx.view_type,
			ref_doctype: ctx.ref_doctype,
			docname:     ctx.docname,
			route:       ctx.route,
		});
	}

	// Event delegation – capture all meaningful click targets
	document.addEventListener("click", function (e) {
		const target = e.target.closest("button, .btn, .dropdown-item, .menu-item, .primary-action");
		if (!target) return;
		trackButtonClick(target);
	}, { passive: true });

	/* ------------------------------------------------------------------ */
	/* Click batch flush                                                    */
	/* ------------------------------------------------------------------ */
	async function sendClickBatch(attempt) {
		attempt = attempt || 1;
		if (!clickBuffer.length) return;
		const batch = clickBuffer.splice(0, clickBuffer.length);

		try {
			await frappe.call({
				method: CLICK_API_METHOD,
				args:   { logs: JSON.stringify(batch) },
				freeze: false,
			});
		} catch (err) {
			clickBuffer.unshift(...batch);
			if (attempt < MAX_RETRY_ATTEMPTS) {
				setTimeout(function () {
					sendClickBatch(attempt + 1);
				}, attempt * 15_000);
			}
		}
	}

	setInterval(function () {
		if (document.hidden) return;
		sendClickBatch(1);
	}, CLICK_BATCH_INTERVAL_MS);

	// Best-effort flush on unload (sendBeacon)
	window.addEventListener("beforeunload", function () {
		if (!clickBuffer.length) return;
		const payload = JSON.stringify({ logs: JSON.stringify(clickBuffer) });
		navigator.sendBeacon(
			"/api/method/" + CLICK_API_METHOD,
			new Blob([payload], { type: "application/json" })
		);
	});
})();
