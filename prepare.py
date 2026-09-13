"""Prepare reproducible local scientific figures and a starter notebook."""

from concurrent.futures import ThreadPoolExecutor
from html import escape
import json

import nbformat
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative

from brain import (ARTIFACTS, CACHE, DATA, ROOT, build_graph, context_mesh,
                   ensure_skeleton, graph, load_neuron, neurons, partners,
                   plot_neurons, style_3d)


def write_figure(fig, filename, title, description, extra=""):
    # Plotly is embedded: each exported figure can also be opened offline.
    body = fig.to_html(full_html=False, include_plotlyjs=True, div_id="brain-figure",
                       config=dict(displaylogo=False, scrollZoom=True, responsive=True,
                                   toImageButtonOptions=dict(format="png", scale=2)))
    links = [("index.html", "Nöronlar"), ("hucre-govdeleri.html", "Tüm hücre gövdeleri"),
             ("dnge104.html", "Tek nöron çifti"), ("baglantilar.html", "Bağlantılar")]
    nav = " · ".join(f'<a href="{p}">{name}</a>' for p, name in links)
    controls = ("Sürükle: döndür · Tekerlek: yakınlaş · Sağdaki isimlere tıkla: göster/gizle · Çift tıkla: bir grubu ayır"
                if any(t.type in ("scatter3d", "mesh3d") for t in fig.data)
                else "Hücre üzerinde dur: tam temas sayısını gör · Sürükle: alan seçerek yakınlaş · Çift tıkla: görünümü sıfırla")
    content = f'''<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · MaleCNS</title>
<style>body{{margin:0;background:#101722;color:#e2e8f0;font:15px system-ui,sans-serif}}
header,footer,section{{padding:20px 32px}}h1{{font-size:26px;margin:14px 0 8px}}
p{{line-height:1.6;margin:8px 0;color:#b5c3d5}}a{{color:#83d9cf}}nav{{line-height:2}}
table{{border-collapse:collapse;font-size:13px}}td,th{{padding:7px 12px;border-bottom:1px solid #344052;text-align:left}}
details{{margin-top:15px}}summary{{cursor:pointer}}.tables{{display:flex;gap:36px;flex-wrap:wrap}}</style>
<header><nav>{nav}</nav><h1>{escape(title)}</h1><p>{description}</p>
<p>{controls}</p></header>
{body}<section>{extra}</section><footer><p>MaleCNS v1.0 · İndirilen gerçek anatomi ve bağlantı verisi.
Renkler nöron veya sınıf kimliğini gösterir; elektriksel aktiviteyi göstermez.</p>
<p>Kaynaklar: <a href="https://male-cns.janelia.org/download/">Janelia MaleCNS</a> ·
<a href="https://github.com/navis-org/navis-flybrains">flybrains JRCFIB2022M anatomi yüzeyi</a> ·
<a href="https://neuroglancer-demo.appspot.com/#!gs://flyem-male-cns/v1.0/male-cns-v1.0.json">Tüm çevrimiçi atlas</a></p></footer></html>'''
    (ARTIFACTS / filename).write_text(content)


def sample_ids():
    n = neurons()
    # Curated examples, not a statistically representative or connected circuit.
    ids = []
    for name in ("DNge104", "DNp01", "DNa02", "DNg13", "MBON11", "APL", "CT1", "EPG", "PEN_a(PEN1)"):
        ids.extend(n.loc[n.type.eq(name), "bodyId"].head(2).tolist())
    for name in ("vnc_motor", "vnc_intrinsic", "ascending_neuron", "cb_sensory", "ol_sensory"):
        candidates = n.loc[n.superclass.eq(name)].sort_values(
            "statusLabel", key=lambda s: s.ne("Reviewed"), kind="stable")
        ids.extend(candidates.bodyId.head(2).tolist())
    return list(dict.fromkeys(ids))


