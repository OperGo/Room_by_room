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
    var message = form.getAttribute("data-confirm");
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

  // Purchase editor.
  document.querySelectorAll("[data-purchase-editor]").forEach(function (editor) {
    var form = editor.closest("form");
    var linesBox = editor.querySelector("[data-lines]");
    var lineTemplate = form.querySelector("template[data-line-template]");
    var allocTemplate = form.querySelector("template[data-alloc-template]");
    var totalInput = editor.querySelector("[data-total]");

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
      var sum = 0, bad = false;
      linesBox.querySelectorAll("[data-line-amount]").forEach(function (input) {
        var p = parseMoney(input.value);
        if (p === null) return;
        if (isNaN(p)) { bad = true; return; }
        sum += p;
      });
      var out = editor.querySelector("[data-lines-sum]");
      var status = editor.querySelector("[data-reconcile-status]");
      var box = editor.querySelector("[data-reconcile]");
      out.textContent = bad ? "check amounts" : formatPence(sum);
      var total = parseMoney(totalInput.value);
      box.classList.remove("good", "bad");
      if (total === null || bad) { status.textContent = total === null ? "Total will match the lines" : ""; return; }
      if (isNaN(total)) { status.textContent = "Check the total"; box.classList.add("bad"); return; }
      var diff = total - sum;
      if (diff === 0) { status.textContent = "Matches total"; box.classList.add("good"); }
      else { status.textContent = (diff > 0 ? formatPence(diff) + " not yet itemised" : formatPence(-diff) + " more than total"); box.classList.add("bad"); }
    }

    function addLine(type) {
      var index = nextIndex("[data-line]", "data-index", linesBox);
      var html = lineTemplate.innerHTML.replace(/__L__/g, String(index));
      var holder = document.createElement("div");
      holder.innerHTML = html.trim();
      var line = holder.firstElementChild;
      if (type) {
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
        row.querySelector("[data-alloc-dest]").focus();
      } else if (target.hasAttribute("data-remove-alloc")) {
        var lineEl = target.closest("[data-line]");
        target.closest("[data-alloc]").remove();
        syncAllocs(lineEl);
      }
    });
    editor.addEventListener("input", reconcile);
    relabel();
    reconcile();
    var errors = document.getElementById("editor-errors");
    if (errors) errors.focus();
  });
})();
