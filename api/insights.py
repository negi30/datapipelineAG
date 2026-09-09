import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

INDEX_LIKE_COLS = {"index", "level_0", "unnamed: 0", "_index", "position"}

def generate_data_insights(query: str, result: Any, chart_config: Dict[str, Any] | None, source_df: pd.DataFrame | None = None) -> List[Dict[str, str]]:
    """
    Automatically extracts business observations, statistical trends,
    bivariate correlations, outliers, and sample-size context from the execution result.
    """
    insights: List[Dict[str, str]] = []

    if result is None:
        return insights

    # Handle Scalar Result
    if isinstance(result, (int, float, np.number)):
        val = round(float(result), 2)
        insights.append({
            "type": "summary",
            "icon": "fa-bullseye",
            "title": "Primary Metric",
            "text": f"Computed single value for '{query}': <strong>{val:,.2f}</strong>"
        })
        return insights

    # Handle DataFrame Result
    if isinstance(result, pd.DataFrame):
        if result.empty:
            insights.append({
                "type": "warning",
                "icon": "fa-circle-info",
                "title": "Empty Result",
                "text": "The query executed successfully but produced zero matching rows."
            })
            return insights

        cols = list(result.columns)
        num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(result[c]) and str(c).lower() not in INDEX_LIKE_COLS]
        cat_cols = [c for c in cols if c not in num_cols and str(c).lower() not in INDEX_LIKE_COLS]

        # 1. Scatter Plot & Bivariate Relationship Insights
        is_scatter = chart_config and chart_config.get("type") == "scatter"
        if (is_scatter or (len(num_cols) >= 2 and not cat_cols)) and len(num_cols) >= 2:
            x_col = chart_config.get("x_label") if chart_config else num_cols[0]
            y_col = chart_config.get("y_label") if chart_config else num_cols[1]
            if x_col in result.columns and y_col in result.columns:
                valid_df = result[[x_col, y_col]].dropna()
                if len(valid_df) >= 3:
                    try:
                        corr = float(valid_df[x_col].corr(valid_df[y_col]))
                    except Exception:
                        corr = None

                    if corr is not None and pd.notna(corr):
                        if abs(corr) >= 0.7:
                            strength = "strong"
                        elif abs(corr) >= 0.35:
                            strength = "moderate"
                        else:
                            strength = "weak / non-linear"
                        direction = "positive" if corr > 0 else "negative" if corr < 0 else "neutral"

                        insights.append({
                            "type": "highlight",
                            "icon": "fa-chart-line",
                            "title": "Bivariate Correlation",
                            "text": f"Pearson correlation between <strong>{x_col.replace('_', ' ')}</strong> and <strong>{y_col.replace('_', ' ')}</strong> is <strong>r = {corr:.2f}</strong>, indicating a <strong>{strength} {direction} relationship</strong> across {len(valid_df):,} observations."
                        })

                    max_y_idx = valid_df[y_col].idxmax()
                    max_y_val = valid_df.loc[max_y_idx, y_col]
                    max_y_xval = valid_df.loc[max_y_idx, x_col]
                    
                    label_str = ""
                    if cat_cols and cat_cols[0] in result.columns:
                        label_val = str(result.loc[max_y_idx, cat_cols[0]])
                        label_str = f" for <strong>{label_val}</strong>"

                    insights.append({
                        "type": "observation",
                        "icon": "fa-crosshairs",
                        "title": f"Peak {y_col.replace('_', ' ')} Observation",
                        "text": f"Maximum {y_col.replace('_', ' ')} recorded is <strong>{max_y_val:,.0f}</strong>{label_str} (co-occurring with {x_col.replace('_', ' ')} of <strong>{max_y_xval:,.0f}</strong>)."
                    })
                    return insights

        # 2. Single-Row Leader Insight (e.g. Which artist has the highest average streams per song?)
        if len(result) == 1 and cat_cols and num_cols:
            row = result.iloc[0]
            entity = str(row[cat_cols[0]]).strip()
            lead_metric = num_cols[0]
            val = row[lead_metric]
            
            # Check for sample size column (e.g. count, song_count, num_songs)
            count_col = next((c for c in num_cols if any(k in c.lower() for k in ["count", "songs", "tracks", "samples", "size"])), None)
            
            sample_note = ""
            if count_col and count_col in row:
                c_val = int(row[count_col])
                sample_note = f" based on <strong>{c_val} item{'s' if c_val > 1 else ''}</strong>"
                if c_val == 1:
                    sample_note += " <span class='text-amber-400 font-semibold'>(Single-item sample — watch for N=1 outlier skew)</span>"

            insights.append({
                "type": "highlight",
                "icon": "fa-trophy",
                "title": "Top Leader",
                "text": f"<strong>{entity}</strong> ranks #1 with <strong>{val:,.2f}</strong> {lead_metric.replace('_', ' ')}{sample_note}."
            })

            # Check source_df for sample size context if query relates to averages/means
            if source_df is not None and any(w in query.lower() for w in ["average", "mean", "per", "avg"]):
                cat_col = cat_cols[0]
                match_cols = [c for c in source_df.columns if str(c).lower() == str(cat_col).lower()]
                if match_cols:
                    m_col = match_cols[0]
                    sample_count = len(source_df[source_df[m_col].astype(str).str.strip() == entity])
                    if sample_count == 1:
                        value_counts = source_df[m_col].astype(str).str.strip().value_counts()
                        multi_entities = set(value_counts[value_counts >= 2].index)
                        
                        source_metric_cols = [c for c in source_df.columns if str(c).lower() == str(lead_metric).lower()]
                        if not source_metric_cols:
                            source_metric_cols = [c for c in source_df.columns if any(w in str(c).lower() for w in str(lead_metric).lower().split()) and pd.api.types.is_numeric_dtype(source_df[c]) and str(c).lower() not in INDEX_LIKE_COLS]
                        cat_note = ""
                        if multi_entities and source_metric_cols:
                            sm_col = source_metric_cols[0]
                            try:
                                cat_leaders = source_df[source_df[m_col].astype(str).str.strip().isin(multi_entities)].groupby(m_col)[sm_col].mean().reset_index().sort_values(by=sm_col, ascending=False)
                                if not cat_leaders.empty:
                                    top_cat = cat_leaders.iloc[0]
                                    cat_name = str(top_cat[m_col]).strip()
                                    cat_val = top_cat[sm_col]
                                    cat_songs = int(value_counts[cat_name])
                                    cat_note = f" In contrast, among catalog artists with multiple tracks (&ge; 2 songs), <strong>{cat_name}</strong> leads with <strong>{cat_val:,.0f}</strong> average streams across <strong>{cat_songs} songs</strong>."
                            except Exception:
                                pass

                        insights.append({
                            "type": "observation",
                            "icon": "fa-scale-unbalanced",
                            "title": "Sample Size Sensitivity (N=1 Outlier Effect)",
                            "text": f"<strong>{entity}</strong> has only <strong>1 song in the dataset (N=1)</strong>, mathematically skewing the average.{cat_note}"
                        })

            return insights

        # 3. Rate / Percentage Column Insights
        rate_col = next((c for c in num_cols if any(k in c.lower() for k in ["pct", "rate", "percent", "%", "ratio"])), None)
        if rate_col and len(result) > 1:
            max_idx = result[rate_col].idxmax()
            min_idx = result[rate_col].idxmin()
            max_val = result.loc[max_idx, rate_col]
            min_val = result.loc[min_idx, rate_col]
            
            label_col = cat_cols[0] if cat_cols else cols[0]
            val_max = result.loc[max_idx, label_col]
            val_min = result.loc[min_idx, label_col]
            group_label_max = f'{val_max} ({label_col})'
            group_label_min = f'{val_min} ({label_col})'

            insights.append({
                "type": "highlight",
                "icon": "fa-chart-line",
                "title": f"Peak {rate_col.replace('_', ' ')}",
                "text": f"Highest {rate_col.replace('_', ' ')} occurs at <strong>{group_label_max}</strong> ({max_val:.1f}%), while the lowest is at <strong>{group_label_min}</strong> ({min_val:.1f}%)."
            })

            if min_val > 0:
                ratio = max_val / min_val
                insights.append({
                    "type": "trend",
                    "icon": "fa-arrows-split-up-and-left",
                    "title": "Relative Disparity",
                    "text": f"The rate at <strong>{group_label_max}</strong> is <strong>{ratio:.1f}x higher</strong> compared to <strong>{group_label_min}</strong>."
                })

        # 4. Multi-Numeric / Pivot Table Insights (Strictly multi-row and non-scatter)
        if cat_cols and len(num_cols) > 1 and len(result) > 1 and not is_scatter:
            x_col = cat_cols[0]
            best_val = -float('inf')
            best_cat = ""
            best_metric = ""
            worst_val = float('inf')
            worst_cat = ""
            worst_metric = ""

            for n_col in num_cols:
                for idx, val in result[n_col].items():
                    if pd.notna(val) and isinstance(val, (int, float, np.number)):
                        if val > best_val:
                            best_val = val
                            best_cat = str(result.loc[idx, x_col])
                            best_metric = str(n_col)
                        if val < worst_val:
                            worst_val = val
                            worst_cat = str(result.loc[idx, x_col])
                            worst_metric = str(n_col)

            if best_val != -float('inf'):
                insights.append({
                    "type": "highlight",
                    "icon": "fa-trophy",
                    "title": "Peak Metric Observation",
                    "text": f"Highest value observed is <strong>{best_val:,.2f}</strong> for <strong>{best_cat}</strong> ({best_metric.replace('_', ' ')})."
                })
            if worst_val != float('inf') and worst_val < best_val:
                insights.append({
                    "type": "observation",
                    "icon": "fa-arrow-down-short-wide",
                    "title": "Lowest Metric Observation",
                    "text": f"Lowest value observed is <strong>{worst_val:,.2f}</strong> for <strong>{worst_cat}</strong> ({worst_metric.replace('_', ' ')})."
                })

            insights.append({
                "type": "trend",
                "icon": "fa-chart-column",
                "title": "Grouped Comparison",
                "text": f"The chart plots all <strong>{len(num_cols)} metrics</strong> side-by-side across each {x_col} for complete multi-variable visibility."
            })

        # 5. Numeric Leader & Sample-Size Sensitivity (Single Metric across multiple rows)
        if num_cols and cat_cols and len(num_cols) == 1 and not rate_col and len(result) > 1:
            metric = num_cols[0]
            cat = cat_cols[0]
            sorted_df = result.sort_values(by=metric, ascending=False)
            
            top_row = sorted_df.iloc[0]
            bottom_row = sorted_df.iloc[-1]
            total_sum = sorted_df[metric].sum()

            is_avg = any(w in metric.lower() for w in [
                'mean', 'avg', 'average', 'median', 'year', 'age', 'income',
                'salary', 'rate', 'price', 'cost', 'score', 'rating', 'distance',
                'tenure', 'hour', 'level', 'experience', 'hike'
            ])

            if is_avg:
                diff = top_row[metric] - bottom_row[metric]
                ratio = (top_row[metric] / bottom_row[metric]) if bottom_row[metric] > 0 else 1.0
                insights.append({
                    "type": "highlight",
                    "icon": "fa-chart-simple",
                    "title": f"Average {metric.replace('_', ' ')} Comparison",
                    "text": f"<strong>{top_row[cat]}</strong> averages <strong>{top_row[metric]:,.2f}</strong> vs <strong>{bottom_row[cat]}</strong> at <strong>{bottom_row[metric]:,.2f}</strong> (a difference of <strong>{diff:,.2f}</strong>, or <strong>{ratio:.1f}x</strong>)."
                })
            else:
                top_share = (top_row[metric] / total_sum * 100) if total_sum > 0 else 0
                insights.append({
                    "type": "highlight",
                    "icon": "fa-crown",
                    "title": f"Top Performer by {metric.replace('_', ' ')}",
                    "text": f"<strong>{top_row[cat]}</strong> leads with <strong>{top_row[metric]:,.2f}</strong>, contributing <strong>{top_share:.1f}%</strong> of total volume."
                })

                if len(sorted_df) >= 3:
                    top_3_sum = sorted_df.head(3)[metric].sum()
                    top_3_share = (top_3_sum / total_sum * 100) if total_sum > 0 else 0
                    insights.append({
                        "type": "trend",
                        "icon": "fa-layer-group",
                        "title": "Top-3 Concentration",
                        "text": f"The top 3 categories account for <strong>{top_3_share:.1f}%</strong> of aggregate {metric.replace('_', ' ')}."
                    })

        # 6. Sample Size / N=1 Outlier Guard (when sample count column exists)
        count_col = next((c for c in cols if any(k in c.lower() for k in ["song_count", "track_count", "item_count", "catalog_count"])), None)
        if count_col and cat_cols and len(result) > 1:
            n1_records = result[result[count_col] == 1]
            multi_records = result[result[count_col] > 1]
            if len(n1_records) > 0 and len(multi_records) > 0:
                n1_name = str(n1_records.iloc[0][cat_cols[0]])
                catalog_leader = str(multi_records.iloc[0][cat_cols[0]])
                insights.append({
                    "type": "observation",
                    "icon": "fa-scale-unbalanced",
                    "title": "Catalog Size vs Single-Hit Disparity",
                    "text": f"Top ranking includes single-item artists like <strong>{n1_name}</strong> ($N=1$). Among multi-track catalog leaders, <strong>{catalog_leader}</strong> commands the highest sustained volume."
                })

        # 7. Chart-Specific Visual Pattern
        if chart_config:
            chart_type = chart_config.get("type")
            if chart_type == "scatter":
                insights.append({
                    "type": "observation",
                    "icon": "fa-braille",
                    "title": "Visual Pattern (Scatter Plot)",
                    "text": f"The scatter plot visualizes bivariate distribution between {chart_config.get('x_label', 'X')} and {chart_config.get('y_label', 'Y')}. Look for cluster density and outliers along the frontier."
                })
            elif chart_type == "pie":
                insights.append({
                    "type": "observation",
                    "icon": "fa-circle-notch",
                    "title": "Visual Pattern (Donut Chart)",
                    "text": "The donut chart highlights proportional share. Look for slices commanding more than 20% share as primary drivers."
                })
            elif chart_type == "bar":
                insights.append({
                    "type": "observation",
                    "icon": "fa-chart-column",
                    "title": "Visual Pattern (Bar Chart)",
                    "text": f"The bar chart highlights comparative ranking across {chart_config.get('x_label', 'categories')}. Notice the steepness of drop-off from the leader."
                })
            elif chart_type == "line":
                insights.append({
                    "type": "observation",
                    "icon": "fa-wave-square",
                    "title": "Visual Pattern (Trend Line)",
                    "text": f"The line chart tracks progression over {chart_config.get('x_label', 'time')}. Observe inflection points where trajectories shift."
                })

    return insights