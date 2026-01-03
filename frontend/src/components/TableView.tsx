import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { tablesAPI } from '../api/client'

interface TableViewProps {
  token: string
}

export default function TableView({ token }: TableViewProps) {
  const { tableName } = useParams<{ tableName: string }>()
  
  const { data: records, isLoading, error } = useQuery({
    queryKey: ['table', tableName],
    queryFn: () => tablesAPI.getAll(tableName!, token),
    enabled: !!tableName,
  })

  if (isLoading) return <div style={styles.loading}>Loading...</div>
  if (error) return <div style={styles.error}>Error loading data</div>

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <Link to="/" style={styles.backLink}>← Back</Link>
        <h1 style={styles.title}>{tableName}</h1>
        <div style={styles.count}>{records?.length || 0} records</div>
      </header>
      
      <main style={styles.main}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>UID</th>
              <th style={styles.th}>Modified</th>
            </tr>
          </thead>
          <tbody>
            {records?.map((record) => (
              <tr key={record.uid} style={styles.tr}>
                <td style={styles.td}>{record.name || '-'}</td>
                <td style={styles.td}>{record.uid}</td>
                <td style={styles.td}>
                  {record.modified_at
                    ? new Date(record.modified_at).toLocaleString()
                    : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </main>
    </div>
  )
}

const styles = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: 'white',
    padding: '1rem 2rem',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  backLink: {
    color: '#007bff',
    textDecoration: 'none',
    fontSize: '1rem',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 'bold',
    color: '#333',
  },
  count: {
    fontSize: '0.9rem',
    color: '#666',
  },
  main: {
    padding: '2rem',
    maxWidth: '1200px',
    margin: '0 auto',
  },
  table: {
    width: '100%',
    backgroundColor: 'white',
    borderRadius: '8px',
    overflow: 'hidden',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    borderCollapse: 'collapse' as const,
  },
  th: {
    padding: '1rem',
    textAlign: 'left' as const,
    backgroundColor: '#f8f9fa',
    fontWeight: '600',
    borderBottom: '2px solid #dee2e6',
  },
  tr: {
    borderBottom: '1px solid #dee2e6',
  },
  td: {
    padding: '1rem',
  },
  loading: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    fontSize: '1.25rem',
    color: '#666',
  },
  error: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    fontSize: '1.25rem',
    color: '#dc3545',
  },
}
