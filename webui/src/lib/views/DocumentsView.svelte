<script>

  export let controller;
  export let workspace = "docs";
  let selectedFile;
  let forceReingest = false;
  let fileInput;


  async function submitUpload(event) {
    event.preventDefault();
    if (!selectedFile) return;
    await controller.upload(selectedFile, workspace, forceReingest);
    selectedFile = undefined;
    if (fileInput) fileInput.value = "";
  }

  function statusLabel(status) {
    const labels = {
      processed: "Selesai",
      processing: "Diproses",
      parsing: "Diproses",
      pending: "Menunggu",
      failed: "Gagal",
      queued: "Menunggu antrean",
    };
    return labels[String(status || "").toLowerCase()] || status || "Tidak diketahui";
  }

  function statusClass(status) {
    const value = String(status || "").toLowerCase();
    if (value === "processed" || value === "completed") return "success";
    if (value === "failed") return "error";
    if (["processing", "parsing", "queued", "pending"].includes(value)) return "working";
    return "neutral";
  }
</script>

<section class="documents-layout" aria-labelledby="documents-heading">
  <div class="document-list-panel panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">KOLEKSI</p>
        <h2 id="documents-heading">Dokumen workspace</h2>
      </div>
      <button class="button secondary" type="button" onclick={() => controller.load(workspace)} disabled={$controller.loading}>
        {$controller.loading ? "Memuat…" : "Perbarui daftar"}
      </button>
    </div>

    {#if $controller.error}
      <div class="notice error-notice" role="alert">
        <strong>Daftar dokumen gagal dimuat.</strong>
        <span>{$controller.error}</span>
      </div>
    {:else if $controller.loading && $controller.documents.length === 0}
      <p class="state-message" role="status">Memuat dokumen workspace…</p>
    {:else if $controller.documents.length === 0}
      <div class="empty-state">
        <h3>Belum ada dokumen</h3>
        <p>Pilih file di panel ingest untuk menambahkan sumber ke workspace ini.</p>
      </div>
    {:else}
      <ul class="document-list">
        {#each $controller.documents as document (document.doc_id)}
          <li class="document-row">
            <div class="file-glyph" aria-hidden="true">{(document.file_name.split(".").pop() || "DOC").slice(0, 4).toUpperCase()}</div>
            <div class="document-meta">
              <span class="document-name">{document.file_name}</span>
              <span class="document-id">{document.doc_id}</span>
              {#if document.message}<span class="document-message">{document.message}</span>{/if}
            </div>
            <span class={`status ${statusClass(document.status)}`}>{statusLabel(document.status)}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  <aside class="ingest-panel panel" aria-labelledby="ingest-heading">
    <p class="eyebrow">TAMBAHKAN SUMBER</p>
    <h2 id="ingest-heading">Ingest dokumen</h2>
    <p class="panel-copy">File diproses ke workspace <strong>{workspace}</strong>.</p>
    <form class="ingest-form" onsubmit={submitUpload}>
      <label class="file-field" for="document-file">
        <span>Pilih file</span>
        <input
          bind:this={fileInput}
          id="document-file"
          type="file"
          accept=".md,.markdown,.txt,.pdf,.docx,.pptx,.doc,.ppt"
          onchange={(event) => (selectedFile = event.currentTarget.files?.[0])}
        />
      </label>
      <p class="field-hint">Markdown, TXT, PDF, DOCX, PPTX, DOC, atau PPT.</p>
      {#if selectedFile}<p class="selected-file">Dipilih: {selectedFile.name}</p>{/if}
      <label class="checkbox-row">
        <input type="checkbox" bind:checked={forceReingest} />
        <span>Proses ulang jika file sudah pernah di-ingest</span>
      </label>
      <button class="button primary upload-button" type="submit" disabled={!selectedFile || $controller.uploadBusy}>
        {$controller.uploadBusy ? "Sedang diproses…" : "Mulai ingest"}
      </button>
    </form>

    {#if $controller.ingestionJob}
      <div class={`notice ${$controller.ingestionJob.status === "failed" ? "error-notice" : "job-notice"}`} role="status" aria-live="polite">
        <strong>{$controller.ingestionJob.filename}: {statusLabel($controller.ingestionJob.status)}</strong>
        {#if $controller.ingestionJob.result?.message}<span>{$controller.ingestionJob.result.message}</span>{/if}
        {#if $controller.ingestionJob.error}<span>{$controller.ingestionJob.error}</span>{/if}
      </div>
    {/if}
    {#if $controller.ingestionLogs.length}
      <ol class="progress-log" aria-label="Log ingest terbaru" aria-live="polite">
        {#each $controller.ingestionLogs.slice(-8) as entry (entry.sequence)}
          <li><span>{entry.kind}</span>{entry.message}</li>
        {/each}
      </ol>
    {/if}
  </aside>
</section>
