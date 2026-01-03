"""
Process Management API
Start/Stop/Monitor backend services and listeners
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict
import psutil
import subprocess
import os
from datetime import datetime
from app.core.security import get_current_user

router = APIRouter()

# In-memory service registry (in production: use database)
SERVICES = {}

class ServiceInfo(BaseModel):
    """Service information"""
    name: str
    description: str
    port: Optional[int] = None
    process_id: Optional[int] = None
    status: str  # running, stopped, error
    started_at: Optional[str] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None


class ServiceCommand(BaseModel):
    """Service command"""
    name: str
    command: Optional[str] = None
    working_dir: Optional[str] = None


async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require admin role for service management"""
    # TODO: Check actual admin role
    return current_user


def get_process_info(pid: int) -> Optional[Dict]:
    """Get process information by PID"""
    try:
        proc = psutil.Process(pid)
        if proc.is_running():
            return {
                "status": "running",
                "memory_mb": proc.memory_info().rss / 1024 / 1024,
                "cpu_percent": proc.cpu_percent(interval=0.1),
                "started_at": datetime.fromtimestamp(proc.create_time()).isoformat()
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return None


@router.get("/services", response_model=List[ServiceInfo])
async def list_services(admin: dict = Depends(require_admin)):
    """List all registered services with their status"""
    services = []
    
    # Check running uvicorn processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'uvicorn' in ' '.join(cmdline):
                # Extract port from command line
                port = None
                for i, arg in enumerate(cmdline):
                    if '--port' in arg and i + 1 < len(cmdline):
                        port = int(cmdline[i + 1])
                
                info = get_process_info(proc.info['pid'])
                services.append(ServiceInfo(
                    name=f"uvicorn_{port or proc.info['pid']}",
                    description="FastAPI Backend Server",
                    port=port,
                    process_id=proc.info['pid'],
                    status=info['status'] if info else "unknown",
                    started_at=info['started_at'] if info else None,
                    memory_mb=info['memory_mb'] if info else None,
                    cpu_percent=info['cpu_percent'] if info else None
                ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Add registered services from memory
    for name, service_data in SERVICES.items():
        if service_data.get('process_id'):
            info = get_process_info(service_data['process_id'])
            if info:
                services.append(ServiceInfo(
                    name=name,
                    description=service_data.get('description', ''),
                    port=service_data.get('port'),
                    process_id=service_data['process_id'],
                    status=info['status'],
                    started_at=info['started_at'],
                    memory_mb=info['memory_mb'],
                    cpu_percent=info['cpu_percent']
                ))
            else:
                # Process not running anymore
                SERVICES[name]['process_id'] = None
                services.append(ServiceInfo(
                    name=name,
                    description=service_data.get('description', ''),
                    port=service_data.get('port'),
                    status="stopped"
                ))
    
    return services


@router.post("/services/start")
async def start_service(
    service: ServiceCommand,
    admin: dict = Depends(require_admin)
):
    """Start a service"""
    
    if not service.command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command is required"
        )
    
    try:
        # Start process
        working_dir = service.working_dir or os.getcwd()
        
        # Windows: Use CREATE_NEW_CONSOLE flag
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        
        process = subprocess.Popen(
            service.command,
            shell=True,
            cwd=working_dir,
            creationflags=creationflags
        )
        
        # Register service
        SERVICES[service.name] = {
            'process_id': process.pid,
            'command': service.command,
            'working_dir': working_dir,
            'description': f"Service {service.name}",
            'started_at': datetime.now().isoformat()
        }
        
        return {
            "success": True,
            "message": f"Service '{service.name}' started",
            "process_id": process.pid
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start service: {str(e)}"
        )


@router.post("/services/stop")
async def stop_service(
    service_name: str,
    admin: dict = Depends(require_admin)
):
    """Stop a service"""
    
    service_data = SERVICES.get(service_name)
    if not service_data or not service_data.get('process_id'):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found or not running"
        )
    
    try:
        pid = service_data['process_id']
        proc = psutil.Process(pid)
        
        # Terminate process gracefully
        proc.terminate()
        
        # Wait for termination (max 5 seconds)
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            # Force kill if not terminated
            proc.kill()
        
        # Update registry
        SERVICES[service_name]['process_id'] = None
        
        return {
            "success": True,
            "message": f"Service '{service_name}' stopped"
        }
        
    except psutil.NoSuchProcess:
        SERVICES[service_name]['process_id'] = None
        return {
            "success": True,
            "message": f"Service '{service_name}' was already stopped"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop service: {str(e)}"
        )


@router.post("/services/restart")
async def restart_service(
    service: ServiceCommand,
    admin: dict = Depends(require_admin)
):
    """Restart a service"""
    
    # Stop if running
    if service.name in SERVICES and SERVICES[service.name].get('process_id'):
        await stop_service(service.name, admin)
    
    # Start
    return await start_service(service, admin)


@router.get("/services/{service_name}")
async def get_service(
    service_name: str,
    admin: dict = Depends(require_admin)
):
    """Get detailed service information"""
    
    service_data = SERVICES.get(service_name)
    if not service_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found"
        )
    
    pid = service_data.get('process_id')
    if pid:
        info = get_process_info(pid)
        if info:
            return {
                "name": service_name,
                "process_id": pid,
                "command": service_data.get('command'),
                "working_dir": service_data.get('working_dir'),
                **info
            }
    
    return {
        "name": service_name,
        "status": "stopped",
        "command": service_data.get('command'),
        "working_dir": service_data.get('working_dir')
    }


@router.get("/system/status")
async def system_status(admin: dict = Depends(require_admin)):
    """Get overall system status"""
    
    # System info
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Count running services
    running_services = sum(
        1 for s in SERVICES.values() 
        if s.get('process_id') and get_process_info(s['process_id'])
    )
    
    return {
        "timestamp": datetime.now().isoformat(),
        "system": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / 1024 / 1024 / 1024,
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free / 1024 / 1024 / 1024
        },
        "services": {
            "total": len(SERVICES),
            "running": running_services,
            "stopped": len(SERVICES) - running_services
        }
    }
