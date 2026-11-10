<script>
  import { onMount } from "svelte";
  import WorkspaceHeader from "./lib/components/WorkspaceHeader.svelte";
  import ChatView from "./lib/views/ChatView.svelte";
  import DocumentsView from "./lib/views/DocumentsView.svelte";
  import GraphView from "./lib/views/GraphView.svelte";
  import { createChatController } from "./lib/state/chat.js";
  import { createDocumentsController } from "./lib/state/documents.js";
  import { createGraphController } from "./lib/state/graph.js";

  let activeView = "documents";
  let workspace = "docs";
  let theme = "light";
  const documentsController = createDocumentsController();
  const chatController = createChatController();
  const graphController = createGraphController();

  onMount(() => {
    theme = localStorage.getItem("basisdata-rag-theme") || "light";
    applyTheme();
    documentsController.load(workspace);
  });

  $: pageTitle = activeView === "documents"
    ? "Dokumen"
    : activeView === "chat"
      ? "Tanya dokumen"
      : "Knowledge graph";

  function applyTheme() {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("basisdata-rag-theme", theme);
  }

  function toggleTheme() {
    theme = theme === "light" ? "dark" : "light";
    applyTheme();
  }

  async function navigate(view) {
    activeView = view;
    if (view === "documents") await documentsController.load(workspace);
    if (view === "graph") await graphController.load(workspace);
  }

  async function loadWorkspace(event) {
    event.preventDefault();
    if (activeView === "documents") await documentsController.load(workspace);
    if (activeView === "graph") await graphController.load(workspace);
  }
</script>

<svelte:head>
  <title>BasisData-RAG | Workspace dokumen</title>
  <meta name="description" content="Ingest, cari, dan jelajahi knowledge graph dokumen." />
</svelte:head>

<div class="app-shell">
  <WorkspaceHeader {activeView} {theme} onNavigate={navigate} onToggleTheme={toggleTheme} />

  <main>
    <div class="workspace-row">
      <div>
        <p class="eyebrow">WORKSPACE</p>
        <h1>{pageTitle}</h1>
      </div>
      <form class="workspace-form" onsubmit={loadWorkspace}>
        <label for="workspace-name">Nama workspace</label>
        <div class="workspace-controls">
          <input id="workspace-name" bind:value={workspace} autocomplete="off" />
          <button class="button secondary" type="submit">Muat</button>
        </div>
      </form>
    </div>

    {#if activeView === "documents"}
      <DocumentsView controller={documentsController} {workspace} />
    {:else if activeView === "chat"}
      <ChatView controller={chatController} {workspace} />
    {:else}
      <GraphView controller={graphController} {workspace} />
    {/if}
  </main>

  <footer class="app-footer">
    <span>BasisData-RAG</span>
    <span>API lokal · <a href="/docs" target="_blank" rel="noreferrer">Swagger</a></span>
  </footer>
</div>
