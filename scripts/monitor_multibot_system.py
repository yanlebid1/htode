#!/usr/bin/env python3
"""
Multi-Bot System Monitor

Real-time monitoring for the dispatcher pattern with bot pool.
Tracks bot utilization, message throughput, and system health.
"""
import sys
import os
import time
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.db.database import get_db_session
from common.services.bot_assignment_service import bot_assignment_service
from common.config_multibot import multibot_config
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.progress import Progress, BarColumn, TextColumn

console = Console()

class MultiBotMonitor:
    """Monitor multi-bot system performance"""
    
    def __init__(self):
        self.console = Console()
        self.start_time = datetime.now(timezone.utc)
        
    def get_system_overview(self) -> Dict[str, Any]:
        """Get overall system statistics"""
        with get_db_session() as session:
            stats = bot_assignment_service.get_bot_statistics(session)
            
        # Calculate notification capacity
        active_bots = len([b for b in stats['bots'] if b['available_slots'] > 0])
        throughput_per_bot = 1500  # messages per minute
        total_throughput = active_bots * throughput_per_bot
        
        # Time to notify all users
        if total_throughput > 0:
            time_to_notify_all = stats['total_users'] / total_throughput
        else:
            time_to_notify_all = float('inf')
        
        stats['active_bots'] = active_bots
        stats['total_throughput'] = total_throughput
        stats['time_to_notify_all_minutes'] = round(time_to_notify_all, 1)
        
        return stats
    
    def create_bot_table(self, stats: Dict[str, Any]) -> Table:
        """Create table showing bot status"""
        table = Table(title="Bot Pool Status", show_header=True)
        
        table.add_column("Bot Name", style="cyan")
        table.add_column("Username", style="blue")
        table.add_column("Users", style="green")
        table.add_column("Capacity", style="yellow")
        table.add_column("Utilization", style="magenta")
        table.add_column("Status", style="white")
        
        for bot in stats['bots']:
            # Determine status
            utilization = float(bot['utilization'].rstrip('%'))
            if utilization >= 95:
                status = "[red]FULL[/red]"
            elif utilization >= 90:
                status = "[yellow]HIGH[/yellow]"
            elif utilization >= 70:
                status = "[green]OPTIMAL[/green]"
            else:
                status = "[blue]AVAILABLE[/blue]"
            
            table.add_row(
                bot['name'],
                bot['username'],
                f"{bot['current_users']:,}",
                f"{bot['max_users']:,}",
                bot['utilization'],
                status
            )
        
        return table
    
    def create_overview_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create overview statistics panel"""
        content = f"""
[bold cyan]System Overview[/bold cyan]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[yellow]Total Capacity:[/yellow] {stats['total_capacity']:,} users
[green]Current Users:[/green] {stats['total_users']:,} users
[magenta]Overall Utilization:[/magenta] {stats['overall_utilization']}

[bold white]Notification Performance[/bold white]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[cyan]Active Bots:[/cyan] {stats['active_bots']} bots
[blue]Throughput:[/blue] {stats['total_throughput']:,} users/min
[green]Time for All Users:[/green] {stats['time_to_notify_all_minutes']} minutes

[bold white]Comparison[/bold white]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[red]Single Bot:[/red] {round(stats['total_users'] / 1500, 1)} minutes
[green]Multi Bot:[/green] {stats['time_to_notify_all_minutes']} minutes
[yellow]Improvement:[/yellow] {round((stats['total_users'] / 1500) / max(stats['time_to_notify_all_minutes'], 0.1), 1)}x faster
"""
        return Panel(content, title="Multi-Bot System Monitor", border_style="blue")
    
    def create_recommendations(self, stats: Dict[str, Any]) -> Panel:
        """Create recommendations panel"""
        recommendations = []
        
        # Check overall utilization
        utilization = float(stats['overall_utilization'].rstrip('%'))
        if utilization > 90:
            recommendations.append("[red]⚠️  High utilization! Consider adding more bots[/red]")
        elif utilization > 80:
            recommendations.append("[yellow]📊 Utilization approaching limits[/yellow]")
        else:
            recommendations.append("[green]✅ System operating within normal parameters[/green]")
        
        # Check individual bot status
        full_bots = sum(1 for b in stats['bots'] if float(b['utilization'].rstrip('%')) >= 95)
        if full_bots > 0:
            recommendations.append(f"[red]🚨 {full_bots} bot(s) at capacity[/red]")
        
        # Performance recommendations
        if stats['time_to_notify_all_minutes'] > 5:
            recommendations.append("[yellow]⏱️  Consider adding bots to reduce notification time[/yellow]")
        
        content = "\n".join(recommendations) if recommendations else "[green]✅ All systems optimal[/green]"
        
        return Panel(content, title="Recommendations", border_style="yellow")
    
    def run_continuous(self, refresh_interval: int = 5):
        """Run continuous monitoring"""
        layout = Layout()
        
        with Live(layout, refresh_per_second=1, screen=True) as live:
            while True:
                try:
                    stats = self.get_system_overview()
                    
                    # Create components
                    overview = self.create_overview_panel(stats)
                    bot_table = self.create_bot_table(stats)
                    recommendations = self.create_recommendations(stats)
                    
                    # Update layout
                    layout.split_column(
                        Layout(overview, size=15),
                        Layout(bot_table),
                        Layout(recommendations, size=8)
                    )
                    
                    time.sleep(refresh_interval)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    time.sleep(refresh_interval)
    
    def run_once(self):
        """Run one-time check"""
        try:
            stats = self.get_system_overview()
            
            # Display results
            console.print(self.create_overview_panel(stats))
            console.print()
            console.print(self.create_bot_table(stats))
            console.print()
            console.print(self.create_recommendations(stats))
            
            # Additional details
            console.print("\n[bold cyan]Bot Pool Configuration:[/bold cyan]")
            for bot in multibot_config.get_active_bots():
                console.print(f"  • {bot.username} ({bot.name}): {bot.max_users:,} users max")
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise

def main():
    parser = argparse.ArgumentParser(description="Monitor multi-bot system")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds (default: 5)"
    )
    
    args = parser.parse_args()
    
    monitor = MultiBotMonitor()
    
    if args.once:
        monitor.run_once()
    else:
        console.print("[bold green]Starting Multi-Bot System Monitor[/bold green]")
        console.print("Press Ctrl+C to exit\n")
        monitor.run_continuous(args.interval)

if __name__ == "__main__":
    main() 