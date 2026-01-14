import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import './ServiceManager.css';

interface Service {
  name: string;
  description: string;
  port?: number;
  process_id?: number;
  status: string;
  started_at?: string;
  memory_mb?: number;
  cpu_percent?: number;
}

const ServiceManager: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadServices();
    const interval = setInterval(loadServices, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadServices = async () => {
    try {
      const response = await apiClient.get<Service[]>('/processes/services');
      setServices(response.data);
      setError('');
    } catch (err: any) {
      setError('Fehler beim Laden der Services');
      console.error(err);
    }
  };

  const handleStop = async (serviceName: string) => {
    setLoading(true);
    try {
      await apiClient.post(`/processes/services/stop?service_name=${serviceName}`);
      await loadServices();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Stoppen');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="service-manager">
      <div className="manager-header">
        <h2>Services & Lauscher</h2>
        <button onClick={loadServices} className="refresh-button">
          🔄 Aktualisieren
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="services-list">
        {services.length === 0 ? (
          <div className="empty-state">
            <p>Keine laufenden Services gefunden</p>
            <p className="hint">Services werden automatisch erkannt, wenn sie gestartet werden</p>
          </div>
        ) : (
          services.map((service) => (
            <div key={service.name} className={`service-item ${service.status}`}>
              <div className="service-info">
                <div className="service-header">
                  <h3>{service.description || service.name}</h3>
                  <span className={`status-badge ${service.status}`}>
                    {service.status === 'running' ? '✓ Läuft' : '● Gestoppt'}
                  </span>
                </div>
                <div className="service-details">
                  {service.port && <span>Port: {service.port}</span>}
                  {service.process_id && <span>PID: {service.process_id}</span>}
                  {service.memory_mb && <span>RAM: {service.memory_mb.toFixed(1)} MB</span>}
                  {service.cpu_percent !== undefined && <span>CPU: {service.cpu_percent.toFixed(1)}%</span>}
                </div>
                {service.started_at && (
                  <div className="service-time">
                    Gestartet: {new Date(service.started_at).toLocaleString('de-DE')}
                  </div>
                )}
              </div>
              <div className="service-actions">
                {service.status === 'running' && (
                  <button
                    onClick={() => handleStop(service.name)}
                    disabled={loading}
                    className="stop-button"
                  >
                    ⏹ Stoppen
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="info-box">
        <h4>ℹ️ Hinweis</h4>
        <p>Services werden automatisch erkannt und können hier verwaltet werden.</p>
        <p>Zum Starten eines Service verwende die PowerShell-Scripts im backend-Ordner.</p>
      </div>
    </div>
  );
};

export default ServiceManager;
