(function () {
  const table = document.getElementById("payments-report-table");
  if (!table) return;

  function naturalCellWidth(el) {
    const sw = el.scrollWidth;
    const cw = el.clientWidth;
    if (sw > cw + 2) return sw;
    const st = window.getComputedStyle(el);
    const span = document.createElement("span");
    span.style.cssText =
      "position:fixed;left:-9999px;top:0;white-space:nowrap;visibility:hidden;" +
      "font-family:" + st.fontFamily + ";font-size:" + st.fontSize +
      ";font-weight:" + st.fontWeight + ";font-style:" + st.fontStyle +
      ";letter-spacing:" + st.letterSpacing + ";";
    span.textContent = (el.textContent || "").replace(/\s+/g, " ").trim();
    document.body.appendChild(span);
    const tw = span.offsetWidth;
    document.body.removeChild(span);
    const pad = (parseFloat(st.paddingLeft) || 0) + (parseFloat(st.paddingRight) || 0);
    return Math.ceil(Math.max(sw, tw + pad));
  }

  function autofitPaymentsReportColumns() {
    const cols = table.querySelectorAll("colgroup col");
    const n = cols.length;
    if (!n) return;
    for (let i = 0; i < n; i++) {
      let max = 0;
      const sel = "thead tr:first-child > *:nth-child(" + (i + 1) + "), tbody tr > *:nth-child(" + (i + 1) + ")";
      const cells = table.querySelectorAll(sel);
      for (let c = 0; c < cells.length; c++) {
        max = Math.max(max, naturalCellWidth(cells[c]));
      }
      cols[i].style.width = Math.max(48, max + 6) + "px";
    }
    table.classList.add("payments-report-table--columns-sized");
  }

  function installPaymentsReportColumnResizers() {
    const cols = table.querySelectorAll("colgroup col");
    const headers = table.querySelectorAll("thead tr th");
    const minW = 48;
    headers.forEach(function (th, i) {
      const handle = document.createElement("span");
      handle.className = "col-resize-handle";
      handle.setAttribute("role", "separator");
      handle.setAttribute("aria-orientation", "vertical");
      handle.setAttribute("aria-label", "Resize column");
      th.appendChild(handle);
      handle.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const col = cols[i];
        if (!col) return;
        const startX = ev.pageX;
        const startW = col.getBoundingClientRect().width;
        function onMove(ev2) {
          const w = Math.max(minW, startW + (ev2.pageX - startX));
          col.style.width = Math.round(w) + "px";
        }
        function onUp() {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        }
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  }

  function initPaymentsReportTableLayout() {
    requestAnimationFrame(function () {
      autofitPaymentsReportColumns();
      installPaymentsReportColumnResizers();
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPaymentsReportTableLayout);
  } else {
    initPaymentsReportTableLayout();
  }
})();
