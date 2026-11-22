<script>
  export let graph;
  let selectedId = graph.nodes[0]?.id || "";

  function prominentNodeIds(nodes, edges) {
    const degree = new Map(nodes.map((node) => [node.id, 0]));
    for (const edge of edges) {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    }
    return new Set([...degree.entries()].sort((left, right) => right[1] - left[1]).slice(0, 8).map(([id]) => id));
  }

  $: labelIds = prominentNodeIds(graph.nodes, graph.edges);
  $: selectedNode = graph.nodes.find((node) => node.id === selectedId);
  $: selectedEdges = selectedNode
    ? graph.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).slice(0, 5)
    : [];
</script>

{#if graph?.nodes?.length && graph?.edges?.length}
  <section class="inline-graph" aria-label="Knowledge graph dari konteks jawaban">
    <div class="inline-graph-heading">
      <span>Graph konteks</span>
      <small>{graph.nodes.length} entitas · {graph.edges.length} relasi</small>
    </div>
    <div class="inline-graph-scroll" role="region" aria-label="Graf konteks, dapat digulir pada layar sempit">
      <div class="inline-graph-canvas">
        <svg class="inline-graph-lines" viewBox="0 0 720 360" aria-hidden="true" focusable="false">
          {#each graph.edges as edge (edge.id)}
            {#if graph.positions[edge.source] && graph.positions[edge.target]}
              <line
                x1={graph.positions[edge.source].x}
                y1={graph.positions[edge.source].y}
                x2={graph.positions[edge.target].x}
                y2={graph.positions[edge.target].y}
              />
            {/if}
          {/each}
        </svg>
        <div class="inline-graph-nodes">
          {#each graph.nodes as node (node.id)}
            {#if graph.positions[node.id]}
              <button
                class="inline-graph-node"
                class:selected={selectedId === node.id}
                type="button"
                style={`--node-x:${graph.positions[node.id].x}px; --node-y:${graph.positions[node.id].y}px;`}
                aria-label={`Pilih ${node.label}, ${node.type}`}
                aria-pressed={selectedId === node.id}
                title={`${node.label}, ${node.type}`}
                onclick={() => (selectedId = node.id)}
              >
                <span class={labelIds.has(node.id) || selectedId === node.id ? "inline-node-label" : "sr-only"}>{node.label}</span>
              </button>
            {/if}
          {/each}
        </div>
      </div>
    </div>
    {#if selectedNode}
      <div class="inline-graph-detail" aria-live="polite">
        <strong>{selectedNode.label}</strong>
        <span>{selectedNode.type}</span>
        {#if selectedEdges.length}
          <span>{selectedEdges.map((edge) => edge.label).join(" · ")}</span>
        {/if}
      </div>
    {/if}
  </section>
{/if}
