"""
Service Management Script
Start, stop, restart all PDVM services
"""
import os
import sys
import subprocess
import time
import psutil
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

class ServiceManager:
    """Manage PDVM services"""
    
    def __init__(self):
        self.backend_dir = Path(__file__).parent
        self.venv_python = self.backend_dir / "venv" / "Scripts" / "python.exe"
        
    def start_backend(self, port=8000):
        """Start FastAPI backend"""
        print(f"🚀 Starting backend on port {port}...")
        
        cmd = [
            str(self.venv_python),
            "-m", "uvicorn",
            "app.main:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", str(port)
        ]
        
        process = subprocess.Popen(
            cmd,
            cwd=str(self.backend_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        
        print(f"✓ Backend started (PID: {process.pid})")
        return process
    
    def stop_service(self, port):
        """Stop service by port"""
        print(f"⏹ Stopping service on port {port}...")
        
        killed = 0
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        print(f"  Killing process {proc.pid} ({proc.name()})...")
                        proc.terminate()
                        proc.wait(timeout=5)
                        killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
        
        if killed > 0:
            print(f"✓ Stopped {killed} process(es)")
        else:
            print("  No processes found")
    
    def is_port_in_use(self, port):
        """Check if port is in use"""
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                return True
        return False
    
    def show_status(self):
        """Show status of all services"""
        print("\n" + "="*60)
        print("PDVM Service Status")
        print("="*60)
        
        # Check backend
        backend_running = self.is_port_in_use(8000)
        print(f"\nBackend (Port 8000): {'✓ Running' if backend_running else '✗ Stopped'}")
        
        # Check all Python processes
        print("\nRunning Python services:")
        found = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'python' in proc.name().lower():
                    cmdline = ' '.join(proc.cmdline())
                    if 'uvicorn' in cmdline:
                        print(f"  PID {proc.pid}: {proc.name()} - uvicorn")
                        found = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if not found:
            print("  None")
        
        print("\n" + "="*60)


def main():
    """Main entry point"""
    manager = ServiceManager()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python manage_services.py start    - Start all services")
        print("  python manage_services.py stop     - Stop all services")
        print("  python manage_services.py restart  - Restart all services")
        print("  python manage_services.py status   - Show service status")
        return
    
    command = sys.argv[1].lower()
    
    if command == "start":
        print("\n🚀 Starting PDVM Services...")
        print("-" * 60)
        
        # Check if already running
        if manager.is_port_in_use(8000):
            print("⚠ Backend already running on port 8000")
        else:
            manager.start_backend()
            time.sleep(2)
        
        manager.show_status()
        
        print("\n✓ Services started!")
        print("\nAccess:")
        print("  Backend API: http://localhost:8000")
        print("  API Docs:    http://localhost:8000/docs")
        print("\nTo stop services: python manage_services.py stop")
    
    elif command == "stop":
        print("\n⏹ Stopping PDVM Services...")
        print("-" * 60)
        
        manager.stop_service(8000)
        time.sleep(1)
        
        manager.show_status()
        
        print("\n✓ Services stopped!")
    
    elif command == "restart":
        print("\n🔄 Restarting PDVM Services...")
        print("-" * 60)
        
        manager.stop_service(8000)
        time.sleep(2)
        manager.start_backend()
        time.sleep(2)
        
        manager.show_status()
        
        print("\n✓ Services restarted!")
    
    elif command == "status":
        manager.show_status()
    
    else:
        print(f"Unknown command: {command}")
        print("Use: start, stop, restart, or status")


if __name__ == "__main__":
    main()
