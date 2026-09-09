import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def generate_data_insights(query: str, result: Any, chart_config: Dict[str, Any] | None) -> List[Dict[str, str]]:
    """
    Automatically extracts business observations, trends, outliers,
    and key insights from the execution result and chart configuration.
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
            "text": f"Computed single value for '{query}': {val:,.2f}"
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
        num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(result[c])]
        cat_cols = [c for c in cols if c not in num_cols]

        # 1. Rate / Percentage Column Insights
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

        # 2. Categorical Distribution / Value Counts (e.g. Attrition overall: Yes vs No)
        if len(result) == 2 and any(k in cols[0].lower() for k in ["status", "attrition", "churn", "flag"]):
            count_col = next((c for c in num_cols if "count" in c.lower()), None)
            pct_col = next((c for c in num_cols if "percent" in c.lower() or "pct" in c.lower()), None)
            
            row0_val = result.iloc[0][cols[0]]
            row1_val = result.iloc[1][cols[0]]

            if pct_col:
                pct0 = result.iloc[0][pct_col]
                pct1 = result.iloc[1][pct_col]
                insights.append({
                    "type": "summary",
                    "icon": "fa-chart-pie",
                    "title": "Overall Distribution",
                    "text": f"<strong>{row0_val}</strong> represents <strong>{pct0:.1f}%</strong> of total, while <strong>{row1_val}</strong> accounts for <strong>{pct1:.1f}%</strong>."
                })

        # 3. Numeric Leader & Concentration / Comparison
        if num_cols and cat_cols and not rate_col and len(result) > 1:
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
                # Comparative average insight (no additive volume fallacy)
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
                    "text": f"<strong>{top_row[cat]}</strong> leads with <strong>{top_row[metric]:,.2f}</strong>, contributing <strong>{top_share:.1f}%</strong> of the total volume observed."
                })

                if len(sorted_df) >= 3:
                    top_3_sum = sorted_df.head(3)[metric].sum()
                    top_3_share = (top_3_sum / total_sum * 100) if total_sum > 0 else 0
                    insights.append({
                        "type": "trend",
                        "icon": "fa-layer-group",
                        "title": "Top-3 Concentration",
                        "text": f"The top 3 categories alone account for <strong>{top_3_share:.1f}%</strong> of the aggregate {metric.replace('_', ' ')}."
                    })

        # 4. Chart-Specific Interpretation
        if chart_config:
            chart_type = chart_config.get("type")
            if chart_type == "pie":
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

        # 5. Strategic Recommendation
        if rate_col or any(k in query.lower() for k in ["attrition", "turnover", "churn"]):
            insights.append({
                "type": "action",
                "icon": "fa-lightbulb",
                "title": "Strategic Recommendation",
                "text": "Focus retention and intervention efforts on the high-risk cohorts identified above to reduce turnover churn effectively."
            })

    return insights