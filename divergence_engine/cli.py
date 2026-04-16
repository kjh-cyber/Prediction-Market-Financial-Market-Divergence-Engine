"""CLI interface for the Divergence Engine."""

from __future__ import annotations

import logging
import time

import typer
from rich.console import Console
from rich.logging import RichHandler

from divergence_engine.config import settings

app = typer.Typer(
    name="divergence-engine",
    help="Prediction Market × Financial Market Divergence Engine",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    # Only show our own logs at INFO level unless verbose
    if not verbose:
        logging.getLogger("divergence_engine").setLevel(logging.INFO)


@app.command()
def init_db() -> None:
    """Initialize the database schema."""
    from divergence_engine.storage.database import init_db as _init_db

    _init_db()
    console.print("[green]Database initialized.[/green]")


@app.command()
def mappings(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Show all configured event-asset mappings."""
    _setup_logging(verbose)
    from divergence_engine.mappings.definitions import get_all_mappings
    from divergence_engine.output.console import display_mappings

    all_mappings = get_all_mappings()
    display_mappings(all_mappings)


@app.command()
def resolve(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-resolution"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Resolve event-asset mappings to Polymarket tokens."""
    _setup_logging(verbose)
    from divergence_engine.collectors.polymarket import PolymarketCollector
    from divergence_engine.mappings.definitions import get_all_mappings
    from divergence_engine.mappings.registry import MappingRegistry
    from divergence_engine.output.console import display_mappings
    from divergence_engine.storage.database import init_db as _init_db

    _init_db()

    with PolymarketCollector() as collector:
        registry = MappingRegistry(collector)
        resolved = registry.resolve_all(force=force)

    all_mappings = get_all_mappings()
    display_mappings(all_mappings, resolved)
    console.print(f"\n[bold]Resolved: {len(resolved)}/{len(all_mappings)}[/bold]")


@app.command()
def collect(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Collect data from Polymarket and financial markets."""
    _setup_logging(verbose)
    from divergence_engine.output.console import display_collection_summary
    from divergence_engine.pipeline import Pipeline

    pipeline = Pipeline()
    pipeline.initialize()

    console.print("[bold]Resolving mappings...[/bold]")
    resolved = pipeline.resolve_mappings()
    console.print(f"  Resolved {len(resolved)} mappings")

    console.print("[bold]Collecting data...[/bold]")
    start = time.time()
    stats = pipeline.collect(resolved)
    elapsed = time.time() - start

    display_collection_summary(
        stats["pred_count"], stats["asset_count"], stats["errors"], elapsed
    )
    pipeline.close()


@app.command()
def analyze(
    window: int = typer.Option(
        None, "--window", "-w", help="Analysis window in hours"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run drift analysis on collected data."""
    _setup_logging(verbose)
    from divergence_engine.output.console import display_analysis_summary
    from divergence_engine.pipeline import Pipeline

    pipeline = Pipeline()
    pipeline.initialize()

    console.print("[bold]Resolving mappings...[/bold]")
    resolved = pipeline.resolve_mappings()

    console.print("[bold]Running analysis...[/bold]")
    stats = pipeline.analyze(resolved, window_hours=window)

    display_analysis_summary(stats["total_pairs"], stats["anomalies"])
    pipeline.close()


@app.command()
def top(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
    min_zscore: float = typer.Option(0.0, "--min-zscore", "-z", help="Minimum Z-score"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display top divergence events."""
    _setup_logging(verbose)
    from divergence_engine.output.console import display_top_divergences
    from divergence_engine.storage.database import get_db, init_db as _init_db
    from divergence_engine.storage.queries import get_top_divergences

    _init_db()

    with get_db() as conn:
        records = get_top_divergences(conn, limit=limit, min_zscore=min_zscore)

    display_top_divergences(records)


@app.command()
def run(
    watch: bool = typer.Option(False, "--watch", help="Run continuously"),
    interval: int = typer.Option(None, "--interval", "-i", help="Collection interval (seconds)"),
    window: int = typer.Option(None, "--window", "-w", help="Analysis window (hours)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the full pipeline: collect -> analyze -> display top divergences."""
    _setup_logging(verbose)
    from divergence_engine.output.console import (
        display_analysis_summary,
        display_collection_summary,
        display_top_divergences,
    )
    from divergence_engine.pipeline import Pipeline
    from divergence_engine.storage.database import get_db
    from divergence_engine.storage.queries import get_top_divergences

    poll_interval = interval or settings.collect_interval
    pipeline = Pipeline()
    pipeline.initialize()

    try:
        while True:
            console.rule("[bold blue]Divergence Engine[/bold blue]")

            # Resolve
            console.print("[bold]Resolving mappings...[/bold]")
            resolved = pipeline.resolve_mappings()
            console.print(f"  Resolved {len(resolved)} mappings")

            # Collect
            console.print("[bold]Collecting data...[/bold]")
            start = time.time()
            collect_stats = pipeline.collect(resolved)
            elapsed = time.time() - start
            display_collection_summary(
                collect_stats["pred_count"],
                collect_stats["asset_count"],
                collect_stats["errors"],
                elapsed,
            )

            # Analyze
            console.print("[bold]Analyzing drift...[/bold]")
            analysis_stats = pipeline.analyze(resolved, window_hours=window)
            display_analysis_summary(
                analysis_stats["total_pairs"], analysis_stats["anomalies"]
            )

            # Display top divergences
            with get_db() as conn:
                records = get_top_divergences(conn, limit=10)
            display_top_divergences(records)

            if not watch:
                break

            console.print(f"\n[dim]Next run in {poll_interval}s... (Ctrl+C to stop)[/dim]")
            time.sleep(poll_interval)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")
    finally:
        pipeline.close()


@app.command()
def dashboard() -> None:
    """Launch the Streamlit web dashboard."""
    import subprocess
    import sys

    dashboard_path = str(
        __import__("pathlib").Path(__file__).parent / "output" / "dashboard.py"
    )
    console.print("[bold]Launching dashboard...[/bold]")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", dashboard_path],
        check=True,
    )


if __name__ == "__main__":
    app()
