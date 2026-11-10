<script>
  export let controller;
  export let workspace = "docs";
  $: selectedNode = $controller.nodes.find((node) => node.id === $controller.selectedNodeId);
  $: selectedEdges = selectedNode
    ? $controller.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).slice(0, 8)
    : [];

  function select(node) {
    controller.selectNode(node.id);
  }

  function prominentNodeIds(nodes, edges) {
    const degree = new Map(nodes.map((node) => [node.id, 0]));
    for (const edge of edges) {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    }
    return new Set(
      [...degree.entries()]
        .sort((left, right) => right[1] - left[1])
        .slice(0, 8)
        .map(([id]) => id),
    );
  }

  $: labelIds = prominentNodeIds($controller.nodes, $controller.edges);

</script>

<section class="graph-section" aria-labelledby="graph-heading">
  <div class="panel graph-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">ENTITAS DAN RELASI</p>
        <h2 id="graph-heading">Peta knowledge graph</h2>
      </div>
      <button class="button secondary" type="button" onclick={() => controller.load(workspace)} disabled={$controller.busy}>
        {$controller.busy ? "Memuat…" : "Muat ulang graph"}
      </button>
    </div>
    {#if $controller.error}
      <div class="notice error-notice" role="alert">{$controller.error}</div>
    {:else if $controller.busy && $controller.nodes.length === 0}
      <p class="state-message" role="status" aria-live="polite">{$controller.stage || "Membaca graph…"}</p>
    {:else if $controller.nodes.length === 0}
      <div class="empty-state">
        <h3>Graph masih kosong</h3>
        <p>Ingest dokumen dengan Neo4j aktif agar entitas dan relasinya muncul di sini.</p>
      </div>
    {:else}
      <div class="graph-summary">
        <span><strong>{$controller.nodes.length}</strong> entitas</span>
        <span><strong>{$controller.edges.length}</strong> relasi</span>
        {#if $controller.truncated}<span class="field-hint">Tampilan dibatasi agar graph tetap terbaca.</span>{/if}
      </div>
      <p class="field-hint graph-help">Label menyorot node paling terhubung. Pilih titik untuk detail; geser area grafik ke samping pada layar sempit.</p>
      {#if $controller.progressLog.length}
        <ol class="progress-log" aria-label="Tahap baca knowledge graph" aria-live="polite">
          {#each $controller.progressLog as entry (entry.id)}
            <li><span>{entry.kind}</span>{entry.message}</li>
          {/each}
        </ol>
      {/if}
      {#if $controller.busy}<p class="stream-status" role="status" aria-live="polite">{$controller.stage}</p>{/if}
      <div class="graph-layout">
        <div class="graph-scroll" role="region" aria-label="Knowledge graph, area dapat digulir horizontal pada layar kecil">
          <div class="graph-canvas">
            <svg class="graph-svg" viewBox="0 0 780 560" aria-hidden="true" focusable="false">
              <g class="edges">
                {#each $controller.edges as edge (edge.id)}
                  {#if $controller.positions[edge.source] && $controller.positions[edge.target]}
                    <line
                      x1={$controller.positions[edge.source].x}
                      y1={$controller.positions[edge.source].y}
                      x2={$controller.positions[edge.target].x}
                      y2={$controller.positions[edge.target].y}
                    />
                  {/if}
                {/each}
              </g>
            </svg>
            <div class="graph-node-layer">
              {#each $controller.nodes as node (node.id)}
                {#if $controller.positions[node.id]}
                  <button
                    class="graph-node"
                    class:selected={$controller.selectedNodeId === node.id}
                    type="button"
                    style={`--node-x:${$controller.positions[node.id].x}px; --node-y:${$controller.positions[node.id].y}px;`}
                    aria-pressed={$controller.selectedNodeId === node.id}
                    aria-label={`Pilih ${node.label}, ${node.type}`}
                    title={`${node.label}, ${node.type}`}
                    onclick={() => select(node)}
                  >
                    <span class={labelIds.has(node.id) || $controller.selectedNodeId === node.id ? "node-label" : "sr-only"}>
                      {node.label.length > 22 ? `${node.label.slice(0, 20)}…` : node.label}
                    </span>
                  </button>
                {/if}
              {/each}
            </div>
          </div>
        </div>
        <aside class="node-detail" aria-live="polite" aria-label="Detail entitas yang dipilih">
          {#if selectedNode}
            <p class="eyebrow">ENTITAS DIPILIH</p>
            <h3>{selectedNode.label}</h3>
            <p class="node-type">{selectedNode.type}</p>
            <p>{selectedNode.description || "Tidak ada deskripsi tersimpan."}</p>
            <p class="node-id">{selectedNode.id}</p>
            {#if selectedEdges.length}
              <h4>Relasi</h4>
              <ul class="relation-list">
                {#each selectedEdges as edge (edge.id)}<li>{edge.label || "terkait"}</li>{/each}
              </ul>
            {/if}
          {:else}
            <p class="field-hint">Pilih node untuk membaca detail.</p>
          {/if}
        </aside>
      </div>
    {/if}
  </div>
</section>