def prepare_geometry():
    ids = sample_ids()
    print(f"Downloading/verifying {len(ids)} selected SWCs", flush=True)
    # Initialize metadata once before concurrent read-only lookups.
    from brain import annotations
    annotations()
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths = list(pool.map(ensure_skeleton, ids))
    rows = []
    for body_id in ids:
        n = load_neuron(body_id)
        nodes = n.nodes
        parents = nodes.loc[nodes.parent_id >= 0, "parent_id"]
        if not nodes.node_id.is_unique or not parents.isin(nodes.node_id).all():
            raise ValueError(f"Invalid skeleton parent references: {body_id}")
        if not np.isfinite(nodes[["x", "y", "z"]].to_numpy()).all():
            raise ValueError(f"Non-finite skeleton coordinates: {body_id}")
        rows.append(dict(bodyId=body_id, name=n.name, nodes=len(nodes), roots=int((nodes.parent_id < 0).sum())))
    (CACHE / "selected-skeletons.json").write_text(json.dumps(rows, indent=2) + "\n")
    vertices, faces = context_mesh()
    np.savez_compressed(CACHE / "cns-surface-um.npz", vertices=vertices, faces=faces)
    print(f"Geometry valid: {len(ids)} neurons, {sum(r['nodes'] for r in rows):,} SWC nodes", flush=True)
    return ids, rows


