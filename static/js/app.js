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
  function markDirty() { formDirty = true; }
  document.querySelectorAll("form[data-editor-form]").forEach(function (form) {
    if (form.hasAttribute("data-dirty-on-load")) markDirty();  // e.g. a returned save conflict
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
    function tick() {
      if (Date.now() - started > 10 * 60 * 1000) {
        if (label) label.textContent = "Still not finished. Refresh later, or enter the details yourself.";
        return;
      }
      fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin", cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (state) {
          if (!state) { window.setTimeout(tick, 5000); return; }
          if (state.status === "queued" || state.status === "processing") {
            if (label) label.textContent = state.status === "queued" ? "Waiting to read the receipt…" : "Reading the receipt…";
            if (attempt) attempt.textContent = state.attempts ? "Attempt " + state.attempts + " of " + state.max_attempts + "." : "";
            if (stale) stale.hidden = !state.stale_queue;
            window.setTimeout(tick, 3000);
            return;
          }
          if (!formDirty) { window.location.reload(); return; }
          if (label) label.textContent = state.status === "failed" ? "Reading failed." : "Reading finished.";
          var spinner = panel.querySelector("[data-reading-spinner]");
          if (spinner) spinner.hidden = true;
          var progressNote = panel.querySelector("[data-reading-progress-note]");
          if (progressNote) progressNote.hidden = true;
          if (attempt) attempt.textContent = "";
          if (done) done.hidden = false;
          if (dirtyNote) dirtyNote.hidden = false;
        })
        .catch(function () { window.setTimeout(tick, 5000); });
    }
    window.setTimeout(tick, 2000);
  });
  document.querySelectorAll("[data-reading-reload]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      if (formDirty && !window.confirm("Show the stored reading? This reloads the page and replaces the changes you made here. To keep your changes, press Save draft instead.")) return;
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

    editor.addEventListener("click", function (event) {
      var target = event.target.closest("button");
      if (!target) return;
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
