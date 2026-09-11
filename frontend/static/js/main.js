// Dashboard and Upload Interaction Handler

document.addEventListener("DOMContentLoaded", () => {
  const fileInput = document.getElementById("file-input");
  const uploadZone = document.getElementById("upload-zone");
  const uploadForm = document.getElementById("upload-form");
  const uploadText = document.getElementById("upload-text");
  const loadingOverlay = document.getElementById("loading-overlay");
  const statusMessage = document.getElementById("status-message");

  if (fileInput && uploadZone) {
    // Drag & Drop handlers
    uploadZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadZone.classList.add("dragover");
    });

    uploadZone.addEventListener("dragleave", () => {
      uploadZone.classList.remove("dragover");
    });

    uploadZone.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadZone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        updateFileLabel(fileInput.files[0].name);
      }
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files.length > 0) {
        updateFileLabel(fileInput.files[0].name);
      }
    });
  }

  function updateFileLabel(name) {
    if (uploadText) {
      uploadText.textContent = `Selected: ${name}`;
    }
  }

  // Handle upload submission with API
  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      if (!fileInput.files || fileInput.files.length === 0) {
        showError("Please select a file to upload.");
        return;
      }

      const file = fileInput.files[0];
      const docTypeSelect = document.getElementById("document-type-select");
      const docType = docTypeSelect ? docTypeSelect.value : "invoice";

      const formData = new FormData();
      formData.append("file", file);
      formData.append("document_type", docType);

      // Show spinner overlay
      if (loadingOverlay) loadingOverlay.style.display = "flex";
      clearMessage();

      try {
        const response = await fetch("/api/v1/documents/process", {
          method: "POST",
          body: formData,
        });

        const result = await response.json();

        if (!response.ok) {
          const errMsg = result.error?.message || "Document processing failed.";
          const errCode = result.error?.code || "ERROR";
          showError(`[${errCode}] ${errMsg}`);
          return;
        }

        // Success - navigate to the detail view for this document
        const record = result.data;
        window.location.href = `/documents/${encodeURIComponent(record.document_name)}`;
      } catch (err) {
        showError(`Network or connection error: ${err.message}`);
      } finally {
        if (loadingOverlay) loadingOverlay.style.display = "none";
      }
    });
  }

  function showError(msg) {
    if (statusMessage) {
      statusMessage.className = "alert alert-error";
      statusMessage.textContent = msg;
      statusMessage.style.display = "block";
    }
  }

  function clearMessage() {
    if (statusMessage) {
      statusMessage.style.display = "none";
      statusMessage.textContent = "";
    }
  }
});
