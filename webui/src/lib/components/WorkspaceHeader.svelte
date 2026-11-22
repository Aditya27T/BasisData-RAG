<script>
  export let activeView = "documents";
  export let theme = "light";
  export let onNavigate = () => {};
  export let onToggleTheme = () => {};

  const views = [
    { id: "documents", label: "Dokumen" },
    { id: "chat", label: "Tanya" },
    { id: "graph", label: "Knowledge graph" },
  ];
</script>

<header class="topbar">
  <a class="brand" href="/" aria-label="BasisData-RAG, buka workspace dokumen">
    <span>BasisData<span class="brand-light">-RAG</span></span>
  </a>
  <nav class="primary-nav" aria-label="Bagian workspace">
    {#each views as view (view.id)}
      <button
        type="button"
        class:active={activeView === view.id}
        aria-current={activeView === view.id ? "page" : undefined}
        onclick={() => onNavigate(view.id)}
      >{view.label}</button>
    {/each}
  </nav>
  <div class="top-actions">
    <a class="docs-link" href="/docs" target="_blank" rel="noreferrer">Swagger API</a>
    <button class="theme-button" type="button" onclick={onToggleTheme} aria-label={theme === "light" ? "Ganti ke tema gelap" : "Ganti ke tema terang"}>
      {theme === "light" ? "Tema gelap" : "Tema terang"}
    </button>
  </div>
</header>
