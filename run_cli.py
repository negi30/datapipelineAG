#!/usr/bin/env python3
"""
Interactive Terminal CLI for DataChat Agent using rich console.
"""

import sys
import pandas as pd

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.prompt import Prompt
    console = Console()
except ImportError:
    print("For full terminal styling, install rich: pip install rich")
    class DummyConsole:
        def print(self, *args, **kwargs):
            print(*args)
    console = DummyConsole()

from api.data_loader import dataset_manager
from api.agent import generate_pandas_code
from api.execution_engine import execute_generated_code

def display_dataframe(df: pd.DataFrame, title="Result"):
    if not hasattr(console, 'print'):
        print(df.to_string())
        return
        
    table = Table(title=title, show_header=True, header_style="bold magenta")
    for col in df.columns:
        table.add_column(str(col), style="cyan")

    for _, row in df.head(30).iterrows():
        table.add_row(*[str(val) for val in row])

    console.print(table)
    if len(df) > 30:
        console.print(f"[italic yellow](Showing first 30 of {len(df)} total rows)[/italic yellow]")

def main():
    if hasattr(console, 'rule'):
        console.rule("[bold cyan]📊 DataChat AI Terminal Agent[/bold cyan]")
    else:
        print("=== 📊 DataChat AI Terminal Agent ===")

    info = dataset_manager.get_info()
    console.print(f"[green]✔ Loaded dataset:[/green] [bold]{info['dataset_name']}[/bold] ({info['rows']} rows, {info['columns_count']} columns, {info['memory_mb']} MB)")
    console.print("[dim]Type your question in natural language, or 'schema', 'summary', 'dict', 'exit'.[/dim]\n")

    while True:
        try:
            query = Prompt.ask("\n[bold cyan]Ask data[/bold cyan]") if hasattr(console, 'rule') else input("\nAsk data: ")
            query = query.strip()

            if not query:
                continue

            if query.lower() in ("exit", "quit", "q"):
                console.print("[yellow]Goodbye![/yellow]")
                break

            if query.lower() == "schema":
                console.print(Panel(dataset_manager.schema, title="Dataset Schema", border_style="cyan"))
                continue

            if query.lower() == "summary":
                console.print(Panel(dataset_manager.summary, title="Statistical Summary", border_style="green"))
                continue

            if query.lower() == "dict":
                console.print(Panel(dataset_manager.data_dictionary, title="Data Dictionary", border_style="amber"))
                continue

            console.print("[dim]Generating code and analyzing...[/dim]")

            # 1. Generate code
            agent_res = generate_pandas_code(
                user_query=query,
                df=dataset_manager.df,
                schema=dataset_manager.schema,
                summary=dataset_manager.summary,
                data_dictionary=dataset_manager.data_dictionary
            )

            code = agent_res["code"]
            provider = agent_res["provider"]

            console.print(f"[dim]Provider: {provider}[/dim]")
            if hasattr(console, 'print') and hasattr(Syntax, '__init__'):
                syntax = Syntax(code, "python", theme="monokai", line_numbers=False)
                console.print(Panel(syntax, title="Generated Pandas Code", border_style="indigo"))
            else:
                print(f"--- Code ---\n{code}\n------------")

            # 2. Execute code
            exec_res = execute_generated_code(code, dataset_manager.df)

            if not exec_res["success"]:
                console.print(f"[bold red]❌ Execution Error ({exec_res.get('error_type')}):[/bold red] {exec_res.get('error')}")
                continue

            console.print("[bold green]✔ Safety Passed & Code Executed[/bold green]")

            res_type = exec_res["result_type"]
            if res_type == "dataframe":
                df_res = pd.DataFrame(exec_res["data"])
                display_dataframe(df_res, title=f"Result for: {query}")
            elif res_type == "scalar":
                console.print(Panel(f"[bold white font-size=24]{exec_res['display']}[/bold white]", title="Scalar Metric", border_style="green"))
            else:
                console.print(exec_res.get("value"))

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting...[/yellow]")
            break

if __name__ == "__main__":
    main()
