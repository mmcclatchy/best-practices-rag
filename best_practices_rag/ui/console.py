from rich.console import Console


console = Console()


def print_success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]⚠[/yellow]  {message}")


def print_info(message: str) -> None:
    console.print(f"[cyan]ℹ[/cyan]  {message}")
