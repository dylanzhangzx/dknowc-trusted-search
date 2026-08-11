#!/usr/bin/env python3
"""Generate stable policy-analysis visualization SVG from JSON or CSV."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PALETTE = ["#2563eb", "#059669", "#f97316", "#7c3aed", "#dc2626", "#0891b2"]
HEAT_COLORS = ["#eef2ff", "#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#2563eb"]
NAME_KEYS = ["name", "city", "region", "area", "对象", "名称", "城市", "地市", "地区", "区域"]
POSITION_KEYS = ["positioning", "特色定位", "定位", "说明", "summary", "description", "核心要点"]
KEYWORD_KEYS = ["keywords", "标签", "关键词", "特色标签"]
SKIP_NUMERIC_KEYS = set(NAME_KEYS + POSITION_KEYS + KEYWORD_KEYS + ["x", "y", "经度", "纬度"])


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def svg_esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def to_float(value: Any, default: float = 0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").replace("，", "").strip())
    except (TypeError, ValueError):
        return default


def first_value(row: Dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def split_keywords(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value or "")
    for sep in ["|", "、", "，", ",", ";", "；"]:
        text = text.replace(sep, "|")
    return [x.strip() for x in text.split("|") if x.strip()]


def load_data(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"items": data, "metadata": {"source_note": path.name}}
        if isinstance(data, dict):
            if isinstance(data.get("items"), list):
                return data
            if isinstance(data.get("cities"), list):
                data["items"] = data["cities"]
                return data
        raise ValueError("JSON input must be a list, or contain items/cities list.")

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return {"items": list(csv.DictReader(f)), "metadata": {"source_note": f"CSV: {path.name}"}}

    raise ValueError("Input must be a .json or .csv file.")


def is_number_like(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        float(str(value).replace(",", "").replace("，", ""))
        return True
    except ValueError:
        return False


def detect_metrics(rows: List[Dict[str, Any]]) -> List[Tuple[str, str, str, str]]:
    keys: List[str] = []
    for row in rows:
        for key, value in row.items():
            if key in keys or key in SKIP_NUMERIC_KEYS or isinstance(value, (dict, list)):
                continue
            if is_number_like(value):
                keys.append(key)
    metrics = []
    for idx, key in enumerate(keys[:6]):
        unit = ""
        if "亿元" in key:
            unit = "亿元"
        elif "万元" in key:
            unit = "万元"
        elif any(token in key for token in ["数", "量", "项", "家"]):
            unit = "项"
        metrics.append((key, key, PALETTE[idx % len(PALETTE)], unit))
    return metrics


def normalize_series(values: List[float], floor: float = 38.0) -> List[float]:
    if not values:
        return []
    max_v = max(values)
    min_v = min(values)
    if max_v == min_v:
        return [75.0 for _ in values]
    return [round(floor + (100 - floor) * (value - min_v) / (max_v - min_v), 1) for value in values]


def normalize_score(value: float, all_values: List[float]) -> float:
    if not all_values:
        return 0
    max_v = max(all_values)
    if max_v <= 5:
        return round(value / 5 * 100, 1)
    if max_v <= 10:
        return round(value / 10 * 100, 1)
    if max_v <= 100:
        return round(value, 1)
    return normalize_series(all_values)[all_values.index(value)]


def normalize_items(data: Dict[str, Any], metric_names: List[str] | None) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str, str, str]], List[str]]:
    raw_items = [x for x in data.get("items", []) if isinstance(x, dict)]
    if not raw_items:
        raise ValueError("Input contains no usable items.")

    metrics = [(name, name, PALETTE[idx % len(PALETTE)], "") for idx, name in enumerate(metric_names or [])]
    if not metrics:
        metrics = detect_metrics(raw_items)
    if not metrics:
        raise ValueError("No numeric metrics found. Provide numeric columns or --metrics.")

    items = []
    for idx, row in enumerate(raw_items, start=1):
        radar_scores = row.get("radar_scores") or row.get("雷达评分") or {}
        if not isinstance(radar_scores, dict):
            radar_scores = {}
        items.append(
            {
                "name": first_value(row, NAME_KEYS, f"对象{idx}"),
                "positioning": first_value(row, POSITION_KEYS, ""),
                "keywords": split_keywords(first_value(row, KEYWORD_KEYS, "")),
                "metrics": {key: to_float(row.get(key)) for key, _, _, _ in metrics},
                "radar_scores": {str(k): to_float(v) for k, v in radar_scores.items()},
            }
        )

    normalized_by_metric: Dict[str, List[float]] = {}
    for key, _, _, _ in metrics:
        normalized_by_metric[key] = normalize_series([item["metrics"].get(key, 0) for item in items])
    for row_idx, item in enumerate(items):
        item["normalized_metrics"] = {key: normalized_by_metric[key][row_idx] for key, _, _, _ in metrics}

    radar_dims: List[str] = []
    for item in items:
        for dim in item["radar_scores"]:
            if dim not in radar_dims:
                radar_dims.append(dim)
    if radar_dims:
        for dim in radar_dims:
            raw_values = [item["radar_scores"].get(dim, 0) for item in items]
            for item in items:
                item["radar_scores"][dim] = normalize_score(item["radar_scores"].get(dim, 0), raw_values)
    else:
        radar_dims = [label for _, label, _, _ in metrics[:5]]
        for item in items:
            item["radar_scores"] = {label: item["normalized_metrics"][key] for key, label, _, _ in metrics[:5]}

    return items, metrics, radar_dims[:6]


def overall_score(item: Dict[str, Any], dims: List[str]) -> float:
    values = [to_float(item["radar_scores"].get(dim)) for dim in dims]
    return round(sum(values) / max(len(values), 1), 1)


def metric_value(item: Dict[str, Any], key: str) -> float:
    return to_float(item["metrics"].get(key))


def metric_norm(item: Dict[str, Any], key: str) -> float:
    return to_float(item["normalized_metrics"].get(key))


def heat_class(value: float) -> str:
    idx = min(int(value // 17), 5)
    return f"heat-{idx}"


def summary_band(items: List[Dict[str, Any]], metrics: List[Tuple[str, str, str, str]], radar_dims: List[str]) -> str:
    ranked = sorted(items, key=lambda item: overall_score(item, radar_dims), reverse=True)
    leader = ranked[0]
    second = ranked[1] if len(ranked) > 1 else ranked[0]
    kpis = [
        ("最高综合分", f"{leader['name']} {overall_score(leader, radar_dims):.1f}"),
        ("第二梯队", f"{second['name']} {overall_score(second, radar_dims):.1f}"),
        ("对比对象", f"{len(items)} 个"),
    ]
    first_metric = metrics[0]
    top_metric = max(items, key=lambda item: metric_value(item, first_metric[0]))
    kpis.append((f"{first_metric[1]}最高", f"{top_metric['name']} {metric_value(top_metric, first_metric[0]):g}"))
    cards = "".join(f'<div class="kpi"><b>{esc(value)}</b><span>{esc(label)}</span></div>' for label, value in kpis)
    return f"""
    <section class="summary-band">
      <div class="summary-copy">
        <small>综合判断</small>
        <strong>{esc(leader["name"])}表现领先，{esc(second["name"])}构成重点对比对象</strong>
        <p>本页按输入数据自动归一化处理，适合政策调研、城市对比、园区评估和领导汇报场景。</p>
      </div>
      {cards}
    </section>
    """


def ranking_panel(items: List[Dict[str, Any]], radar_dims: List[str]) -> str:
    ranked = sorted(items, key=lambda item: overall_score(item, radar_dims), reverse=True)
    rows = []
    for idx, item in enumerate(ranked, start=1):
        score = overall_score(item, radar_dims)
        tags = "".join(f"<span>{esc(tag)}</span>" for tag in item.get("keywords", [])[:3])
        rows.append(
            f"""
            <article class="rank-row">
              <div class="rank-no">{idx}</div>
              <div class="rank-main">
                <div class="rank-title"><b>{esc(item["name"])}</b><span>{score:.1f}</span></div>
                <div class="bar"><i style="width:{score:.1f}%"></i></div>
                <p>{esc(item.get("positioning") or "暂无定位说明")}</p>
                <div class="tags">{tags}</div>
              </div>
            </article>
            """
        )
    return "\n".join(rows)


def heat_matrix(items: List[Dict[str, Any]], metrics: List[Tuple[str, str, str, str]]) -> str:
    sorted_items = sorted(items, key=lambda item: sum(metric_norm(item, key) for key, _, _, _ in metrics), reverse=True)
    header = "".join(f"<th>{esc(label)}</th>" for _, label, _, _ in metrics)
    rows = []
    for item in sorted_items:
        cells = []
        for key, _, _, unit in metrics:
            raw = metric_value(item, key)
            normalized = metric_norm(item, key)
            cells.append(
                f'<td class="{heat_class(normalized)}"><b>{raw:g}</b><small>{esc(unit)}</small><em>{normalized:.0f}</em></td>'
            )
        rows.append(f"<tr><th>{esc(item['name'])}</th>{''.join(cells)}</tr>")
    legend = "".join(f'<span class="heat-{idx}"></span>' for idx in range(6))
    return f"""
    <div class="matrix-note"><b>读图：</b>颜色越深代表该对象在对应指标上相对越强；格内大数字是原始值，右下角小数字是归一化分。</div>
    <div class="heat-legend">{legend}<em>低</em><em>高</em></div>
    <div class="table-wrap">
      <table class="matrix"><thead><tr><th>对象</th>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>
    </div>
    """


def bar_comparison(items: List[Dict[str, Any]], metrics: List[Tuple[str, str, str, str]]) -> str:
    selected = metrics[:4]
    parts = []
    for key, label, color, unit in selected:
        ranked = sorted(items, key=lambda item: metric_value(item, key), reverse=True)
        max_value = max([metric_value(item, key) for item in ranked] + [1])
        bars = []
        for item in ranked:
            raw = metric_value(item, key)
            width = 8 + 92 * raw / max(max_value, 1)
            bars.append(
                f"""
                <div class="hbar-row">
                  <span>{esc(item["name"])}</span>
                  <div class="hbar"><i style="width:{width:.1f}%; background:{color}"></i></div>
                  <b>{raw:g}{esc(unit)}</b>
                </div>
                """
            )
        parts.append(f'<article class="metric-block"><h3>{esc(label)}</h3>{"".join(bars)}</article>')
    return "\n".join(parts)


def radar_chart(items: List[Dict[str, Any]], dims: List[str]) -> str:
    selected = sorted(items, key=lambda item: overall_score(item, dims), reverse=True)[:4]
    size, cx, cy, radius = 620, 310, 310, 190
    angle_step = 2 * math.pi / max(len(dims), 1)
    parts = [f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="多维雷达画像">']
    for level in range(20, 101, 20):
        points = []
        r = radius * level / 100
        for i in range(len(dims)):
            a = -math.pi / 2 + i * angle_step
            points.append(f"{cx + math.cos(a)*r:.1f},{cy + math.sin(a)*r:.1f}")
        parts.append(f'<polygon points="{" ".join(points)}" class="radar-grid"/>')
        parts.append(f'<text x="{cx+7}" y="{cy-r+5:.1f}" class="radar-tick">{level}</text>')
    for i, dim in enumerate(dims):
        a = -math.pi / 2 + i * angle_step
        axis_x = cx + math.cos(a) * radius
        axis_y = cy + math.sin(a) * radius
        label_x = cx + math.cos(a) * (radius + 72)
        label_y = cy + math.sin(a) * (radius + 72)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{axis_x:.1f}" y2="{axis_y:.1f}" class="radar-axis"/>')
        parts.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="radar-label" text-anchor="middle">{esc(dim)}</text>')
    for idx, item in enumerate(selected):
        points = []
        for i, dim in enumerate(dims):
            value = max(0, min(100, to_float(item["radar_scores"].get(dim))))
            a = -math.pi / 2 + i * angle_step
            r = radius * value / 100
            points.append(f"{cx + math.cos(a)*r:.1f},{cy + math.sin(a)*r:.1f}")
        color = PALETTE[idx % len(PALETTE)]
        parts.append(
            f'<polygon class="series series-{idx}" points="{" ".join(points)}" fill="{color}" fill-opacity="0.13" stroke="{color}" stroke-width="3">'
            f'<title>{esc(item["name"])} 综合评分 {overall_score(item, dims):.1f}</title></polygon>'
        )
    parts.append("</svg>")
    legend = []
    for idx, item in enumerate(selected):
        color = PALETTE[idx % len(PALETTE)]
        legend.append(
            f'<button class="radar-toggle" data-series="{idx}" type="button"><i style="background:{color}"></i>{esc(item["name"])} {overall_score(item, dims):.1f}</button>'
        )
    return f'<div class="radar-layout"><div class="radar-legend">{"".join(legend)}</div>{"".join(parts)}</div>'


def module_intro(title: str, body: str) -> str:
    return f'<div class="module-head"><h2>{esc(title)}</h2><p>{esc(body)}</p></div>'


def wrap_text(text: Any, width: int = 18, max_lines: int = 2) -> List[str]:
    value = str(text or "").strip()
    if not value:
        return [""]
    lines: List[str] = []
    current = ""
    for char in value:
        current += char
        if len(current) >= width:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(value) > sum(len(line) for line in lines):
        lines[-1] = lines[-1].rstrip("，。；、") + "..."
    return lines


def svg_text_block(text: Any, x: float, y: float, width: int, size: int = 16, weight: int = 400, fill: str = "#334155", max_lines: int = 2) -> str:
    tspans = []
    for idx, line in enumerate(wrap_text(text, width=width, max_lines=max_lines)):
        dy = 0 if idx == 0 else size * 1.35
        tspans.append(f'<tspan x="{x:g}" dy="{dy:g}">{svg_esc(line)}</tspan>')
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}" font-weight="{weight}" fill="{fill}">{"".join(tspans)}</text>'


def svg_bar(x: float, y: float, width: float, value: float, color: str, bg: str = "#e2e8f0") -> str:
    value = max(0, min(100, value))
    return (
        f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="10" rx="5" fill="{bg}"/>'
        f'<rect x="{x:g}" y="{y:g}" width="{width * value / 100:g}" height="10" rx="5" fill="{color}"/>'
    )


def render_svg(data: Dict[str, Any], title: str, input_path: Path, metric_names: List[str] | None) -> str:
    items, metrics, radar_dims = normalize_items(data, metric_names)
    metadata = data.get("metadata", {})
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    source_note = str(metadata.get("source_note", input_path.name)).rstrip("。.")
    region = metadata.get("region") or metadata.get("范围") or "通用区域"
    topic = metadata.get("topic") or metadata.get("主题") or "政策研究"
    ranked = sorted(items, key=lambda item: overall_score(item, radar_dims), reverse=True)
    width = 1400
    height = 1180
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{svg_esc(title)}">',
        '<rect width="1400" height="1180" fill="#f4f7fb"/>',
        '<rect x="0" y="0" width="1400" height="150" fill="#17324d"/>',
        f'<text x="44" y="62" font-size="34" font-weight="800" fill="#ffffff">{svg_esc(title)}</text>',
        f'<text x="44" y="104" font-size="17" fill="#cfe6ff">{svg_esc(region)} · {svg_esc(topic)} · 生成时间 {svg_esc(generated)}</text>',
    ]

    # Summary cards
    card_w = 300
    for idx, item in enumerate(ranked[:4]):
        x = 44 + idx * (card_w + 22)
        y = 184
        score = overall_score(item, radar_dims)
        color = PALETTE[idx % len(PALETTE)]
        parts.extend([
            f'<rect x="{x}" y="{y}" width="{card_w}" height="150" rx="12" fill="#ffffff" stroke="#d7dfeb"/>',
            f'<circle cx="{x+32}" cy="{y+35}" r="17" fill="{color}" opacity="0.16"/>',
            f'<text x="{x+25}" y="{y+42}" font-size="18" font-weight="800" fill="{color}">{idx+1}</text>',
            f'<text x="{x+58}" y="{y+42}" font-size="24" font-weight="800" fill="#172033">{svg_esc(item["name"])}</text>',
            f'<text x="{x+58}" y="{y+78}" font-size="30" font-weight="900" fill="{color}">{score:.1f}</text>',
            svg_bar(x+58, y+94, 190, score, color),
            svg_text_block(item.get("positioning") or "暂无定位说明", x+24, y+125, 20, size=13, fill="#64748b", max_lines=2),
        ])

    # Heat matrix
    matrix_x, matrix_y = 44, 380
    row_h, col_w = 52, 155
    parts.extend([
        '<text x="44" y="362" font-size="24" font-weight="800" fill="#0f172a">指标热力矩阵</text>',
        '<text x="220" y="362" font-size="14" fill="#64748b">颜色越深代表该对象在对应指标上相对越强</text>',
        f'<rect x="{matrix_x}" y="{matrix_y}" width="{220 + len(metrics[:5]) * col_w}" height="{52 + len(ranked) * row_h}" rx="10" fill="#ffffff" stroke="#d7dfeb"/>',
        f'<text x="{matrix_x+22}" y="{matrix_y+34}" font-size="15" font-weight="800" fill="#334155">对象</text>',
    ])
    for m_idx, (_, label, _, _) in enumerate(metrics[:5]):
        parts.append(svg_text_block(label, matrix_x + 220 + m_idx * col_w + 16, matrix_y + 30, 10, size=13, weight=800, fill="#334155", max_lines=2))
    heat_palette = ["#eef2ff", "#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#2563eb"]
    for r_idx, item in enumerate(ranked):
        y = matrix_y + 52 + r_idx * row_h
        parts.append(f'<line x1="{matrix_x}" y1="{y}" x2="{matrix_x + 220 + len(metrics[:5]) * col_w}" y2="{y}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{matrix_x+22}" y="{y+32}" font-size="16" font-weight="800" fill="#0f172a">{svg_esc(item["name"])}</text>')
        for m_idx, (key, _, _, unit) in enumerate(metrics[:5]):
            norm = metric_norm(item, key)
            raw = metric_value(item, key)
            color = heat_palette[min(int(norm // 17), 5)]
            tx = matrix_x + 220 + m_idx * col_w
            text_fill = "#ffffff" if norm >= 85 else "#172033"
            parts.extend([
                f'<rect x="{tx}" y="{y}" width="{col_w}" height="{row_h}" fill="{color}" opacity="0.95"/>',
                f'<text x="{tx+18}" y="{y+32}" font-size="17" font-weight="900" fill="{text_fill}">{raw:g}{svg_esc(unit)}</text>',
            ])

    # Bar comparison
    bar_x, bar_y = 44, 760
    parts.append('<text x="44" y="726" font-size="24" font-weight="800" fill="#0f172a">横向指标对比</text>')
    for m_idx, (key, label, color, unit) in enumerate(metrics[:3]):
        x = bar_x + m_idx * 430
        parts.extend([
            f'<rect x="{x}" y="{bar_y}" width="400" height="230" rx="10" fill="#ffffff" stroke="#d7dfeb"/>',
            f'<text x="{x+20}" y="{bar_y+34}" font-size="18" font-weight="800" fill="#172033">{svg_esc(label)}</text>',
        ])
        max_value = max([metric_value(item, key) for item in ranked] + [1])
        for idx, item in enumerate(sorted(items, key=lambda item: metric_value(item, key), reverse=True)[:5]):
            y = bar_y + 65 + idx * 31
            raw = metric_value(item, key)
            parts.append(f'<text x="{x+20}" y="{y+13}" font-size="14" font-weight="700" fill="#334155">{svg_esc(item["name"])}</text>')
            parts.append(svg_bar(x+104, y+4, 210, 100 * raw / max(max_value, 1), color))
            parts.append(f'<text x="{x+326}" y="{y+13}" font-size="13" font-weight="800" fill="#334155">{raw:g}{svg_esc(unit)}</text>')

    # Radar
    radar_cx, radar_cy, radar_r = 1110, 550, 130
    selected = ranked[:4]
    dims = radar_dims[:6]
    if dims:
        angle_step = 2 * math.pi / len(dims)
        parts.append('<text x="950" y="362" font-size="24" font-weight="800" fill="#0f172a">多维雷达画像</text>')
        parts.append('<rect x="930" y="380" width="410" height="330" rx="10" fill="#ffffff" stroke="#d7dfeb"/>')
        for level in range(20, 101, 20):
            pts = []
            r = radar_r * level / 100
            for i in range(len(dims)):
                a = -math.pi / 2 + i * angle_step
                pts.append(f"{radar_cx + math.cos(a)*r:.1f},{radar_cy + math.sin(a)*r:.1f}")
            parts.append(f'<polygon points="{" ".join(pts)}" fill="none" stroke="#d8e1ee"/>')
        for i, dim in enumerate(dims):
            a = -math.pi / 2 + i * angle_step
            ax = radar_cx + math.cos(a) * radar_r
            ay = radar_cy + math.sin(a) * radar_r
            lx = radar_cx + math.cos(a) * (radar_r + 42)
            ly = radar_cy + math.sin(a) * (radar_r + 42)
            parts.append(f'<line x1="{radar_cx}" y1="{radar_cy}" x2="{ax:.1f}" y2="{ay:.1f}" stroke="#d8e1ee"/>')
            parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12" font-weight="700" fill="#334155" text-anchor="middle">{svg_esc(dim[:7])}</text>')
        for idx, item in enumerate(selected):
            pts = []
            for i, dim in enumerate(dims):
                value = max(0, min(100, to_float(item["radar_scores"].get(dim))))
                a = -math.pi / 2 + i * angle_step
                r = radar_r * value / 100
                pts.append(f"{radar_cx + math.cos(a)*r:.1f},{radar_cy + math.sin(a)*r:.1f}")
            color = PALETTE[idx % len(PALETTE)]
            parts.append(f'<polygon points="{" ".join(pts)}" fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-width="2.5"/>')
            parts.append(f'<rect x="950" y="{660 + idx*25}" width="12" height="12" rx="2" fill="{color}"/>')
            parts.append(f'<text x="970" y="{671 + idx*25}" font-size="13" font-weight="700" fill="#334155">{svg_esc(item["name"])} {overall_score(item, dims):.1f}</text>')

    parts.append(f'<text x="44" y="1136" font-size="13" fill="#64748b">数据说明：{svg_esc(source_note)}。本图为静态 SVG，可直接在对话中展示。</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成通用本地政策可视化 SVG 图片。")
    parser.add_argument("--input", required=True, help="JSON 或 CSV 数据路径。")
    parser.add_argument("--output", required=True, help="生成的 SVG 图片输出路径。")
    parser.add_argument("--title", default="政策研究可视化分析")
    parser.add_argument("--heat-metric", default="", help="兼容旧参数；新版默认生成指标热力矩阵。")
    parser.add_argument("--metrics", default="", help="逗号分隔的指标列名；默认自动识别数值列。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if output_path.suffix.lower() != ".svg":
        raise ValueError("可视化只支持输出 SVG 图片；请使用 .svg 作为输出扩展名。")
    metric_names = [x.strip() for x in args.metrics.split(",") if x.strip()] if args.metrics else None
    data = load_data(input_path)
    output_text = render_svg(data, args.title, input_path, metric_names)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