def figures(ids):
    n = neurons()
    print("Exporting local 3D figures", flush=True)
    # A compact pair is immediately readable; the multi-neuron view offers context.
    write_figure(plot_neurons([12781, 556329], context=False), "dnge104.html", "DNge104 · Sağ ve sol nöron",
                 "İki nöronun indirilen SWC iskeleti. Her dal dosyadaki gerçek bir uzantıdır; eksen birimi µm. "
                 "Birden fazla kök bileşeni kaynak dosyada da var; aralarına yapay bağlantı eklenmedi.")
    write_figure(plot_neurons(ids), "index.html", f"MaleCNS · {len(ids)} nöronla 3B keşif",
                 "Beyin ve ventral sinir kordonu yüzeyi üzerinde farklı tiplerden seçilmiş gerçek nöronlar. "
                 "Bu görünüm bir örnek koleksiyondur; tüm nöron iskeletleri indirilmiş değildir. "
                 "Uzun yapı ventral sinir kordonudur (VNC).")
    located = n[n.somaLocation.notna()]
    fig = go.Figure()
    for i, (name, group) in enumerate(located.groupby("superclass", sort=True)):
        xyz = (np.stack(group.somaLocation.to_numpy()) * 0.008).astype(np.float32)
        labels = (group["instance"].fillna(group["type"]).fillna("Etiket yok").astype(str)
                  + " · " + group.bodyId.astype(str)).tolist()
        fig.add_trace(go.Scatter3d(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2], mode="markers",
                                  marker=dict(size=1.5, opacity=0.6, color=qualitative.Dark24[i % 24]),
                                  name=f"{name} ({len(group):,})", text=labels,
                                  hovertemplate="%{text}<extra></extra>"))
    style_3d(fig)
    write_figure(fig, "hucre-govdeleri.html", f"{len(located):,} hücre gövdesinin konumu",
                 f"Her nokta bir hücre gövdesidir; dalları göstermez. superclass etiketi bulunan {len(n):,} kayıt içinden "
                 f"konumu olan {len(located):,} kayıt çizildi; {len(n) - len(located):,} kaydın soma konumu yok. "
                 "Bu keşif filtresi, makalenin 166.691 nöronluk sayımını birebir yeniden üretmez.")
    body_ids, matrix = graph()
    codes, groups = pd.factorize(n.loc[body_ids, "superclass"], sort=True)
    total = np.zeros((len(groups), len(groups)), dtype=np.int64)
    for group_id in range(len(groups)):
        output = np.asarray(matrix[codes == group_id].sum(axis=0)).ravel()
        np.add.at(total[group_id], codes, output)
    fig = go.Figure(go.Heatmap(z=np.log10(1 + total), x=groups.tolist(), y=groups.tolist(),
                              customdata=total, colorscale="Viridis", colorbar=dict(title="log10(1+n)"),
                              hovertemplate="%{y} → %{x}<br>%{customdata:,} temas<extra></extra>"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#101722", height=780,
                      margin=dict(l=220, r=30, b=200, t=20),
                      xaxis_title="Hedef (postsynaptic)", yaxis_title="Kaynak (presynaptic)")
    tables = '<div class="tables">'
    for direction, title in (("in", "12781'e en güçlü 12 girdi"), ("out", "12781'in en güçlü 12 çıktısı")):
        result = partners(12781, direction, 12)
        tables += f"<div><h3>{title}</h3>{result[['bodyId', 'instance', 'synaptic_contacts']].to_html(index=False)}</div>"
    tables += "</div>"
    write_figure(fig, "baglantilar.html", "Sınıflar arasında bağlantılar",
                 f"166.700 kayıt arasındaki {matrix.nnz:,} yönlü bağlantı ve {int(matrix.sum()):,} sinaptik temas. "
                 "Hücre üzerine gelince tam sayı görünür. Ağırlıklar anatomik temas sayısıdır; uyarıcı/baskılayıcı etki veya öğrenilmiş ağırlık değildir.", tables)


def notebook():
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = dict(display_name="Python 3 (fruitfly)", language="python", name="python3")
    nb.cells = [
        nbformat.v4.new_markdown_cell("# MaleCNS yerel keşif\n\nBu defter indirilen MaleCNS v1.0 verisini okur. `Shift+Enter` ile hücreleri çalıştır. İlk üç örnek internet gerektirmez. Yeni bir nöronun iskeletini seçersen resmî depodan indirilip doğrulanır.\n\n**Kapsam:** anatomi ve bağlantı analizi. Çalışan/öğrenen bir biyolojik beyin simülasyonu değildir."),
        nbformat.v4.new_code_cell("from brain import find_neurons, partners, plot_neurons, graph\nfind_neurons('DNge104')"),
        nbformat.v4.new_markdown_cell("Nöron 12781'in en güçlü girişleri. `direction='out'` çıkışları verir. Yalnızca superclass etiketi olan keşif kümesi içindeki bağlantılar listelenir."),
        nbformat.v4.new_code_cell("partners(12781, direction='in', limit=15)"),
        nbformat.v4.new_code_cell("partners(12781, direction='out', limit=15)"),
        nbformat.v4.new_markdown_cell("Gerçek 3B iskeletleri çiz. Etiketlere tıklayarak bir nöronu gizleyebilirsin. Hazır HTML dosyaları `artifacts/` klasöründe de bulunuyor."),
        nbformat.v4.new_code_cell("fig = plot_neurons([12781, 556329], context=False)\nfig.show(renderer='notebook')"),
        nbformat.v4.new_markdown_cell("Bağlantı matrisi: satır kaynak, sütun hedef. Tüm 166.700 × 166.700 matrisi `.toarray()` ile yoğunlaştırma; sparse olarak kullan. 166.700 sayısı keşif filtresidir, makalenin 166.691 sayımıyla aynı seçim değildir."),
        nbformat.v4.new_code_cell("body_ids, adjacency = graph()\n{'neurons': len(body_ids), 'directed_edges': adjacency.nnz, 'synaptic_contacts': int(adjacency.sum())}"),
        nbformat.v4.new_markdown_cell("Yeni arama örnekleri: `find_neurons('APL')`, `find_neurons('MBON11')`, `find_neurons('EPG')`. Listeden bodyId seçip `plot_neurons([bodyId])` ile incele. Neurotransmitter tahmini tek başına bütün sinapsların fizyolojik işaretini belirlemez. Brian2 kurulu; biyolojik dinamikler ve öğrenme kuralı henüz tanımlanmadı.")
    ]
    path = ROOT / "baslangic.ipynb"
    if not path.exists():
        nbformat.write(nb, path)


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    stats = build_graph()
    print(json.dumps(stats), flush=True)
    ids, rows = prepare_geometry()
    figures(ids)
    notebook()
    summary = dict(graph=stats, skeletons=rows, local_figures=4,
                   soma_positions=int(neurons().somaLocation.notna().sum()),
                   coordinate_unit="micrometer", neural_simulation_executed=False)
    (ARTIFACTS / "validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("Ready: artifacts/index.html and baslangic.ipynb", flush=True)


if __name__ == "__main__":
    main()
