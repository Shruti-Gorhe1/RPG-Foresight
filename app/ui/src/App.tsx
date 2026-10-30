import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import DashboardPage from './pages/DashboardPage'
import ConnectorsPage from './pages/ConnectorsPage'
import RulesPage from './pages/RulesPage'
import RecipientsPage from './pages/RecipientsPage'
import SignalHistoryPage from './pages/SignalHistoryPage'
import DeliveryStatusPage from './pages/DeliveryStatusPage'
import TenderOperationsPage from './pages/TenderOperationsPage'
import PursuitCopilotPage from './pages/PursuitCopilotPage'

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/rules" element={<RulesPage />} />
          <Route path="/recipients" element={<RecipientsPage />} />
          <Route path="/signal-history" element={<SignalHistoryPage />} />
          <Route path="/delivery-status" element={<DeliveryStatusPage />} />
          <Route path="/tenders" element={<TenderOperationsPage />} />
          <Route path="/pursuit-copilot" element={<PursuitCopilotPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}