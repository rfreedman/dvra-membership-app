(function () {
  var MIN_PANEL_HEIGHT = 180;

  function fitScrollablePanels() {
    const panels = document.querySelectorAll(
      ".grid-page-body > .members-tabulator-wrap, .grid-page-body > .data-table-scroll"
    );
    if (!panels.length) return;
    const siteMain = document.querySelector(".site-main");
    if (!siteMain) return;

    // Size panels against the visible main area (not the window), so a short
    // viewport can scroll .site-main to bring the table into view.
    const mainRect = siteMain.getBoundingClientRect();
    const pad = parseFloat(window.getComputedStyle(siteMain).paddingBottom || "0") || 0;

    for (let i = 0; i < panels.length; i++) {
      const panel = panels[i];
      panel.style.height = "";
      const rect = panel.getBoundingClientRect();
      let gap = 12;
      if (panel.classList.contains("data-table-scroll")) {
        gap = 44;
      } else if (panel.classList.contains("members-tabulator-wrap")) {
        gap = 8;
      }
      const available = Math.floor(mainRect.bottom - rect.top - pad - gap);
      const target = Math.max(MIN_PANEL_HEIGHT, available);
      panel.style.height = target + "px";
      if (panel.classList.contains("members-tabulator-wrap")) {
        const tabulatorRoot = panel.querySelector(".tabulator");
        if (tabulatorRoot && tabulatorRoot.tabulator && typeof tabulatorRoot.tabulator.redraw === "function") {
          tabulatorRoot.tabulator.redraw(true);
        }
      }
    }
  }

  window.addEventListener("resize", fitScrollablePanels);
  document.addEventListener("DOMContentLoaded", function () {
    fitScrollablePanels();
    window.requestAnimationFrame(fitScrollablePanels);
    document.querySelectorAll("select[data-submit-on-change]").forEach(function (el) {
      el.addEventListener("change", function () {
        if (el.form) el.form.requestSubmit();
      });
    });
  });
})();
