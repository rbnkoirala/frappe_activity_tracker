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
 *
 * Performance guarantees
 * ──────────────────────
 * • ZERO UI blocking – all heavy work deferred via requestIdleCallback.
 * • Event listeners do minimal work: push to local buffer and exit (<5 ms).
 * • mousemove throttled to 1 event per 2 s; scroll to 1 per 3 s.
 * • Click DOM reads (innerText) deferred to idle time via pendingClickTargets.
 * • Buffers capped at MAX_BUFFER_SIZE; force-flushed when full.
 * • Tracking pauses automatically when the tab is hidden.
 * • All errors swallowed silently – tracker never breaks Frappe UI.
 */

(function () {
	"use strict";

	/* ------------------------------------------------------------------ */
	/* Constants                                                            */
	/* ------------------------------------------------------------------ */
	const IDLE_THRESHOLD_MS       = 60_000;   // 60 s without interaction → idle
	const BATCH_INTERVAL_MS       = 120_000;  // flush time-buffer every 2 min
	const CLICK_BATCH_INTERVAL_MS = 60_000;   // flush click-buffer every 1 min
	const LEADER_TTL_MS           = 10_000;   // leader lease duration
	const MAX_BUFFER_SIZE         = 100;      // max events before forced flush
	const MOUSE_THROTTLE_MS       = 2_000;    // one mousemove signal per 2 s
	const SCROLL_THROTTLE_MS      = 3_000;    // one scroll   signal per 3 s
	const LEADER_KEY              = "fat_leader";
	const LEADER_TS_KEY           = "fat_leader_ts";
	const TAB_ID                  = Math.random().toString(36).slice(2);
	const API_METHOD              = "frappe_activity_tracker.api.track_time";
	const CLICK_API_METHOD        = "frappe_activity_tracker.api.track_button_click";
	const MAX_RETRY_ATTEMPTS      = 3;
	const CLICK_DEBOUNCE_MS       = 300;   // ignore duplicate clicks within 300 ms

	/* ------------------------------------------------------------------ */
	/* Utilities                                                            */
	/* ------------------------------------------------------------------ */

	/**
	 * Schedule work during browser idle time.
	 * Falls back to setTimeout when requestIdleCallback is unavailable.
	 */
	function scheduleIdle(fn) {
		if (typeof requestIdleCallback === "function") {
			requestIdleCallback(fn, { timeout: 5_000 });
		} else {
			setTimeout(fn, 0);
		}
	}

	/**
	 * Return a throttled version of fn that fires at most once per ms interval.
	 * Preserves the calling context and arguments of the original function.
	 */
	function throttle(fn, ms) {
		let last = 0;
		return function () {
			const now = Date.now();
			if (now - last >= ms) {
				last = now;
				fn.apply(this, arguments);
			}
		};
	}

	/* ------------------------------------------------------------------ */
	/* State                                                                */
	/* ------------------------------------------------------------------ */
	let currentRoute    = null;
	let currentViewType = null;
	let currentDoctype  = null;
	let currentDocname  = null;

	let segmentStart = Date.now();  // when current route segment started
	let lastActivity = Date.now();  // last user-interaction timestamp
	let isIdle       = false;
	let idleStart    = null;        // when idleness began

	let activeAccum = 0;            // accumulated active ms for this segment
	let idleAccum   = 0;            // accumulated idle   ms for this segment

	const logBuffer = [];           // completed time-segment entries

	// Button click tracking state
	const clickBuffer         = [];   // pending click entries ready to send
	const pendingClickTargets = [];   // raw click targets awaiting idle processing
	let lastClickKey  = null;
	let lastClickTime = 0;

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
		try { if (isLeader()) claimLeadership(); } catch (_) {}
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
		const now     = Date.now();
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

			// Force-flush if buffer is nearing capacity
			if (logBuffer.length >= MAX_BUFFER_SIZE) {
				scheduleIdle(function () { sendBatch(1); });
			}
		}

		// Reset accumulators
		activeAccum  = 0;
		idleAccum    = 0;
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

	// Throttled variants to prevent flooding on high-frequency events
	const recordActivityMousemove = throttle(recordActivity, MOUSE_THROTTLE_MS);
	const recordActivityScroll    = throttle(recordActivity, SCROLL_THROTTLE_MS);

	// Lightweight idle poll – no DOM reads, no heavy logic
	setInterval(function () {
		try {
			if (document.hidden) return;
			const now = Date.now();
			if (!isIdle && now - lastActivity >= IDLE_THRESHOLD_MS) {
				isIdle    = true;
				idleStart = lastActivity + IDLE_THRESHOLD_MS; // idle started at threshold
			}
		} catch (_) {}
	}, 5_000);

	/* ------------------------------------------------------------------ */
	/* User-interaction listeners (passive, minimal inline work)            */
	/* ------------------------------------------------------------------ */
	document.addEventListener("click",      recordActivity,           { passive: true });
	document.addEventListener("keypress",   recordActivity,           { passive: true });
	document.addEventListener("touchstart", recordActivity,           { passive: true });
	document.addEventListener("mousemove",  recordActivityMousemove,  { passive: true });
	document.addEventListener("scroll",     recordActivityScroll,     { passive: true });

	// Pause tracking when tab hidden; resume when visible
	document.addEventListener("visibilitychange", function () {
		try {
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
		} catch (_) {}
	});

	/* ------------------------------------------------------------------ */
	/* Route-change tracking                                                */
	/* ------------------------------------------------------------------ */
	function onRouteChange() {
		try {
			if (!isLeader()) return;
			if (!frappe.session || !frappe.session.user) return;
			const routeArr = (frappe.get_route ? frappe.get_route() : []) || [];
			startNewSegment(routeArr);
			// Flush pending clicks from the previous route in idle time
			scheduleIdle(function () {
				processPendingClicks();
				sendClickBatch(1);
			});
		} catch (error) {
			console.error("Activity Tracker Error:", error);
		}
	}

	// Hook into Frappe router and capture the initial route once Frappe is ready
	if (typeof frappe !== "undefined") {
	    frappe.after_ajax(function () {
	        try {
	            if (!frappe.session || !frappe.session.user) return;
	
	            // ensure router exists
	            if (frappe.router && frappe.router.on) {
	                frappe.router.on("change", function () {
	                    onRouteChange();
	                });
	            }
	
	            // run once safely
	            if (typeof onRouteChange === "function") {
	                onRouteChange();
	            }
	
	        } catch (error) {
	            console.error("Activity Tracker Error:", error);
	        }
	    });
	}

	/* ------------------------------------------------------------------ */
	/* Batch flush – time logs                                              */
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
				setTimeout(function () { sendBatch(attempt + 1); }, attempt * 15_000);
			}
		}
	}

	setInterval(function () {
		try {
			if (!isLeader()) return;
			if (document.hidden) return;
			flushSegment(); // close current segment synchronously (timing accuracy)
			scheduleIdle(function () { sendBatch(1); }); // network call in idle time
		} catch (_) {}
	}, BATCH_INTERVAL_MS);

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
	 * Called only from idle-time processing – never from a live event handler.
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
		const routeArr = (typeof frappe !== "undefined" && frappe.get_route ? frappe.get_route() : []) || [];
		const { viewType, doctype, docname } = parseRoute(routeArr);
		return {
			view_type:   viewType,
			ref_doctype: doctype,
			docname:     docname,
			route:       routeToString(routeArr),
		};
	}

	/**
	 * Process a single pending click entry during idle time.
	 * Uses the captured click timestamp for accurate debounce comparison.
	 */
	function processClick(el, ts) {
		// Skip elements that have been removed from the DOM since the click
		if (!el.isConnected) return;
		if (isButtonIgnored(el)) return;

		const info = extractButtonInfo(el); // innerText read deferred to idle time
		if (!info.label) return;

		const ctx      = getClickContext();
		const clickKey = info.label + "|" + ctx.route;
		// Debounce: ignore if same label+route clicked within CLICK_DEBOUNCE_MS
		if (clickKey === lastClickKey && ts - lastClickTime < CLICK_DEBOUNCE_MS) return;
		lastClickKey  = clickKey;
		lastClickTime = ts;

		clickBuffer.push({
			label:       info.label,
			button_type: info.button_type,
			action_type: info.action_type,
			view_type:   ctx.view_type,
			ref_doctype: ctx.ref_doctype,
			docname:     ctx.docname,
			route:       ctx.route,
		});

		// Force-flush if buffer is nearing capacity
		if (clickBuffer.length >= MAX_BUFFER_SIZE) {
			scheduleIdle(function () { sendClickBatch(1); });
		}
	}

	/**
	 * Drain the pendingClickTargets queue during idle time.
	 * Errors per entry are swallowed so one bad element cannot block the rest.
	 * Drains by splicing the whole queue at once to avoid O(n²) shift() cost.
	 */
	function processPendingClicks() {
		if (!pendingClickTargets.length) return;
		const items = pendingClickTargets.splice(0, pendingClickTargets.length);
		for (let i = 0; i < items.length; i++) {
			try { processClick(items[i].el, items[i].ts); } catch (_) {}
		}
	}

	// Click listener: only capture element reference + timestamp, then exit.
	// All heavy DOM reads happen later in processPendingClicks() via idle callback.
	document.addEventListener("click", function (e) {
		const target = e.target.closest("button, .btn, .dropdown-item, .menu-item, .primary-action");
		if (target) {
			pendingClickTargets.push({ el: target, ts: Date.now() });
		}
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
				setTimeout(function () { sendClickBatch(attempt + 1); }, attempt * 15_000);
			}
		}
	}

	setInterval(function () {
		try {
			if (document.hidden) return;
			scheduleIdle(function () {
				processPendingClicks();
				sendClickBatch(1);
			});
		} catch (_) {}
	}, CLICK_BATCH_INTERVAL_MS);

	/* ------------------------------------------------------------------ */
	/* Page unload – best-effort flush via sendBeacon (single handler)     */
	/* ------------------------------------------------------------------ */
	window.addEventListener("beforeunload", function () {
		try {
			// Drain any pending click targets synchronously before the page closes
			processPendingClicks();
			flushSegment();

			if (logBuffer.length) {
				navigator.sendBeacon(
					"/api/method/" + API_METHOD,
					new Blob(
						[JSON.stringify({ logs: JSON.stringify(logBuffer) })],
						{ type: "application/json" }
					)
				);
			}

			if (clickBuffer.length) {
				navigator.sendBeacon(
					"/api/method/" + CLICK_API_METHOD,
					new Blob(
						[JSON.stringify({ logs: JSON.stringify(clickBuffer) })],
						{ type: "application/json" }
					)
				);
			}
		} catch (_) {}
	});
})();
