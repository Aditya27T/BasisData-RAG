<script>
  import KnowledgeGraphInline from "../components/KnowledgeGraphInline.svelte";
  export let controller;
  export let workspace = "docs";
  let draft = "";

  async function submit(event) {
    event.preventDefault();
    if (!draft.trim() || $controller.busy) return;
    const question = draft.trim();
    draft = "";
    await controller.send(question, workspace);
  }

  function sourceDetails(source) {
    return [source.page_label, ...(source.headings || [])].filter(Boolean).join(" · ");
  }
</script>

<section class="chat-panel panel" aria-labelledby="chat-heading">
  <div class="panel-heading chat-heading">
    <div>
      <p class="eyebrow">TANYA JAWAB</p>
      <h2 id="chat-heading">Bertanya dari dokumen</h2>
    </div>
    <span class="workspace-tag">{workspace}</span>
  </div>

  {#if $controller.messages.length === 0}
    <div class="empty-state chat-empty">
      <h3>Mulai dengan pertanyaan tentang koleksi</h3>
      <p>Jawaban memakai konteks dari dokumen yang sudah berhasil di-ingest.</p>
    </div>
  {:else}
    <div class="chat-history" role="log" aria-live="polite" aria-label="Percakapan">
      {#each $controller.messages as message (message.id)}
        <article class={`message ${message.role}`}>
          <p class="message-label">{message.role === "user" ? "Anda" : "BasisData-RAG"}</p>
          <p class="message-text">{message.text}</p>
          {#if message.role === "assistant" && message.sources?.length}
            <div class="sources-block">
              <p class="sources-title">Sumber</p>
              <ul>
                {#each message.sources as source, index (`${message.id}-${source.chunk_id || index}`)}
                  <li>
                    <span class="source-index">{source.reference_id || index + 1}</span>
                    <span>{source.file_path}</span>
                    {#if sourceDetails(source)}<small>{sourceDetails(source)}</small>{/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/if}
          {#if message.role === "assistant" && message.graph?.edges?.length}
            <KnowledgeGraphInline graph={message.graph} />
          {/if}
        </article>
      {/each}
    </div>
  {/if}
  {#if $controller.progressLog.length}
    <ol class="progress-log" aria-label="Tahap proses pertanyaan" aria-live="polite">
      {#each $controller.progressLog as entry (entry.id)}
        <li><span>{entry.kind}</span>{entry.message}</li>
      {/each}
    </ol>
  {/if}

  {#if $controller.error}<div class="notice error-notice" role="alert">{$controller.error}</div>{/if}
  <form class="chat-form" onsubmit={submit}>
    <label for="chat-question">Pertanyaan</label>
    <textarea
      id="chat-question"
      bind:value={draft}
      rows="3"
      maxlength="4000"
      placeholder="Contoh: Apa yang dijelaskan dokumen tentang objek database?"
      disabled={$controller.busy}
    ></textarea>
    <div class="chat-submit-row">
      <span class="field-hint" role="status" aria-live="polite">{$controller.stage || "Jawaban yang tidak didukung sumber akan ditolak."}</span>
      <button class="button primary" type="submit" disabled={$controller.busy || !draft.trim()}>
        {$controller.busy ? "Sedang diproses…" : "Kirim pertanyaan"}
      </button>
    </div>
  </form>
</section>
