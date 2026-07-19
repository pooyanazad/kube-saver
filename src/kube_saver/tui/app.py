"""kube-saver TUI application.

Textual-based terminal UI for real-time Kubernetes cost and waste visibility.

Screens:
    Dashboard — cluster overview, namespace waste table, alerts
    NamespaceDetail — drill-down into a namespace
    PodDetail — individual pod resource chart
    Recommendations — ranked recommendations with savings
    CostDashboard — cost breakdown by namespace and resource type
"""

from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Static,
)

from kube_saver.config import KubeSaverConfig, load_config
from kube_saver.tui.data import TUIData, load_data
from kube_saver.version import VERSION

# ── Helpers ────────────────────────────────────────────────────────────────

def _sym(data: TUIData) -> str:
    return data.currency.symbol

def _code(data: TUIData) -> str:
    return data.currency.code

def _fmt_cost(data: TUIData, usd: float) -> str:
    return f"{_sym(data)}{usd * data.exchange_rate:.2f}"

def _bar(ratio: float, width: int = 20) -> str:
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)

def _eff_color(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


# ── Summary Bar (reused across screens) ────────────────────────────────────

class SummaryBar(Widget):
    """Top summary bar showing cluster-level numbers."""

    DEFAULT_CSS = """
    SummaryBar {
        height: 3;
        padding: 0 1;
        background: $surface;
        dock: top;
    }
    """

    def __init__(self, data: TUIData) -> None:
        super().__init__()
        self.data = data

    def set_data(self, data: TUIData) -> None:
        """Update data and re-render."""
        self.data = data
        self.refresh()

    def render(self) -> str:
        d = self.data
        if not d.connected or not d.cluster:
            return "Not connected"
        c = d.cluster
        ns_count = len(d.resource_report.namespaces) if d.resource_report else 0
        pod_count = d.resource_report.total_pods if d.resource_report else 0
        waste_cpu = d.resource_report.total_cpu_waste_millicores if d.resource_report else 0
        waste_mem = d.resource_report.total_memory_waste_bytes if d.resource_report else 0
        waste_cost = d.cost_report.total_cost_waste.monthly_usd if d.cost_report else 0
        eff = 100 - (d.cost_report.waste_ratio * 100) if d.cost_report else 100
        sym = _sym(d)
        return (
            f" {c.name} v{c.version} | "
            f"Nodes {c.node_count} | NS {ns_count} | Pods {pod_count} | "
            f"CPU waste {waste_cpu:.0f}m | Mem waste {waste_mem / 1024**2:.0f}Mi | "
            f"Waste {sym}{waste_cost * d.exchange_rate:.2f}/mo | "
            f"Efficiency {eff:.0f}% "
        )


# ── Dashboard Screen ──────────────────────────────────────────────────────

class Dashboard(Screen):
    """Main dashboard — cluster summary, namespace table, alerts."""

    BINDINGS = [
        Binding("enter", "drill_down", "Namespace detail"),
        Binding("r", "refresh", "Refresh"),
        Binding("2", "show_cost", "Cost view"),
        Binding("3", "show_recs", "Recommendations"),
        Binding("slash", "search", "Search"),
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help"),
    ]

    CSS = """
    Dashboard > DataTable { height: 1fr; }
    Dashboard > Static#alerts { height: auto; max-height: 5; padding: 0 1; }
    Dashboard > Static#status { height: 1; dock: bottom; padding: 0 1; background: $surface; }
    Dashboard > Static#search_bar { height: 1; dock: top; padding: 0 1; display: none; }
    Dashboard > Static#search_bar.show { display: block; }
    """

    def __init__(self, data: TUIData) -> None:
        super().__init__()
        self.data = data
        self._filter: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield SummaryBar(self.data)
        yield Static("", id="search_bar")
        with Container(id="table_container"):
            yield DataTable(id="ns_table")
        yield Static("", id="alerts")
        yield Static(self._status_text(), id="status")
        yield Footer()

    def _status_text(self) -> str:
        d = self.data
        ts = d.loaded_at.strftime("%H:%M:%S") if d.loaded_at else "never"
        conn = "[green]connected[/green]" if d.connected else "[red]disconnected[/red]"
        metric_source = d.metric_source.value if hasattr(d, "metric_source") else "estimated"
        if metric_source == "ebpf":
            metrics = "[green]eBPF[/green]"
        elif metric_source == "metrics-server":
            metrics = "[green]metrics-server[/green]"
        else:
            metrics = "[yellow]estimated[/yellow]"
        warn = " [yellow]fallback[/yellow]" if getattr(d, "warnings", []) else ""
        return f"  kube-saver v{VERSION} │ {conn} │ {metrics}{warn} │ updated {ts} │ {d.currency.code}"

    def on_mount(self) -> None:
        table = self.query_one("#ns_table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Namespace", "Pods", "CPU Waste", "Mem Waste",
            f"Waste/{_code(self.data)}", "Efficiency", "Score"
        )
        self._populate_table(table)
        table.focus()

    def _populate_table(self, table: DataTable, filter_text: str = "") -> None:
        table.clear()
        d = self.data
        if not d.resource_report:
            return
        ns_list = sorted(
            d.resource_report.namespaces,
            key=lambda ns: ns.cpu_waste_millicores,
            reverse=True,
        )
        ns_costs = {}
        if d.cost_report:
            ns_costs = {n.namespace: n for n in d.cost_report.namespaces}

        for ns in ns_list:
            name = ns.namespace.name
            if filter_text and filter_text.lower() not in name.lower():
                continue
            cpu_w = f"{ns.cpu_waste_millicores:.0f}m"
            mem_w = f"{ns.memory_waste_bytes / 1024**2:.0f}Mi"
            cost = ns_costs.get(name)
            monthly = _fmt_cost(d, cost.cost_waste.monthly_usd) if cost else "$0.00"
            eff = ns.efficiency_score
            score_bar = _bar(eff / 100)
            eff_str = f"[{_eff_color(eff)}]{eff:.0f}%[/]"
            table.add_row(
                name, str(ns.pod_count), cpu_w, mem_w,
                monthly, eff_str, score_bar,
                key=name,
            )

    def _refresh_table(self) -> None:
        table = self.query_one("#ns_table", DataTable)
        self._populate_table(table, self._filter)

    def _refresh_alerts(self) -> None:
        alerts_w = self.query_one("#alerts", Static)
        if not self.data.alerts:
            alerts_w.update("")
            return
        lines = []
        for a in self.data.alerts[:5]:
            color = "red" if a.level == "critical" else "yellow"
            lines.append(f"[{color}]{a.level.upper()}[/]: {a.target} — {a.message}")
        alerts_w.update("\n".join(lines))

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        status.update(self._status_text())

    def action_refresh(self) -> None:
        self.app.refresh_data()

    def action_drill_down(self) -> None:
        table = self.query_one("#ns_table", DataTable)
        if table.cursor_row is not None and table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            if row_idx < len(table.rows):
                ns_name = list(table.rows.keys())[row_idx]
                self.app.push_screen(NamespaceDetail(self.data, ns_name))

    def action_show_cost(self) -> None:
        self.app.push_screen(CostDashboard(self.data))

    def action_show_recs(self) -> None:
        self.app.push_screen(RecommendationsView(self.data))

    def action_search(self) -> None:
        bar = self.query_one("#search_bar", Static)
        bar.toggle_class("show")
        if bar.has_class("show"):
            current = self._filter or ""
            bar.update(f"[dim]Filter namespaces:[/] {current}")
        else:
            self._filter = ""
            self._refresh_table()

    def action_show_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def on_key(self, event) -> None:
        bar = self.query_one("#search_bar", Static)
        if bar.has_class("show"):
            if event.key == "escape":
                self._filter = ""
                bar.remove_class("show")
                self._refresh_table()
                event.stop()
            elif event.key == "backspace":
                self._filter = self._filter[:-1]
                bar.update(f"[dim]Filter namespaces:[/] {self._filter}")
                self._refresh_table()
                event.stop()
            elif len(event.character or "") == 1 and event.character.isprintable():
                self._filter += event.character
                bar.update(f"[dim]Filter namespaces:[/] {self._filter}")
                self._refresh_table()
                event.stop()


# ── Namespace Detail Screen ───────────────────────────────────────────────

class NamespaceDetail(Screen):
    """Drill-down view for a single namespace."""

    BINDINGS = [
        Binding("enter", "drill_pod", "Pod detail"),
        Binding("escape", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    NamespaceDetail > DataTable { height: 1fr; }
    NamespaceDetail > Static#ns_header { height: 3; padding: 0 1; background: $surface; }
    NamespaceDetail > Static#ns_footer { height: 1; dock: bottom; padding: 0 1; background: $surface; }
    """

    def __init__(self, data: TUIData, namespace: str) -> None:
        super().__init__()
        self.data = data
        self.namespace = namespace

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._header_text(), id="ns_header")
        yield DataTable(id="pod_table")
        yield Static("  [dim]Enter: pod detail │ Esc: back │ r: refresh[/dim]", id="ns_footer")
        yield Footer()

    def _header_text(self) -> str:
        d = self.data
        ns_report = None
        if d.resource_report:
            ns_report = next(
                (ns for ns in d.resource_report.namespaces if ns.namespace.name == self.namespace),
                None,
            )
        if not ns_report:
            return f"{self.namespace} - no data"

        cpu_w = ns_report.cpu_waste_millicores
        mem_w = ns_report.memory_waste_bytes / 1024**2
        eff = ns_report.efficiency_score
        return (
            f"{self.namespace} | "
            f"Pods: {ns_report.pod_count} | "
            f"CPU waste: {cpu_w:.0f}m | "
            f"Mem waste: {mem_w:.0f}Mi | "
            f"Efficiency: {eff:.0f}%"
        )

    def on_mount(self) -> None:
        table = self.query_one("#pod_table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Pod", "Workload", "CPU Req", "CPU Actual", "CPU Waste",
            "Mem Req", "Mem Actual", "Mem Waste", "Restarts"
        )
        self._populate(table)
        table.focus()

    def _populate(self, table: DataTable) -> None:
        d = self.data
        if not d.resource_report:
            return
        ns_report = next(
            (ns for ns in d.resource_report.namespaces if ns.namespace.name == self.namespace),
            None,
        )
        if not ns_report:
            return

        for pw in sorted(ns_report.pod_waste, key=lambda p: p.cpu_waste_millicores, reverse=True):
            pod = pw.pod
            cpu_req = f"{pod.resources.cpu_millicores_request:.0f}m"
            cpu_act = f"{pod.actual.cpu_millicores:.0f}m"
            cpu_w = f"[red]{pw.cpu_waste_millicores:.0f}m[/red]" if pw.cpu_waste_millicores > 0 else "[green]0m[/green]"
            mem_req = f"{pod.resources.memory_bytes_request / 1024**2:.0f}Mi"
            mem_act = f"{pod.actual.memory_bytes / 1024**2:.0f}Mi"
            mem_w = f"[red]{pw.memory_waste_bytes / 1024**2:.0f}Mi[/red]" if pw.memory_waste_bytes > 0 else "[green]0Mi[/green]"
            restarts = f"[red]{pod.restart_count}[/red]" if pod.restart_count > 0 else "0"
            table.add_row(
                pod.name, f"{pod.workload_kind}/{pod.workload_name}",
                cpu_req, cpu_act, cpu_w, mem_req, mem_act, mem_w, restarts,
                key=pod.name,
            )

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_drill_pod(self) -> None:
        table = self.query_one("#pod_table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            if row_idx < len(table.rows):
                pod_name = list(table.rows.keys())[row_idx]
                self.app.push_screen(PodDetail(self.data, self.namespace, pod_name))

    def action_refresh(self) -> None:
        self.app.refresh_data()


# ── Pod Detail Screen ─────────────────────────────────────────────────────

class PodDetail(Screen):
    """Detailed view for a single pod with ASCII resource charts."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    CSS = """
    PodDetail > Static#pod_info { height: auto; padding: 1 1; background: $surface; }
    PodDetail > Static#pod_chart { height: 1fr; padding: 1 1; }
    PodDetail > Static#pod_footer { height: 1; dock: bottom; padding: 0 1; background: $surface; }
    """

    def __init__(self, data: TUIData, namespace: str, pod_name: str) -> None:
        super().__init__()
        self.data = data
        self.namespace = namespace
        self.pod_name = pod_name

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._info_text(), id="pod_info")
        yield Static(self._chart_text(), id="pod_chart")
        yield Static("  [dim]Esc: back[/dim]", id="pod_footer")
        yield Footer()

    def _find_pod_waste(self):
        d = self.data
        if not d.resource_report:
            return None
        for ns in d.resource_report.namespaces:
            if ns.namespace.name == self.namespace:
                for pw in ns.pod_waste:
                    if pw.pod.name == self.pod_name:
                        return pw
        return None

    def _info_text(self) -> str:
        pw = self._find_pod_waste()
        if not pw:
            return f"[red]Pod {self.pod_name} not found[/red]"
        pod = pw.pod
        lines = [
            f"[bold cyan]{pod.name}[/bold cyan]  in  [bold]{pod.namespace}[/bold]",
            f"Workload: {pod.workload_kind}/{pod.workload_name}",
            f"Restart count: {pod.restart_count}",
            f"Health score: [{_eff_color(pw.efficiency_score if hasattr(pw, 'efficiency_score') else 50)}]—[/]",
        ]
        return "\n".join(lines)

    def _chart_text(self) -> str:
        pw = self._find_pod_waste()
        if not pw:
            return ""
        pod = pw.pod
        d = self.data

        cpu_req = pod.resources.cpu_millicores_request
        cpu_act = pod.actual.cpu_millicores
        cpu_ratio = cpu_act / cpu_req if cpu_req > 0 else 0

        mem_req = pod.resources.memory_bytes_request
        mem_act = pod.actual.memory_bytes
        mem_ratio = mem_act / mem_req if mem_req > 0 else 0

        limit_req = pod.resources.cpu_millicores_limit
        limit_mem = pod.resources.memory_bytes_limit

        sym = _sym(d)
        lines = [
            "[bold]CPU[/bold]",
            f"  Request : {cpu_req:.0f}m",
            f"  Actual  : {cpu_act:.0f}m",
            f"  Limit   : {limit_req:.0f}m",
            f"  Usage   : {_bar(cpu_ratio)} {cpu_ratio:.0%}",
            f"  Waste   : [red]{pw.cpu_waste_millicores:.0f}m[/red]",
            "",
            "[bold]Memory[/bold]",
            f"  Request : {mem_req / 1024**2:.0f}Mi",
            f"  Actual  : {mem_act / 1024**2:.1f}Mi",
            f"  Limit   : {limit_mem / 1024**2:.0f}Mi",
            f"  Usage   : {_bar(mem_ratio)} {mem_ratio:.0%}",
            f"  Waste   : [red]{pw.memory_waste_bytes / 1024**2:.0f}Mi[/red]",
            "",
        ]

        # Find recommendation for this pod
        for rec in d.recommendations:
            if rec.target_namespace == self.namespace and rec.container_name == self.pod_name:
                lines.append(f"[bold green]Recommendation:[/bold green] {rec.resource_type}: {rec.current_value} → {rec.suggested_value} ({rec.confidence})")
                lines.append(f"  Savings: {sym}{rec.estimated_savings.monthly_usd * d.exchange_rate:.2f}/mo")
                lines.append(f"  Reason: {rec.reason}")
                lines.append("")

        return "\n".join(lines)

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ── Recommendations View ──────────────────────────────────────────────────

class RecommendationsView(Screen):
    """Dedicated screen for all recommendations."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "show_dashboard", "Dashboard"),
    ]

    CSS = """
    RecommendationsView > DataTable { height: 1fr; }
    RecommendationsView > Static#rec_header { height: auto; padding: 0 1; background: $surface; }
    RecommendationsView > Static#rec_footer { height: 1; dock: bottom; padding: 0 1; background: $surface; }
    """

    def __init__(self, data: TUIData) -> None:
        super().__init__()
        self.data = data

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._summary_text(), id="rec_header")
        yield DataTable(id="rec_table")
        yield Static("  [dim]Esc: back │ 1: dashboard │ r: refresh[/dim]", id="rec_footer")
        yield Footer()

    def _summary_text(self) -> str:
        d = self.data
        total = len(d.recommendations)
        high = sum(1 for r in d.recommendations if r.confidence == "high")
        med = sum(1 for r in d.recommendations if r.confidence == "medium")
        low = sum(1 for r in d.recommendations if r.confidence == "low")
        total_savings = sum(r.estimated_savings.monthly_usd for r in d.recommendations) * d.exchange_rate
        sym = _sym(d)
        return (
            f"[bold]Recommendations[/bold]  │  "
            f"Total: {total}  │  "
            f"[green]High: {high}[/green]  [yellow]Med: {med}[/yellow]  [dim]Low: {low}[/dim]  │  "
            f"Potential savings: [bold green]{sym}{total_savings:.2f}/mo[/bold green]"
        )

    def on_mount(self) -> None:
        table = self.query_one("#rec_table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Target", "Type", "Current", "Suggested", "Confidence", "Savings/mo", "Reason"
        )
        d = self.data
        sym = _sym(d)
        for rec in d.recommendations:
            conf_color = {"high": "green", "medium": "yellow", "low": "dim"}.get(rec.confidence, "white")
            table.add_row(
                f"{rec.target_namespace}/{rec.target_name}",
                rec.resource_type,
                rec.current_value,
                rec.suggested_value,
                f"[{conf_color}]{rec.confidence}[/]",
                f"{sym}{rec.estimated_savings.monthly_usd * d.exchange_rate:.2f}",
                rec.reason,
            )
        table.focus()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.app.refresh_data()

    def action_show_dashboard(self) -> None:
        self.app.pop_screen()


# ── Cost Dashboard Screen ─────────────────────────────────────────────────

class CostDashboard(Screen):
    """Cost breakdown by namespace with bar chart."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "show_dashboard", "Dashboard"),
    ]

    CSS = """
    CostDashboard > DataTable { height: 1fr; }
    CostDashboard > Static#cost_header { height: auto; padding: 0 1; background: $surface; }
    CostDashboard > Static#cost_chart { height: auto; padding: 0 1; }
    CostDashboard > Static#cost_footer { height: 1; dock: bottom; padding: 0 1; background: $surface; }
    """

    def __init__(self, data: TUIData) -> None:
        super().__init__()
        self.data = data

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._summary_text(), id="cost_header")
        yield DataTable(id="cost_table")
        yield Static(self._chart_text(), id="cost_chart")
        yield Static("  [dim]Esc: back │ 1: dashboard │ r: refresh[/dim]", id="cost_footer")
        yield Footer()

    def _summary_text(self) -> str:
        d = self.data
        if not d.cost_report:
            return "[yellow]No cost data available[/yellow]"
        sym = _sym(d)
        cr = d.cost_report
        return (
            f"[bold]Cost Dashboard[/bold]  │  "
            f"Requested: {sym}{cr.total_requested_cost.monthly_usd * d.exchange_rate:.2f}/mo  │  "
            f"Wasted: [bold red]{sym}{cr.total_cost_waste.monthly_usd * d.exchange_rate:.2f}/mo[/bold red]  │  "
            f"Annual: {sym}{cr.total_cost_waste.yearly_usd * d.exchange_rate:.2f}  │  "
            f"Waste ratio: [red]{cr.waste_ratio:.0%}[/red]"
        )

    def _chart_text(self) -> str:
        d = self.data
        if not d.cost_report:
            return ""
        sym = _sym(d)
        lines = ["[bold]Namespace Cost Bar Chart[/bold]", ""]
        max_cost = max(
            (n.cost_waste.monthly_usd for n in d.cost_report.namespaces),
            default=1,
        )
        for ns in d.cost_report.namespaces[:8]:
            ratio = ns.cost_waste.monthly_usd / max_cost if max_cost > 0 else 0
            bar_width = 40
            filled = int(ratio * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            cost_str = f"{sym}{ns.cost_waste.monthly_usd * d.exchange_rate:.2f}"
            lines.append(f"  {ns.namespace:<25s} {bar} {cost_str}")
        return "\n".join(lines)

    def on_mount(self) -> None:
        table = self.query_one("#cost_table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(
            "Namespace", "Pods", "CPU Waste", "Mem Waste",
            "Waste/mo", "Efficiency"
        )
        d = self.data
        sym = _sym(d)
        if not d.cost_report:
            return
        for ns in d.cost_report.namespaces:
            eff = ns.efficiency_score
            ns_res = next(
                (n for n in d.resource_report.namespaces if n.namespace.name == ns.namespace),
                None,
            ) if d.resource_report else None
            pod_count = ns_res.pod_count if ns_res else 0
            table.add_row(
                ns.namespace,
                str(pod_count),
                f"{ns.cpu_waste_millicores:.0f}m",
                f"{ns.memory_waste_bytes / 1024**2:.0f}Mi",
                f"{sym}{ns.cost_waste.monthly_usd * d.exchange_rate:.2f}",
                f"[{_eff_color(eff)}]{eff:.0f}%[/]",
            )
        table.focus()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.app.refresh_data()

    def action_show_dashboard(self) -> None:
        self.app.pop_screen()


# ── Help Screen ───────────────────────────────────────────────────────────

class HelpScreen(Screen):
    """Keyboard shortcuts help screen."""

    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "[bold]kube-saver Keyboard Shortcuts[/bold]\n\n"
            "  [cyan]j/k[/] or [cyan]↑/↓[/]     Navigate up/down\n"
            "  [cyan]Enter[/]           Drill into namespace / pod\n"
            "  [cyan]Esc[/]             Go back\n"
            "  [cyan]1[/]               Dashboard\n"
            "  [cyan]2[/]               Cost view\n"
            "  [cyan]3[/]               Recommendations\n"
            "  [cyan]/[/]               Search / filter\n"
            "  [cyan]r[/]               Refresh data\n"
            "  [cyan]?[/]               This help screen\n"
            "  [cyan]q[/]               Quit\n"
        )
        yield Footer()

    def action_go_back(self) -> None:
        self.app.pop_screen()


# ── Main App ──────────────────────────────────────────────────────────────

class KubeSaverApp(App):
    """kube-saver TUI — live Kubernetes cost and waste dashboard."""

    TITLE = "kube-saver"
    SUB_TITLE = "Kubernetes Cost & Waste Dashboard"

    CSS = """
    Screen { background: $background; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config: KubeSaverConfig | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        self._data = TUIData()
        self._refresh_timer: Timer | None = None

    def on_mount(self) -> None:
        self.push_screen(Dashboard(self._data))
        self.refresh_data()
        self._refresh_timer = self.set_interval(30, self.refresh_data)

    @work(exclusive=True, group="data_loader", thread=True)
    def refresh_data(self) -> None:
        """Reload data from the cluster in a background thread."""
        new_data = load_data(self.config)
        self._data = new_data
        self.call_from_thread(self._update_screens)

    def _update_screens(self) -> None:
        """Push fresh data into the current screen."""
        screen = self.screen
        if isinstance(screen, Dashboard):
            screen.data = self._data
            try:
                summary = screen.query_one(SummaryBar)
                summary.set_data(self._data)
            except Exception:
                pass
            screen._refresh_table()
            screen._refresh_alerts()
            screen._refresh_status()

    def action_quit(self) -> None:
        self.exit()
