"""Rich console output for the Divergence Engine."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from divergence_engine.analysis.signals import SignalType
from divergence_engine.storage.models import DriftRecord

console = Console()

SIGNAL_COLORS = {
    SignalType.BUY_YES.value: "bold green",
    SignalType.BUY_NO.value: "bold red",
    SignalType.PRICED_IN.value: "dim",
    SignalType.NEUTRAL.value: "dim",
}

SIGNAL_ICONS = {
    SignalType.BUY_YES.value: ">>> BUY YES",
    SignalType.BUY_NO.value: ">>> BUY NO",
    SignalType.PRICED_IN.value: "=== PRICED IN",
    SignalType.NEUTRAL.value: "--- NEUTRAL",
}


def display_top_divergences(records: list[DriftRecord], title: str = "Polymarket Entry Signals") -> None:
    """Display a rich table of Polymarket entry opportunities."""
    if not records:
        console.print("[dim]No signals found.[/dim]")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("Event", style="bold", max_width=25)
    table.add_column("Indicator", style="bold cyan")
    table.add_column("ΔProb", justify="right")
    table.add_column("ΔMarket", justify="right")
    table.add_column("Drift", justify="right")
    table.add_column("Z-Score", justify="right")
    table.add_column("Signal", justify="center", min_width=15)
    table.add_column("Window", justify="right")

    for rec in records:
        color = SIGNAL_COLORS.get(rec.signal_type, "white")
        icon = SIGNAL_ICONS.get(rec.signal_type, rec.signal_type)

        z_str = f"{rec.z_score:.2f}" if rec.z_score is not None else "N/A"
        drift_color = "red" if abs(rec.drift) > 0.1 else "yellow" if abs(rec.drift) > 0.05 else "white"

        table.add_row(
            rec.event_slug,
            rec.ticker,
            _format_pct(rec.delta_p),
            _format_pct(rec.delta_a_normalized),
            f"[{drift_color}]{rec.drift:+.4f}[/{drift_color}]",
            f"[bold]{z_str}[/bold]",
            f"[{color}]{icon}[/{color}]",
            f"{rec.window_hours}h",
        )

    console.print(table)


def display_mappings(mappings: list, resolved: list | None = None) -> None:
    """Display configured event-asset mappings."""
    table = Table(title="Event-Asset Mappings", show_lines=True)
    table.add_column("Event Slug", style="bold")
    table.add_column("Description")
    table.add_column("Indicators", style="cyan")
    table.add_column("Direction")
    table.add_column("Status")

    resolved_slugs = set()
    if resolved:
        resolved_slugs = {r.mapping.event_slug for r in resolved}

    for m in mappings:
        status = "[green]Resolved[/green]" if m.event_slug in resolved_slugs else "[yellow]Pending[/yellow]"
        table.add_row(
            m.event_slug,
            m.description,
            ", ".join(m.asset_tickers),
            m.correlation_direction,
            status,
        )

    console.print(table)


def display_collection_summary(
    pred_count: int, asset_count: int, errors: int, elapsed: float
) -> None:
    """Display a summary of a collection run."""
    console.print()
    console.print(f"  Prediction snapshots: [bold green]{pred_count}[/bold green]")
    console.print(f"  Asset snapshots:      [bold green]{asset_count}[/bold green]")
    if errors > 0:
        console.print(f"  Errors:               [bold red]{errors}[/bold red]")
    console.print(f"  Elapsed:              {elapsed:.1f}s")
    console.print()


def display_analysis_summary(total: int, anomalies: int) -> None:
    """Display a summary of an analysis run."""
    console.print()
    console.print(f"  Pairs analyzed:  [bold]{total}[/bold]")
    console.print(f"  Entry signals:   [bold {'green' if anomalies > 0 else 'dim'}]{anomalies}[/bold {'green' if anomalies > 0 else 'dim'}]")
    console.print()


def _format_pct(value: float) -> str:
    """Format a decimal as a percentage with color."""
    pct = value * 100
    if pct > 0:
        return f"[green]+{pct:.2f}%[/green]"
    elif pct < 0:
        return f"[red]{pct:.2f}%[/red]"
    else:
        return f"{pct:.2f}%"
