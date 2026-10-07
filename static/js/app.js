/* Room by Room — small progressive enhancements. Every action also works server-side. */
(function () {
  "use strict";

  function parseMoney(value) {
    if (!value) return null;
    var cleaned = String(value).replace(/[£,\s]/g, "");
    if (!/^-?\d*(\.\d{0,2})?$/.test(cleaned) || cleaned === "" || cleaned === "-") return NaN;
    return Math.round(parseFloat(cleaned) * 100);
  }
  function formatPence(p) {
    var sign = p < 0 ? "−" : "";
    p = Math.abs(p);
    return sign + "£" + (Math.floor(p / 100)).toLocaleString("en-GB") + "." + String(p % 100).padStart(2, "0");
  }

  // Confirmation prompts for destructive actions.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.hasAttribute("data-requires-saved") && formDirty) {
      // Reading requests are separate forms: never let them silently drop unsaved editor values.
      event.preventDefault();
      var note = form.querySelector("[data-unsaved-note]");
      if (note) { note.hidden = false; note.focus(); }
      return;
    }
    var message = (event.submitter && event.submitter.getAttribute("data-confirm")) || form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }
    if (form.hasAttribute("data-leaves-page") && warnUnsaved && formDirty && !leaveAllowed && !window.confirm(LEAVE_MESSAGE)) {
      event.preventDefault();  // e.g. signing out from a receipt with unsaved edits
      return;
    }
    leaveAllowed = true;  // Save, Confirm and other submissions never trigger the leave warning

    // Prevent double taps; the server is idempotent as well.
    var submitter = event.submitter;
    if (submitter && submitter.hasAttribute("data-submit-once")) {
      window.setTimeout(function () {
        submitter.disabled = true;
        submitter.setAttribute("aria-busy", "true");
      }, 0);
    }
  });

  // On phones, let the on-screen keyboard and the focused field own the screen:
  // sticky actions return to normal flow while a field is focused.
  var narrow = window.matchMedia("(max-width: 1023.98px)");
  document.addEventListener("focusin", function (event) {
    if (narrow.matches && event.target.matches("input:not([type=checkbox]):not([type=radio]):not([type=file]), select, textarea")) {
      document.body.classList.add("is-typing");
    }
  });
  document.addEventListener("focusout", function () {
    window.setTimeout(function () {
      var active = document.activeElement;
      if (!active || !active.matches("input, select, textarea")) document.body.classList.remove("is-typing");
    }, 0);
  });

  // Receipt upload: submit as soon as a file is chosen.
  document.querySelectorAll("[data-auto-submit]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (!input.files || !input.files.length) return;
      var form = input.form;
      form.querySelectorAll("input[type=file]").forEach(function (other) {
        if (other !== input) other.disabled = true;
      });
      var status = form.querySelector("[data-upload-status]");
      if (status) status.textContent = "Uploading " + input.files[0].name + "…";
      form.submit();
    });
  });

  // Track unsaved changes (typing, structural edits, programmatic fills) so nothing discards them.
  var formDirty = false;
  // Receipt review: show "Unsaved changes" and warn before leaving. Nothing is stored in the browser.
  var warnUnsaved = !!document.querySelector("form[data-warn-unsaved]");
  var leaveAllowed = false;  // set by a form submission (Save, Confirm…) or an accepted leave prompt
  var LEAVE_MESSAGE = "Leave this receipt? Your unsaved changes will be lost. To keep them, stay and press Save draft.";
  function onBeforeUnload(event) {
    if (!formDirty || leaveAllowed) return;
    event.preventDefault();
    event.returnValue = "";  // best effort: browsers show their own wording, and iOS may not ask at all
  }
  function markDirty() {
    if (formDirty) return;
    formDirty = true;
    if (!warnUnsaved) return;
    document.querySelectorAll("[data-unsaved-indicator]").forEach(function (el) { el.hidden = false; });
    var live = document.querySelector("[data-unsaved-live]");
    if (live) live.textContent = "Unsaved changes. Press Save draft to keep them.";
    window.addEventListener("beforeunload", onBeforeUnload);
  }
  if (warnUnsaved) {
    // In-app links warn on every browser (beforeunload alone is unreliable on iPhone).
    document.addEventListener("click", function (event) {
      if (!formDirty || leaveAllowed || event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      var link = event.target.closest("a[href]");
      if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
      var url = new URL(link.href, window.location.href);
      if (url.hash && url.origin === window.location.origin && url.pathname === window.location.pathname
          && url.search === window.location.search) return;  // in-page anchor
      if (window.confirm(link.getAttribute("data-leave-message") || LEAVE_MESSAGE)) leaveAllowed = true;
      else event.preventDefault();
    });
    // A page restored from the back/forward cache after a submission still holds its edits.
    window.addEventListener("pageshow", function () { leaveAllowed = false; });
  }
  document.querySelectorAll("form[data-editor-form]").forEach(function (form) {
    if (form.hasAttribute("data-dirty-on-load")) markDirty();  // any editor returned from a POST
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
  });

  // Receipt reading status: poll the job only; never touch form values.
  document.querySelectorAll("[data-reading]").forEach(function (panel) {
    var status = panel.getAttribute("data-status");
    if (status !== "queued" && status !== "processing") return;
    var url = panel.getAttribute("data-status-url");
    var started = Date.now();
    var label = panel.querySelector("[data-reading-label]");
    var attempt = panel.querySelector("[data-reading-attempt]");
    var stale = panel.querySelector("[data-reading-stale]");
    var done = panel.querySelector("[data-reading-done]");
    var dirtyNote = panel.querySelector("[data-reading-dirty]");
    var connection = panel.querySelector("[data-reading-connection]");
    // Connection trouble is never an extraction result: keep polling, never reload, never touch values.
    var failures = 0, timer = null, stopped = false;
    function schedule(ms) { window.clearTimeout(timer); timer = window.setTimeout(tick, ms); }
    function connectionLost() {
      failures += 1;
      if (failures >= 3 && connection) {
        connection.textContent = "Connection problem: can’t check the reading right now. Still trying. " +
          "What you’ve entered here stays on this page, and nothing is recorded.";
      }
      schedule(Math.min(5000 * Math.pow(2, failures - 1), 30000));  // 5, 10, 20, then every 30 s
    }
    function connectionBack() {
      failures = 0;
      if (connection) connection.textContent = "";
    }
    window.addEventListener("online", function () { if (failures && !stopped) schedule(0); });
    function fetchStatus() {
      var controller = window.AbortController ? new AbortController() : null;
      var abort = controller && window.setTimeout(function () { controller.abort(); }, 15000);
      return fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin", cache: "no-store",
                          signal: controller ? controller.signal : undefined })
        .then(function (r) {
          window.clearTimeout(abort);
          var json = (r.headers.get("Content-Type") || "").indexOf("application/json") === 0;
          if (!r.ok || !json) throw new Error("status unavailable");  // includes a sign-in redirect
          return r.json();
        }, function (error) { window.clearTimeout(abort); throw error; });
    }
    function tick() {
      if (Date.now() - started > 10 * 60 * 1000) {
        stopped = true;
        if (label) label.textContent = "Still not finished. Refresh later, or enter the details yourself.";
        return;
      }
      fetchStatus().then(function (state) {
        connectionBack();
        if (state.status === "queued" || state.status === "processing") {
          if (label) label.textContent = state.status === "queued" ? "Waiting to read the receipt…" : "Reading the receipt…";
          if (attempt) attempt.textContent = state.attempts ? "Attempt " + state.attempts + " of " + state.max_attempts + "." : "";
          if (stale) stale.hidden = !state.stale_queue;
          schedule(3000);
          return;
        }
        stopped = true;
        if (!formDirty) { window.location.reload(); return; }
        if (label) label.textContent = state.status === "failed" ? "Reading failed." : "Reading finished.";
        var spinner = panel.querySelector("[data-reading-spinner]");
        if (spinner) spinner.hidden = true;
        var progressNote = panel.querySelector("[data-reading-progress-note]");
        if (progressNote) progressNote.hidden = true;
        if (attempt) attempt.textContent = "";
        if (done) done.hidden = false;
        if (dirtyNote) dirtyNote.hidden = false;
      }, connectionLost);
    }
    schedule(2000);
  });
  document.querySelectorAll("[data-reading-reload]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      if (formDirty && !window.confirm("Show the stored reading? This reloads the page and replaces the changes you made here. To keep your changes, press Save draft instead.")) return;
      leaveAllowed = true;  // already confirmed above; no second prompt
      window.location.reload();
    });
  });

  // "Use one unitemised line": an explicit owner action, never automatic.
  document.querySelectorAll("[data-unitemised]").forEach(function (button) {
    button.addEventListener("click", function () {
      var form = button.closest("form");
      var line = form.querySelector("[data-line]");
      if (!line) return;
      line.querySelector("input[name$='-description']").value = "Unitemised purchase";
      line.querySelector("[data-line-type]").value = "unitemised";
      line.querySelector("select[name$='-category']").value = "other";
      line.querySelector("[data-line-amount]").value = button.getAttribute("data-unitemised");
      markDirty();
      line.querySelector("input[name$='-description']").dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

  // Purchase editor.
  document.querySelectorAll("[data-purchase-editor]").forEach(function (editor) {
    var form = editor.closest("form");
    var linesBox = editor.querySelector("[data-lines]");
    var lineTemplate = form.querySelector("template[data-line-template]");
    var allocTemplate = form.querySelector("template[data-alloc-template]");
    var totalInput = form.querySelector("[data-total]");

    function nextIndex(selector, attr, root) {
      var max = -1;
      root.querySelectorAll(selector).forEach(function (el) {
        var n = parseInt(el.getAttribute(attr), 10);
        if (!isNaN(n) && n > max) max = n;
      });
      return max + 1;
    }

    function relabel() {
      var lines = linesBox.querySelectorAll("[data-line]");
      lines.forEach(function (line, i) {
        var label = line.querySelector("[data-line-label]");
        if (label) label.textContent = "Line " + (i + 1);
        var remove = line.querySelector("[data-remove-line]");
        if (remove) remove.hidden = lines.length === 1;
      });
    }

    function syncAllocs(line) {
      var rows = line.querySelectorAll("[data-alloc]");
      rows.forEach(function (row) { row.classList.toggle("single", rows.length === 1); });
    }

    function reconcile() {
      var linesSum = 0, allocated = 0, bad = false, unassigned = false;
      linesBox.querySelectorAll("[data-line]").forEach(function (line) {
        var p = parseMoney(line.querySelector("[data-line-amount]").value);
        if (p === null) return;
        if (isNaN(p)) { bad = true; return; }
        linesSum += p;
        var rows = line.querySelectorAll("[data-alloc]");
        if (rows.length === 1) {
          if (rows[0].querySelector("[data-alloc-dest]").value) allocated += p; else unassigned = true;
        } else {
          rows.forEach(function (row) {
            var a = parseMoney(row.querySelector("[data-alloc-amount]").value);
            if (row.querySelector("[data-alloc-dest]").value && a !== null && !isNaN(a)) allocated += a;
            else unassigned = true;
          });
        }
      });
      var text = editor.querySelector("[data-alloc-text]");
      var status = editor.querySelector("[data-reconcile-status]");
      var box = editor.querySelector("[data-reconcile]");
      box.classList.remove("good", "bad");
      status.classList.remove("visually-hidden");
      var total = totalInput ? parseMoney(totalInput.value) : null;
      if (bad || (total !== null && isNaN(total))) {
        text.textContent = "—"; status.textContent = "Check the amounts"; box.classList.add("bad"); return;
      }
      var target = total === null ? linesSum : total;
      text.textContent = formatPence(allocated) + " of " + formatPence(target);
      if (linesSum === 0 && target === 0) {
        status.textContent = "Enter the item amounts"; return;
      }
      if (linesSum !== target) {
        var diff = target - linesSum;
        status.textContent = (diff > 0 ? formatPence(diff) + " of the total is not itemised yet" : "Items are " + formatPence(-diff) + " more than the total") + ". Add missing items or correct the amounts.";
        box.classList.add("bad");
      } else if (allocated !== target || unassigned) {
        status.textContent = "Choose a project for every item"; box.classList.add("bad");
      } else if (total === null) {
        status.textContent = "Purchase total " + formatPence(target) + ", calculated from the items";
        box.classList.add("good");
      } else {
        status.textContent = "Matches total"; status.classList.add("visually-hidden"); box.classList.add("good");
      }
    }

    function addLine(type) {
      var index = nextIndex("[data-line]", "data-index", linesBox);
      var html = lineTemplate.innerHTML.replace(/__L__/g, String(index));
      var holder = document.createElement("div");
      holder.innerHTML = html.trim();
      var line = holder.firstElementChild;
      if (type) {
        line.querySelector("details.line-more").open = true;
        line.querySelector("[data-line-type]").value = type;
        line.querySelector("select[name$='-category']").value = "other";
        line.querySelector("input[name$='-description']").value = type === "discount" ? "Discount" : "Delivery";
      }
      // Default the destination to the first line's choice.
      var first = linesBox.querySelector("[data-alloc-dest]");
      if (first && first.value) line.querySelector("[data-alloc-dest]").value = first.value;
      linesBox.appendChild(line);
      relabel();
      line.querySelector("input[name$='-description']").focus();
    }

    function assignUnassigned(button) {
      // Fill only lines whose single allocation has no destination; split lines and chosen projects stay.
      var box = button.closest("[data-bulk-assign]");
      var dest = box.querySelector("[data-bulk-dest]");
      var note = box.querySelector("[data-bulk-note]");
      if (!dest.value) { note.textContent = "Choose a project first."; dest.focus(); return; }
      var count = 0;
      linesBox.querySelectorAll("[data-line]").forEach(function (line) {
        var rows = line.querySelectorAll("[data-alloc]");
        if (rows.length !== 1) return;
        var select = rows[0].querySelector("[data-alloc-dest]");
        if (select.value) return;
        select.value = dest.value;
        count += 1;
      });
      var name = dest.options[dest.selectedIndex].text;
      note.textContent = count ? "Assigned " + count + (count === 1 ? " item" : " items") + " to " + name + ". Nothing is recorded until you confirm."
                               : "Every item already has a project.";
      if (count) { markDirty(); reconcile(); }
    }

    editor.addEventListener("click", function (event) {
      var target = event.target.closest("button");
      if (!target) return;
      if (target.hasAttribute("data-bulk-apply")) { event.preventDefault(); assignUnassigned(target); return; }
      if (target.matches("[data-add-line], [data-add-adjustment], [data-remove-line], [data-split], [data-remove-alloc]")) markDirty();
      if (target.hasAttribute("data-add-line")) { addLine(); }
      else if (target.hasAttribute("data-add-adjustment")) { addLine("shipping"); }
      else if (target.hasAttribute("data-remove-line")) {
        target.closest("[data-line]").remove(); relabel(); reconcile();
      } else if (target.hasAttribute("data-split")) {
        var line = target.closest("[data-line]");
        var allocs = line.querySelector("[data-allocs]");
        var li = line.getAttribute("data-index");
        var j = 0;
        allocs.querySelectorAll("[data-alloc-dest]").forEach(function (s) {
          var m = /-alloc-(\d+)-dest$/.exec(s.name);
          if (m) j = Math.max(j, parseInt(m[1], 10) + 1);
        });
        var html = allocTemplate.innerHTML.replace(/__L__/g, li).replace(/__A__/g, String(j));
        var holder = document.createElement("div");
        holder.innerHTML = html.trim();
        var row = holder.firstElementChild;
        allocs.appendChild(row);
        syncAllocs(line);
        reconcile();
        row.querySelector("[data-alloc-dest]").focus();
      } else if (target.hasAttribute("data-remove-alloc")) {
        var lineEl = target.closest("[data-line]");
        target.closest("[data-alloc]").remove();
        syncAllocs(lineEl);
        reconcile();
      }
    });
    form.addEventListener("input", reconcile);
    form.addEventListener("change", reconcile);
    relabel();
    reconcile();
    var errors = document.getElementById("editor-errors");
    if (errors) errors.focus();
  });
})();
