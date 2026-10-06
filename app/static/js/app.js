// Vanilla JS only, no framework, no external dependency.

document.addEventListener("DOMContentLoaded", function () {
  // Mobile sidebar toggle
  var toggle = document.querySelector("[data-sidebar-toggle]");
  var sidebar = document.querySelector(".sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
  }

  // Generic confirm dialogs for destructive/irreversible actions
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("submit", function (e) {
      var msg = el.getAttribute("data-confirm");
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });
  document.querySelectorAll("a[data-confirm-link]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      var msg = el.getAttribute("data-confirm-link");
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });

  // Auto-dismiss flash alerts
  document.querySelectorAll("[data-flash]").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.4s ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 450);
    }, 5000);
  });

  // Debounced live filter for tables marked with data-live-filter
  document.querySelectorAll("[data-live-filter-form]").forEach(function (form) {
    var timer = null;
    form.querySelectorAll("input, select").forEach(function (input) {
      input.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () { form.requestSubmit(); }, 400);
      });
      if (input.tagName === "SELECT") {
        input.addEventListener("change", function () { form.requestSubmit(); });
      }
    });
  });

  // Balance / variance live preview on physical verification form
  var physicalInput = document.querySelector("[data-physical-qty]");
  if (physicalInput) {
    var expected = parseFloat(physicalInput.getAttribute("data-expected") || "0");
    var out = document.querySelector("[data-variance-out]");
    var reasonField = document.querySelector("[data-reason-field]");
    var tolerance = parseFloat(physicalInput.getAttribute("data-tolerance") || "1");
    function update() {
      var val = parseFloat(physicalInput.value);
      if (isNaN(val)) { out.textContent = "--"; return; }
      var variance = val - expected;
      var pct = expected > 0 ? (variance / expected) * 100 : (variance !== 0 ? 100 : 0);
      var sign = variance > 0 ? "+" : "";
      out.textContent = sign + variance.toFixed(3) + " (" + sign + pct.toFixed(2) + "%)";
      out.style.color = Math.abs(pct) > tolerance ? "#a3241f" : "#1b7a4d";
      if (reasonField) {
        reasonField.style.display = Math.abs(pct) > tolerance ? "flex" : "none";
      }
    }
    physicalInput.addEventListener("input", update);
    update();
  }

  // Dynamic container-size-aware quantity hint on usage form
  var useInput = document.querySelector("[data-use-qty]");
  if (useInput) {
    var available = parseFloat(useInput.getAttribute("data-available") || "0");
    var remainOut = document.querySelector("[data-remaining-out]");
    useInput.addEventListener("input", function () {
      var val = parseFloat(useInput.value);
      if (isNaN(val)) { remainOut.textContent = "--"; return; }
      var remaining = available - val;
      remainOut.textContent = remaining.toFixed(3);
      remainOut.style.color = remaining < 0 ? "#a3241f" : "inherit";
    });
  }
});
