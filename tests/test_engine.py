import unittest
import pandas as pd
import numpy as np
from api.execution_engine import detect_chart_type, execute_generated_code
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
