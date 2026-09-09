import unittest
import pandas as pd
import numpy as np
from api.execution_engine import detect_chart_type, execute_generated_code, clean_dataframe_indices
from api.insights import generate_data_insights
from utils.code_safety import is_code_safe, validate_python_syntax

class TestExecutionEngine(unittest.TestCase):
    def test_grouped_bar_detection_for_pivot_table(self):
        df = pd.DataFrame({
            "Department": ["HR", "R&D", "Sales"],
            "Non-Travel": [5000.0, 6000.0, 7000.0],
            "Travel_Frequently": [5500.0, 6500.0, 7500.0],
            "Travel_Rarely": [5200.0, 6200.0, 7200.0]
        })
        chart = detect_chart_type(df)
        self.assertIsNotNone(chart)
        self.assertEqual(chart["type"], "grouped_bar")
        self.assertEqual(chart["barmode"], "group")
        self.assertEqual(chart["x"], ["HR", "R&D", "Sales"])
        self.assertEqual(len(chart["series"]), 3)
        self.assertEqual(chart["series"][0]["name"], "Non-Travel")
        self.assertEqual(chart["series"][0]["y"], [5000.0, 6000.0, 7000.0])
        self.assertIn("melted", chart)
        self.assertEqual(len(chart["melted"]), 9)

    def test_pivot_table_execution_resets_index(self):
        df = pd.DataFrame({
            "Department": ["HR", "HR", "Sales", "Sales"],
            "BusinessTravel": ["Non-Travel", "Travel_Frequently", "Non-Travel", "Travel_Frequently"],
            "MonthlyIncome": [5000, 6000, 7000, 8000]
        })
        code = "result = df.pivot_table(index='Department', columns='BusinessTravel', values='MonthlyIncome', aggfunc='mean')"
        res = execute_generated_code(code, df, "Average income by department and travel")
        self.assertTrue(res["success"])
        self.assertEqual(res["result_type"], "dataframe")
        self.assertIn("Department", res["columns"])
        self.assertEqual(res["chart"]["type"], "grouped_bar")
        self.assertEqual(res["chart"]["barmode"], "group")

    def test_donut_chart_prohibits_averages(self):
        # Averages should NOT produce a pie chart
        df_avg = pd.DataFrame({
            "Attrition": ["Yes", "No"],
            "YearsAtCompany": [5.13, 7.37]
        })
        chart = detect_chart_type(df_avg)
        self.assertIsNotNone(chart)
        self.assertEqual(chart["type"], "bar")

        # Counts SHOULD produce a pie chart
        df_count = pd.DataFrame({
            "Attrition": ["Yes", "No"],
            "Count": [237, 1233]
        })
        chart_pie = detect_chart_type(df_count)
        self.assertIsNotNone(chart_pie)
        self.assertEqual(chart_pie["type"], "pie")

    def test_scatter_plot_auto_detection_and_no_self_mapping(self):
        # 2 continuous numeric variables must trigger scatter, NOT a self-mapping bar chart
        df = pd.DataFrame({
            "Peak Streams": [2118242, 2127668, 1660502, 659366],
            "Total Streams": [883369738, 864832399, 781153024, 734857487]
        })
        chart = detect_chart_type(df, query="Create a scatter plot showing relationship between Peak Streams and Total Streams")
        self.assertIsNotNone(chart)
        self.assertEqual(chart["type"], "scatter")
        self.assertEqual(chart["x_label"], "Peak Streams")
        self.assertEqual(chart["y_label"], "Total Streams")
        self.assertNotEqual(chart["x_label"], chart["y_label"])
        self.assertEqual(chart["title"], "Total Streams vs Peak Streams")

    def test_scatter_plot_query_with_category_hover(self):
        df = pd.DataFrame({
            "Song Name": ["Sunflower", "Lucid Dreams", "XO TOUR Llif3"],
            "Peak Streams": [2118242, 2127668, 1660502],
            "Total Streams": [883369738, 864832399, 781153024]
        })
        chart = detect_chart_type(df, query="Create a scatter plot showing relationship between Peak Streams and Total Streams")
        self.assertIsNotNone(chart)
        self.assertEqual(chart["type"], "scatter")
        self.assertIn("text", chart)
        self.assertEqual(chart["text"], ["Sunflower", "Lucid Dreams", "XO TOUR Llif3"])

    def test_raw_dataframe_index_cleaning_prevents_metadata_metric(self):
        # Slicing a dataframe (like .head(1)) must NOT inject 'index' into columns
        df = pd.DataFrame({
            "Artist Name": ["Sheck Wes", "Olivia Rodrigo"],
            "Total Streams": [289673118.0, 172925647.0]
        }, index=[1269, 1073])
        
        cleaned = clean_dataframe_indices(df.head(1))
        self.assertNotIn("index", cleaned.columns)
        self.assertEqual(list(cleaned.columns), ["Artist Name", "Total Streams"])

        # Chart detection on cleaned single row should produce a single bar chart, NOT a grouped bar with index
        chart = detect_chart_type(cleaned, query="Which artist has the highest average streams per song?")
        self.assertIsNotNone(chart)
        self.assertEqual(chart["type"], "bar")
        self.assertEqual(chart["x"], ["Sheck Wes"])
        self.assertEqual(chart["y"], [289673118.0])

    def test_scale_incompatibility_prevents_grouped_bar_squashing(self):
        # When columns have wildly incompatible scales (e.g. 289M streams vs count of 1), do NOT group bar
        df = pd.DataFrame({
            "Artist Name": ["Sheck Wes", "Olivia Rodrigo"],
            "avg_streams": [289673118.0, 172925647.0],
            "song_count": [1, 12]
        })
        chart = detect_chart_type(df)
        self.assertIsNotNone(chart)
        # Should default to single bar chart for the primary metric rather than squashing song_count
        self.assertEqual(chart["type"], "bar")
        self.assertEqual(chart["title"], "avg streams by Artist Name")

    def test_bivariate_correlation_insights(self):
        # Compute scatter insights with positive correlation
        df = pd.DataFrame({
            "X": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "Y": [2, 4, 5, 8, 10, 11, 15, 16, 17, 20]
        })
        chart = detect_chart_type(df, query="scatter plot X vs Y")
        insights = generate_data_insights("scatter plot X vs Y", df, chart)
        self.assertTrue(any("Correlation" in ins.get("title", "") for ins in insights))
        self.assertTrue(any("r =" in ins.get("text", "") for ins in insights))

    def test_n1_sample_size_outlier_detection(self):
        source_df = pd.DataFrame({
            "Artist Name": ["Sheck Wes"] + ["Olivia Rodrigo"] * 10,
            "Total Streams": [289673118] + [100000000] * 10
        })
        result_df = pd.DataFrame({
            "Artist Name": ["Sheck Wes"],
            "Total Streams": [289673118.0]
        })
        chart = {"type": "bar", "x_label": "Artist Name", "y_label": "Total Streams"}
        insights = generate_data_insights("Which artist has the highest average streams per song?", result_df, chart, source_df=source_df)
        self.assertTrue(any("N=1" in ins.get("text", "") or "Sample Size" in ins.get("title", "") for ins in insights))

    def test_code_safety_rejections(self):
        unsafe_code = "import os; os.system('ls')"
        self.assertFalse(is_code_safe(unsafe_code))
        
        res = execute_generated_code(unsafe_code, pd.DataFrame({"a": [1]}))
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "SecurityViolation")

    def test_syntax_validation(self):
        bad_syntax = "result = df.groupby('a'.."
        is_valid, err = validate_python_syntax(bad_syntax)
        self.assertFalse(is_valid)

if __name__ == "__main__":
    unittest.main()
