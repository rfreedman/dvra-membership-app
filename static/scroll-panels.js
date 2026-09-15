(function () {
  function fitScrollablePanels() {
    const panels = document.querySelectorAll(
      ".grid-page-body > .members-tabulator-wrap, .grid-page-body > .data-table-scroll, .standard-page-scroll"
    );
    if (!panels.length) return;
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    const siteMain = document.querySelector(".site-main");
    let pad = 0;
    if (siteMain) pad = parseFloat(window.getComputedStyle(siteMain).paddingBottom || "0") || 0;
    for (let i = 0; i < panels.length; i++) {
      const panel = panels[i];
      const rect = panel.getBoundingClientRect();
      let gap = 12;
      if (panel.classList.contains("data-table-scroll")) {
        gap = 44;
      } else if (panel.classList.contains("standard-page-scroll")) {
        gap = 12;
      } else if (panel.classList.contains("members-tabulator-wrap")) {
        gap = 8;
      }
      const target = Math.max(180, Math.floor(vh - rect.top - pad - gap));
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
