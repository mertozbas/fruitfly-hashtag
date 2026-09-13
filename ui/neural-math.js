// Pure instrumentation math, independent of the renderer. No synthetic activity.
export function modelMatches(graph, simulation, model) {
  return !!(model && simulation.activity?.length===graph.total && model.id===simulation.model &&
    model.sha256===simulation.model_sha256 && model.graph_version===graph.version &&
    model.circuit_identity===graph.circuit_identity && simulation.circuit_identity===graph.circuit_identity &&
    model.gains.length===graph.edges.length);
}
export function edgeSignal(graph, edge, activity, gain) {
  // Contribution to target pre-tanh input: the actual forward pass uses tanh(2 * sum(a*w)).
  const value=activity?.[graph.nodes[edge.a].index];
  return Number.isFinite(value)&&Number.isFinite(gain)?2*value*edge.weight*gain:0;
}
export function groupActivity(graph, activity) {
  return graph.group_ranges.map(group=>{
    let sum=0,active=0,max=0;
    for(let i=group.start;i<group.start+group.count;i++){
      const a=activity?.[i]??0;sum+=a;active+=a>.01?1:0;max=Math.max(max,a);
    }
    return {...group,mean:sum/group.count,active,max};
  });
}
export function activityGrid(nodes, activity, bounds, width=48, height=32) {
  const sums=new Float32Array(width*height), counts=new Uint32Array(width*height);
  for(const n of nodes){
    const x=Math.max(0,Math.min(width-1,Math.floor((n.position[0]-bounds.minX)/(bounds.maxX-bounds.minX)*width)));
    const z=Math.max(0,Math.min(height-1,Math.floor((n.position[2]-bounds.minZ)/(bounds.maxZ-bounds.minZ)*height)));
    const i=z*width+x;sums[i]+=activity?.[n.index]??0;counts[i]++;
  }
  return {sums,counts,width,height};
}
