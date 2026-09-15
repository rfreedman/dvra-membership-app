(function () {
  function syncOne(root) {
    const base = root.getAttribute("data-export-base") || "";
    const path = root.getAttribute("data-export-path") || "";
    const prefix = root.getAttribute("data-export-prefix") || "";
    if (!path || !prefix) return;
    ["xlsx", "csv", "pdf"].forEach(function (ext) {
      const link = document.getElementById(prefix + ext);
      if (link) link.href = base + path + "." + ext;
    });
  }

  function syncAll() {
    document.querySelectorAll(".export-links[data-export-path]").forEach(syncOne);
  }

  window.dvraSyncExportLinks = syncAll;
  document.addEventListener("DOMContentLoaded", syncAll);
})();
