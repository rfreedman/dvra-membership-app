<script>
(function () {
  var UNSAVED_MSG = "You have unsaved changes to this member. Leave without saving?";
  var LEAVE_MSG = "You have unsaved changes to this member. Leave this page without saving?";

  function formSnapshot(form) {
    var fd = new FormData(form);
    var pairs = [];
    fd.forEach(function (val, key) {
      pairs.push(key + "\0" + val);
    });
    pairs.sort();
    return pairs.join("\n");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("member-edit-form");
    var saveBtn = document.getElementById("member-edit-save");
    var deleteForm = document.getElementById("member-delete-form");
    if (!form || !saveBtn) {
      return;
    }

    var baseline = formSnapshot(form);
    var allowLeaveWithoutPrompt = false;
    var forceDeleteSubmit = false;

    function isDirty() {
      return formSnapshot(form) !== baseline;
    }

    function syncSaveState() {
      saveBtn.disabled = !isDirty();
    }

    form.addEventListener("input", syncSaveState);
    form.addEventListener("change", syncSaveState);
    syncSaveState();

    form.addEventListener("submit", function () {
      allowLeaveWithoutPrompt = true;
    });

    window.addEventListener("beforeunload", function (e) {
      if (allowLeaveWithoutPrompt || !isDirty()) {
        return;
      }
      e.preventDefault();
      e.returnValue = LEAVE_MSG;
      return LEAVE_MSG;
    });

    document.querySelectorAll(".member-detail-page a.member-edit-leave-risk").forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href) {
        return;
      }
      a.addEventListener("click", function (e) {
        if (!isDirty()) {
          return;
        }
        e.preventDefault();
        if (!window.confirm(UNSAVED_MSG)) {
          return;
        }
        allowLeaveWithoutPrompt = true;
        window.location.href = href;
      });
    });

    if (deleteForm) {
      var deleteMsg = deleteForm.getAttribute("data-confirm-delete") || "Delete this member and all payments?";
      deleteForm.addEventListener("submit", function (e) {
        if (forceDeleteSubmit) {
          return;
        }
        e.preventDefault();
        if (!window.confirm(deleteMsg)) {
          return;
        }
        allowLeaveWithoutPrompt = true;
        forceDeleteSubmit = true;
        deleteForm.submit();
      });
    }
  });
})();
</script>
